# routes/Doctor_Portal/appointment_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, timedelta, time
import math
import json

# --- Authorization ---
def check_provider_authorization(user):
    """Checks if the user is an authenticated doctor or nutritionist."""
    if not user or not user.is_authenticated: return False
    user_type = getattr(user, 'user_type', None)
    return user_type in ['doctor', 'nutritionist']

# Helper to check if the current user can modify a specific appointment
# Expects user_id as an integer
def can_modify_appointment(cursor, appointment_id, user_id_int):
    """Checks if the user is the provider for the appointment."""
    cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, user_id_int))
    return cursor.fetchone() is not None

# Helper to safely get the integer ID from current_user
def get_provider_id(user):
    """Safely gets the integer user ID from the current_user object."""
    try:
        user_id_str = getattr(user, 'id', None)
        if user_id_str is None:
            raise ValueError("User ID attribute ('id') is missing or None.")
        return int(user_id_str)
    except (AttributeError, ValueError, TypeError) as e:
        current_app.logger.error(f"Could not get valid provider user ID from current_user. User: {user}, Error: {e}")
        return None


# --- Blueprint Definition ---
appointments_bp = Blueprint(
    'appointments',
    __name__,
    url_prefix='/portal/appointments',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 20
VALID_SORT_COLUMNS = {
    'date': 'a.appointment_date', 'patient': 'p_user.last_name', 'type': 'a.appointment_type',
    'status': 'a.status', 'doctor': 'd_user.last_name'
}
DEFAULT_SORT_COLUMN = 'date'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE = {}
DEFAULT_APPOINTMENT_DURATIONS = {
    'initial': 60, 'follow-up': 30, 'consultation': 45,
    'urgent': 30, 'routine': 20, 'telehealth': 30,
}

# --- Helper Functions ---

def get_enum_values(table_name, column_name):
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE: return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(); db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result:
            enum_str = result[0]
            values = [val.strip("'") for val in enum_str[enum_str.find("(")+1:enum_str.find(")")].split(",")]
        ENUM_CACHE[cache_key] = values; return values
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_col, name_col, order_by=None, where_clause=None, params=None):
    conn = None; cursor = None; items = []
    order_clause = f"ORDER BY {order_by}" if order_by else f"ORDER BY {name_col}"
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        query = f"SELECT {id_col}, {name_col} FROM {table_name} {where_sql} {order_clause}"
        cursor.execute(query, params or [])
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching from {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

def get_appointment_duration(appointment_type):
    return DEFAULT_APPOINTMENT_DURATIONS.get(appointment_type, 30)

def is_slot_available(cursor, doctor_id, appt_date, start_time, end_time, exclude_appointment_id=None):
    """Checks availability considering availability, overrides, and appointments."""
    schema_day_of_week = (appt_date.weekday() + 1) % 7
    # Check blocking overrides
    sql_override = "SELECT 1 FROM doctor_availability_overrides WHERE doctor_id = %s AND override_date = %s AND is_unavailable = TRUE AND ((start_time IS NULL) OR (%s < end_time AND %s > start_time)) LIMIT 1"
    cursor.execute(sql_override, (doctor_id, appt_date, start_time, end_time))
    if cursor.fetchone(): return False
    # Check conflicting appointments
    sql_appt_conflict = "SELECT 1 FROM appointments WHERE doctor_id = %s AND appointment_date = %s AND status NOT IN ('canceled', 'no-show') AND (%s < end_time AND %s > start_time)"
    params_appt = [doctor_id, appt_date, start_time, end_time]
    if exclude_appointment_id: sql_appt_conflict += " AND appointment_id != %s"; params_appt.append(exclude_appointment_id)
    sql_appt_conflict += " LIMIT 1"; cursor.execute(sql_appt_conflict, tuple(params_appt))
    if cursor.fetchone(): return False
    # Check specific available override
    sql_avail_override = "SELECT 1 FROM doctor_availability_overrides WHERE doctor_id = %s AND override_date = %s AND is_unavailable = FALSE AND (%s >= start_time AND %s <= end_time) LIMIT 1"
    cursor.execute(sql_avail_override, (doctor_id, appt_date, start_time, end_time))
    if cursor.fetchone(): return True
    # Check general availability
    sql_general_avail = "SELECT 1 FROM doctor_availability WHERE doctor_id = %s AND day_of_week = %s AND is_available = TRUE AND (%s >= start_time AND %s <= end_time) LIMIT 1"
    cursor.execute(sql_general_avail, (doctor_id, schema_day_of_week, start_time, end_time))
    if cursor.fetchone(): return True
    return False

def get_paginated_appointments(provider_user_id_int, page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
    """Fetches paginated appointments for a specific provider (expects INT ID)."""
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    if sort_by == 'date': sort_column_sql = "a.appointment_date, a.start_time"
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        sql_select = """ SELECT SQL_CALC_FOUND_ROWS a.*, p.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name, d.user_id as doctor_user_id, d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name """
        sql_from = """ FROM appointments a JOIN users p_user ON a.patient_id = p_user.user_id JOIN patients p ON a.patient_id = p.user_id JOIN users d_user ON a.doctor_id = d_user.user_id JOIN doctors d ON a.doctor_id = d.user_id """
        sql_where = " WHERE a.doctor_id = %s"
        params = [provider_user_id_int] # Use the passed integer ID
        # Apply filters (Date Range, Search, Status, Type)
        start_date = valid_filters.get('start_date'); end_date = valid_filters.get('end_date')
        if start_date: sql_where += " AND a.appointment_date >= %s"; params.append(start_date)
        if end_date: sql_where += " AND a.appointment_date <= %s"; params.append(end_date)
        if search_term: search_like = f"%{search_term}%"; sql_where += " AND (p_user.first_name LIKE %s OR p_user.last_name LIKE %s OR a.reason LIKE %s)"; params.extend([search_like, search_like, search_like])
        statuses = valid_filters.get('status')
        if statuses and isinstance(statuses, list) and len(statuses) > 0: placeholders = ','.join(['%s'] * len(statuses)); sql_where += f" AND a.status IN ({placeholders})"; params.extend(statuses)
        app_type = valid_filters.get('appointment_type')
        if app_type: sql_where += " AND a.appointment_type = %s"; params.append(app_type)
        # Execute query
        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching paginated appointments: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

# Expects provider_user_id_int as integer
def get_appointment_details(appointment_id, provider_user_id_int):
    """Fetches full details of a specific appointment, checking provider access (expects INT ID)."""
    conn = None; cursor = None; details = None
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        sql = """ SELECT a.*, p.user_id as patient_user_id, p.date_of_birth, p.gender, p.insurance_policy_number, p.insurance_group_number, p.insurance_expiration, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name, p_user.email as patient_email, p_user.phone as patient_phone, d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name, d.specialization as doctor_specialization, ip.provider_name as insurance_provider_name
                  FROM appointments a JOIN users p_user ON a.patient_id = p_user.user_id JOIN patients p ON a.patient_id = p.user_id JOIN users d_user ON a.doctor_id = d_user.user_id JOIN doctors d ON a.doctor_id = d.user_id LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
                  WHERE a.appointment_id = %s AND a.doctor_id = %s """
        cursor.execute(sql, (appointment_id, provider_user_id_int)) # Use INT ID
        details = cursor.fetchone()
    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching appointment details for ID {appointment_id}: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

# --- Routes ---

@appointments_bp.route('/', methods=['GET'])
@login_required
def list_appointments():
    if not check_provider_authorization(current_user):
        flash("Access denied. Provider role required.", "danger"); return redirect(url_for('doctor_main.dashboard'))

    # Safely get provider ID as integer
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Error accessing your user data. Please contact support.", "danger")
        return redirect(url_for('auth.logout')) # Log out if ID is invalid

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    view_mode = request.args.get('view', 'upcoming')
    start_date, end_date = None, None; today = date.today()
    try:
        if view_mode == 'today': start_date, end_date = today, today
        elif view_mode == 'week': start_date, end_date = today - timedelta(days=(today.weekday() + 1) % 7), today + timedelta(days=6 - ((today.weekday() + 1) % 7))
        elif view_mode == 'month': start_date, end_date = today.replace(day=1), (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        elif view_mode == 'upcoming': start_date = today
        elif view_mode == 'past': end_date = today - timedelta(days=1)
        elif view_mode == 'custom':
            if start_date_str: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else: start_date, view_mode = today, 'upcoming'
        if start_date and end_date and end_date < start_date: raise ValueError("End date cannot be before start date")
    except ValueError as e:
        flash(f"Invalid date range provided ({e}). Showing upcoming.", "warning"); start_date, end_date, view_mode = today, None, 'upcoming'; start_date_str, end_date_str = '', ''
    filter_statuses = request.args.getlist('status'); filter_type = request.args.get('appointment_type', '')
    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION
    filters = {'start_date': start_date, 'end_date': end_date, 'status': filter_statuses, 'appointment_type': filter_type}

    result = get_paginated_appointments( # Pass the integer ID
        provider_user_id_int=provider_user_id,
        page=page, per_page=ITEMS_PER_PAGE, search_term=search_term,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters
    )

    appointment_types = get_enum_values('appointments', 'appointment_type'); appointment_statuses = get_enum_values('appointments', 'status')
    total_items = result['total']; total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    return render_template(
        'Doctor_Portal/Appointments/appointment_list.html',
        appointments=result['items'], total_items=total_items, total_pages=total_pages, search_term=search_term,
        current_page=page, sort_by=sort_by, sort_dir=sort_dir, filters=filters, filter_statuses=filter_statuses,
        filter_type=filter_type, start_date_str=start_date_str, end_date_str=end_date_str, view_mode=view_mode,
        appointment_types=appointment_types, appointment_statuses=appointment_statuses, valid_sort_columns=VALID_SORT_COLUMNS
    )

@appointments_bp.route('/calendar', methods=['GET'])
@login_required
def calendar_view():
    """Displays the calendar view page."""
    if not check_provider_authorization(current_user):
        flash("Access denied. Provider role required.", "danger")
        return redirect(url_for('doctor_main.dashboard'))
    # You might pass configuration options or initial date to the template
    return render_template('Doctor_Portal/Appointments/calendar_view.html')
# --- End New Route ---

@appointments_bp.route('/<int:appointment_id>', methods=['GET'])
@login_required
def view_appointment(appointment_id):
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: flash("Error accessing user data.", "danger"); return redirect(url_for('auth.logout'))
    details = get_appointment_details(appointment_id, provider_user_id) # Pass INT ID
    if not details: flash("Appointment not found or access denied.", "warning"); return redirect(url_for('.list_appointments'))
    appointment_statuses = get_enum_values('appointments', 'status')
    return render_template('Doctor_Portal/Appointments/appointment_detail.html', appointment=details, appointment_statuses=appointment_statuses)

@appointments_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_appointment():
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: flash("Error accessing user data.", "danger"); return redirect(url_for('auth.logout'))

    appointment_types = get_enum_values('appointments', 'appointment_type')
    patients = get_all_simple('users', 'user_id', "CONCAT(last_name, ', ', first_name, ' (ID:', user_id, ')')", where_clause="user_type='patient' AND account_status='active'", order_by="last_name, first_name")
    doctors = [{'user_id': provider_user_id, 'name': f"Dr. {current_user.last_name}, {current_user.first_name}"}]

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        form_data = request.form.to_dict()
        try:
            patient_id = request.form.get('patient_id', type=int)
            doctor_id = provider_user_id # Use the fetched integer ID
            appt_date_str = request.form.get('appointment_date')
            start_time_str = request.form.get('start_time')
            appointment_type = request.form.get('appointment_type')
            reason = request.form.get('reason', '').strip() or None
            notes = request.form.get('notes', '').strip() or None
            # --- Validation ---
            if not patient_id: errors.append("Patient is required.")
            if not doctor_id: errors.append("Doctor is required.")
            if not appointment_type or appointment_type not in appointment_types: errors.append("Valid Appointment Type is required.")
            appt_date = None; start_time = None; end_time = None
            if not appt_date_str: errors.append("Appointment Date is required.")
            else: 
                try: appt_date = datetime.strptime(appt_date_str, '%Y-%m-%d').date(); 
                except ValueError: errors.append("Invalid Date format.")
            if not start_time_str: errors.append("Start Time is required.")
            else: 
                try: start_time = datetime.strptime(start_time_str, '%H:%M').time(); 
                except ValueError: errors.append("Invalid Time format.")
            if appt_date and start_time:
                 duration_minutes = get_appointment_duration(appointment_type); start_dt = datetime.combine(appt_date, start_time); end_dt = start_dt + timedelta(minutes=duration_minutes); end_time = end_dt.time()
                 if start_dt < datetime.now() - timedelta(minutes=5): errors.append("Cannot book appointments in the past.")
            if errors: raise ValueError("Validation Failed")
            # --- Availability Check ---
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor()
            if not is_slot_available(cursor, doctor_id, appt_date, start_time, end_time): errors.append(f"Slot unavailable."); raise ValueError("Availability Check Failed")
            # --- Database Insert ---
            sql = "INSERT INTO appointments (patient_id, doctor_id, appointment_date, start_time, end_time, appointment_type, status, reason, notes, created_by, updated_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            params = (patient_id, doctor_id, appt_date, start_time, end_time, appointment_type, 'confirmed', reason, notes, provider_user_id, provider_user_id)
            cursor.execute(sql, params); conn.commit()
            flash(f"Appointment created successfully.", "success")
            return redirect(url_for('.list_appointments', view='custom', start_date=appt_date_str, end_date=appt_date_str))
        except ValueError: [flash(err, 'danger') for err in errors]
        except mysql.connector.Error as err:
            if conn: conn.rollback(); current_app.logger.error(f"DB Error Creating Appointment: {err}"); flash(f"Database error: {err.msg}", "danger")
        except ConnectionError as ce: current_app.logger.error(f"DB Connection Error Creating Appt: {ce}"); flash("DB connection error.", "danger")
        except Exception as e:
            if conn: conn.rollback(); current_app.logger.error(f"Error Creating Appointment: {e}", exc_info=True); flash("Unexpected error.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        return render_template('Doctor_Portal/Appointments/create_appointment_form.html', form_data=form_data, patients=patients, doctors=doctors, appointment_types=appointment_types, errors=errors)
    return render_template('Doctor_Portal/Appointments/create_appointment_form.html', patients=patients, doctors=doctors, appointment_types=appointment_types)

@appointments_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: flash("Error accessing user data.", "danger"); return redirect(url_for('auth.logout'))
    conn = None; cursor = None; success = False
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, provider_user_id))
        appt = cursor.fetchone()
        if not appt: flash("Appointment not found or access denied.", "warning")
        elif appt['status'] in ('completed', 'canceled', 'no-show'): flash(f"Cannot cancel: Status is '{appt['status']}'.", "warning")
        else:
            sql_update = "UPDATE appointments SET status = 'canceled', updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
            cursor.execute(sql_update, (provider_user_id, appointment_id)); conn.commit()
            if cursor.rowcount > 0: flash("Appointment canceled.", "success"); success = True
            else: flash("Failed to cancel.", "danger")
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error canceling appt {appointment_id}: {e}", exc_info=True); flash("Error canceling.", "danger")
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()
    redirect_url = request.referrer or url_for('.list_appointments')
    if success and f'/appointments/{appointment_id}' in (request.referrer or ''): redirect_url = url_for('.list_appointments')
    return redirect(redirect_url)

@appointments_bp.route('/<int:appointment_id>/reschedule', methods=['GET', 'POST'])
@login_required
def reschedule_appointment(appointment_id):
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: flash("Error accessing user data.", "danger"); return redirect(url_for('auth.logout'))
    conn = None; cursor = None;
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection Failed")
        cursor = conn.cursor(dictionary=True)
        sql_fetch = "SELECT a.*, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name FROM appointments a JOIN users p_user ON a.patient_id = p_user.user_id WHERE a.appointment_id = %s AND a.doctor_id = %s"
        cursor.execute(sql_fetch, (appointment_id, provider_user_id))
        appointment = cursor.fetchone()
        if not appointment: flash("Appointment not found or access denied.", "warning"); return redirect(url_for('.list_appointments'))
        if appointment['status'] in ('completed', 'canceled', 'no-show'): flash(f"Cannot reschedule: Status is '{appointment['status']}'.", "warning"); return redirect(url_for('.view_appointment', appointment_id=appointment_id))
        appointment_types = get_enum_values('appointments', 'appointment_type')
        if request.method == 'POST':
            errors = []; form_data = request.form.to_dict()
            try:
                new_date_str = request.form.get('appointment_date'); new_time_str = request.form.get('start_time'); reason = request.form.get('reason', appointment['reason']).strip() or None; notes = request.form.get('notes', appointment['notes']).strip() or None
                new_date = None; new_start_time = None; new_end_time = None
                if not new_date_str: errors.append("New Date is required.")
                else: 
                    try: new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date(); 
                    except ValueError: errors.append("Invalid Date format.")
                if not new_time_str: errors.append("New Start Time is required.")
                else: 
                    try: new_start_time = datetime.strptime(new_time_str, '%H:%M').time(); 
                    except ValueError: errors.append("Invalid Time format.")
                if new_date and new_start_time:
                    duration_minutes = get_appointment_duration(appointment['appointment_type']); start_dt = datetime.combine(new_date, new_start_time); end_dt = start_dt + timedelta(minutes=duration_minutes); new_end_time = end_dt.time()
                    if start_dt < datetime.now() - timedelta(minutes=5): errors.append("Cannot reschedule to the past.")
                if errors: raise ValueError("Validation Failed")
                if not is_slot_available(cursor, provider_user_id, new_date, new_start_time, new_end_time, exclude_appointment_id=appointment_id): errors.append(f"Slot unavailable."); raise ValueError("Availability Check Failed")
                sql_update = "UPDATE appointments SET appointment_date=%s, start_time=%s, end_time=%s, status=%s, reason=%s, notes=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE appointment_id=%s AND doctor_id=%s"
                params = (new_date, new_start_time, new_end_time, 'confirmed', reason, notes, provider_user_id, appointment_id, provider_user_id)
                cursor.execute(sql_update, params); conn.commit()
                flash(f"Appointment rescheduled successfully.", "success")
                return redirect(url_for('.view_appointment', appointment_id=appointment_id))
            except ValueError: [flash(err, 'danger') for err in errors]
            except mysql.connector.Error as err:
                if conn: conn.rollback(); current_app.logger.error(f"DB Error Rescheduling Appt {appointment_id}: {err}"); flash(f"DB error: {err.msg}", "danger")
            except Exception as e:
                if conn: conn.rollback(); current_app.logger.error(f"Error Rescheduling Appt {appointment_id}: {e}", exc_info=True); flash("Unexpected error.", "danger")
            appointment.update(form_data) # Update dict with form data for re-render
            return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html', appointment=appointment, appointment_types=appointment_types, errors=errors)
        return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html', appointment=appointment, appointment_types=appointment_types)
    except ConnectionError as ce:
        current_app.logger.error(f"DB Connection Error (reschedule {appointment_id}): {ce}"); flash("Database connection error.", "danger"); return redirect(url_for('.list_appointments'))
    except Exception as e:
        current_app.logger.error(f"Error accessing reschedule page {appointment_id}: {e}", exc_info=True); flash("Unexpected error.", "danger"); return redirect(url_for('.list_appointments'))
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

@appointments_bp.route('/<int:appointment_id>/update_status', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Authorization required."), 403
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: return jsonify(success=False, message="Invalid user session."), 403
    new_status = request.json.get('status'); available_statuses = get_enum_values('appointments', 'status')
    if not new_status or new_status not in available_statuses: return jsonify(success=False, message="Invalid status."), 400
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        if not can_modify_appointment(cursor, appointment_id, provider_user_id): return jsonify(success=False, message="Access denied."), 403
        sql_update = "UPDATE appointments SET status = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
        cursor.execute(sql_update, (new_status, provider_user_id, appointment_id)); conn.commit()
        return jsonify(success=True, message=f"Status updated.", new_status=new_status)
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error updating status AJAX {appointment_id}: {e}", exc_info=True)
        return jsonify(success=False, message="Database error."), 500
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

@appointments_bp.route('/<int:appointment_id>/update_notes', methods=['POST'])
@login_required
def update_appointment_notes(appointment_id):
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Authorization required."), 403
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: return jsonify(success=False, message="Invalid user session."), 403
    new_notes = request.json.get('notes', '').strip() or None
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        if not can_modify_appointment(cursor, appointment_id, provider_user_id): return jsonify(success=False, message="Access denied."), 403
        sql_update = "UPDATE appointments SET notes = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
        cursor.execute(sql_update, (new_notes, provider_user_id, appointment_id)); conn.commit()
        return jsonify(success=True, message="Notes updated.")
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Error updating notes AJAX {appointment_id}: {e}", exc_info=True)
        return jsonify(success=False, message="Database error."), 500
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()

@appointments_bp.route('/feed', methods=['GET'])
@login_required
def appointment_data_feed():
    if not check_provider_authorization(current_user): 
        return jsonify([])
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None: 
        return jsonify({"error": "Invalid user session"}), 403 # Or appropriate error
    start_str = request.args.get('start'); end_str = request.args.get('end')
    if not start_str or not end_str: 
        return jsonify({"error": "Start/end dates required"}), 400
    try: start_date = datetime.fromisoformat(start_str.split('T')[0]).date(); end_date = datetime.fromisoformat(end_str.split('T')[0]).date()
    except ValueError: 
        return jsonify({"error": "Invalid date format"}), 400
    conn = None; cursor = None; events = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql = """SELECT a.appointment_id id, CONCAT(p_user.last_name, ', ', p_user.first_name) title, CONCAT(a.appointment_date, 'T', a.start_time) start, CONCAT(a.appointment_date, 'T', a.end_time) end, a.status, a.appointment_type FROM appointments a JOIN users p_user ON a.patient_id = p_user.user_id WHERE a.doctor_id = %s AND a.appointment_date >= %s AND a.appointment_date < %s AND a.status NOT IN ('canceled')"""
        cursor.execute(sql, (provider_user_id, start_date, end_date))
        appointments = cursor.fetchall()
        status_colors = { 'scheduled': '#0d6efd', 'confirmed': '#198754', 'completed': '#6c757d', 'no-show': '#ffc107', 'rescheduled': '#fd7e14', 'canceled': '#dc3545' }
        for appt in appointments: events.append({ 'id': appt['id'], 'title': f"{appt['title']} ({appt['appointment_type']})", 'start': appt['start'], 'end': appt['end'], 'color': status_colors.get(appt['status'], '#6c757d'), 'url': url_for('.view_appointment', appointment_id=appt['id']), 'status': appt['status'], 'type': appt['appointment_type'], })
        return jsonify(events)
    except Exception as e:
        current_app.logger.error(f"Error generating appointment feed: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve data"}), 500
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()