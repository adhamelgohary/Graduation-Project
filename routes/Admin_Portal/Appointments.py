import datetime
import math
import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app, abort, jsonify
)
from flask_login import login_required, current_user
from db import get_db_connection # Assuming db.py has get_db_connection()
from functools import wraps # Import wraps here

# Define the Blueprint for Admin Appointment Management
admin_appointments_bp = Blueprint(
    'admin_appointments',
    __name__,
    template_folder='../templates/Admin_Portal/',
    url_prefix='/admin/appointments'
)

# --- Constants ---
# These might become less relevant if fetched dynamically, but useful as fallbacks
# APPOINTMENT_TYPES = ['initial', 'follow-up', 'consultation', 'urgent', 'routine', 'telehealth', 'procedure'] # Replaced by DB fetch
APPOINTMENT_STATUSES = ['scheduled', 'confirmed', 'completed', 'canceled', 'no-show', 'rescheduled', 'checked-in', 'pending'] # Keep for validation for now
# DEFAULT_APPOINTMENT_STATUS = 'scheduled' # Replaced by setting fetch


# --- Helper Functions ---

def is_admin():
    """Checks if the current logged-in user is an admin."""
    return (current_user and
            hasattr(current_user, 'is_authenticated') and
            current_user.is_authenticated and
            hasattr(current_user, 'user_type') and
            current_user.user_type == "admin")

def require_admin(func):
    """Decorator to protect routes that require admin privileges."""
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not is_admin():
            flash("Access denied. Administrator privileges required.", "danger")
            return redirect(url_for('login.login_route', next=request.url))
        return func(*args, **kwargs)
    return decorated_view

# --- NEW: Settings Helpers ---
def get_setting(key, default=None):
    """Fetches a setting value from the settings table."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return default
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT setting_value FROM settings WHERE setting_key = %s", (key,))
        result = cursor.fetchone()
        return result['setting_value'] if result else default
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error getting setting '{key}': {err}")
        return default
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_bool_setting(key, default=False):
    """Fetches a setting and converts it to boolean."""
    value = get_setting(key, 'false' if not default else 'true')
    return value.lower() == 'true'

def get_int_setting(key, default=0):
    """Fetches a setting and converts it to integer."""
    value = get_setting(key, str(default))
    try:
        return int(value)
    except (ValueError, TypeError):
        current_app.logger.warning(f"Setting '{key}' has non-integer value '{value}'. Using default {default}.")
        return default

def set_setting(key, value, description=None):
    """Saves a setting value to the settings table."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "danger")
            return False
        cursor = conn.cursor()
        # Use INSERT...ON DUPLICATE KEY UPDATE for simplicity
        if description:
            sql = """
                INSERT INTO settings (setting_key, setting_value, description)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), description = VALUES(description)
            """
            params = (key, str(value), description)
        else:
             sql = """
                INSERT INTO settings (setting_key, setting_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
            """
             params = (key, str(value))
        cursor.execute(sql, params)
        conn.commit()
        return True
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error setting setting '{key}': {err}")
        flash(f"Database error saving setting '{key}': {err}", "danger")
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
# --- END: Settings Helpers ---

def get_appointment_statuses(active_only=True):
    """Fetches appointment statuses from the database."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        query = "SELECT status_id, status_name, description, is_active, sort_order FROM appointment_statuses"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY sort_order, status_name" # Use sort_order
        cursor.execute(query)
        statuses = cursor.fetchall()
        return statuses if statuses else []
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error getting appointment statuses: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
# --- END: Appointment Status Helper ---

# --- NEW: Appointment Type Helper ---
def get_appointment_types(active_only=True):
    """Fetches appointment types from the database."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        query = "SELECT type_id, type_name, default_duration_minutes, description, is_active FROM appointment_types"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY type_name"
        cursor.execute(query)
        types = cursor.fetchall()
        return types if types else []
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error getting appointment types: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
# --- END: Appointment Type Helper ---


def get_appointment_or_404(appointment_id):
    """Fetches a single appointment with patient/doctor names or returns a 404."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
             abort(500, description="Database connection failed")
        cursor = conn.cursor(dictionary=True)
        # Added new columns from appointments table
        query = """
            SELECT a.*,
                   CONCAT(up.first_name, ' ', up.last_name) AS patient_name,
                   up.email AS patient_email,
                   CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name,
                   ud.email AS doctor_email
            FROM appointments a
            LEFT JOIN users up ON a.patient_id = up.user_id
            LEFT JOIN users ud ON a.doctor_id = ud.user_id
            WHERE a.appointment_id = %s
        """
        cursor.execute(query, (appointment_id,))
        appointment = cursor.fetchone()

        if appointment is None:
            abort(404, description=f"Appointment with ID {appointment_id} not found.")

        # Convert DB types to Python types (Dates, Times, Timestamps)
        for field in ['appointment_date']:
             if appointment.get(field) and not isinstance(appointment[field], datetime.date):
                 try: appointment[field] = datetime.datetime.strptime(str(appointment[field]), '%Y-%m-%d').date()
                 except ValueError: appointment[field] = None
        for field in ['start_time', 'end_time']:
             if appointment.get(field) and not isinstance(appointment[field], datetime.time):
                 try:
                     if isinstance(appointment[field], datetime.timedelta): # Handle timedelta
                         total_seconds = int(appointment[field].total_seconds())
                         h, rem = divmod(total_seconds, 3600)
                         m, s = divmod(rem, 60)
                         appointment[field] = datetime.time(h % 24, m, s) # Use modulo 24 for hours
                     else:
                         appointment[field] = datetime.datetime.strptime(str(appointment[field]), '%H:%M:%S').time()
                 except (ValueError, TypeError): appointment[field] = None
        for field in ['check_in_time', 'start_treatment_time', 'end_treatment_time', 'created_at', 'updated_at']:
             if appointment.get(field) and not isinstance(appointment[field], datetime.datetime):
                 try:
                     # Adjust format string if your DB returns timezone info or different precision
                     appointment[field] = datetime.datetime.strptime(str(appointment[field]), '%Y-%m-%d %H:%M:%S')
                 except (ValueError, TypeError):
                     try: # Try without seconds
                         appointment[field] = datetime.datetime.strptime(str(appointment[field]), '%Y-%m-%d %H:%M')
                     except (ValueError, TypeError):
                          current_app.logger.warning(f"Invalid timestamp format for {field} in appointment {appointment_id}")
                          appointment[field] = None

        return appointment
    except mysql.connector.Error as err:
        current_app.logger.error(f"Database error fetching appointment {appointment_id}: {err}")
        abort(500, description="Database error while fetching appointment details.")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def get_all_active_users_by_type(user_type):
    """Fetches active users (ID and name) of a specific type for dropdowns."""
    if user_type not in ['doctor', 'patient']:
        current_app.logger.error(f"Invalid user_type '{user_type}' requested")
        return []
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT u.user_id, CONCAT(u.first_name, ' ', u.last_name) as full_name
            FROM users u
            WHERE u.user_type = %s AND u.account_status = 'active'
            ORDER BY u.last_name, u.first_name
        """
        cursor.execute(query, (user_type,))
        users = cursor.fetchall()
        return users if users else []
    except mysql.connector.Error as err:
        current_app.logger.error(f"Database error fetching active {user_type}s: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

get_all_doctors = lambda: get_all_active_users_by_type('doctor')
get_all_patients = lambda: get_all_active_users_by_type('patient')


def check_appointment_conflict(doctor_user_id, appointment_date, start_time, end_time, exclude_appointment_id=None):
    """Checks for conflicts, considering the allow_double_booking setting."""
    # --- Check Setting First ---
    allow_double_booking = get_bool_setting('allow_double_booking', default=False)
    if allow_double_booking:
        current_app.logger.info(f"Double booking allowed by setting. Skipping conflict check for doctor {doctor_user_id}.")
        return False # No conflict if double booking is allowed globally

    # Input validation
    if not all([
        isinstance(doctor_user_id, int),
        isinstance(appointment_date, datetime.date),
        isinstance(start_time, datetime.time),
        isinstance(end_time, datetime.time)
    ]):
        current_app.logger.error("Invalid type passed to check_appointment_conflict")
        return True # Assume conflict on bad input

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return True
        cursor = conn.cursor(dictionary=True)

        # Statuses considered "blocking" - adjust as needed
        blocking_statuses = ('scheduled', 'confirmed', 'checked-in', 'pending', 'rescheduled')

        query = """
            SELECT appointment_id
            FROM appointments
            WHERE doctor_id = %s
              AND appointment_date = %s
              AND status IN ({}) -- Placeholder for statuses
              AND ( (%s < end_time) AND (%s > start_time) ) -- Overlap condition
        """.format(','.join(['%s'] * len(blocking_statuses))) # Dynamic status placeholders

        params = [doctor_user_id, appointment_date]
        params.extend(blocking_statuses)
        params.extend([start_time.strftime('%H:%M:%S'), end_time.strftime('%H:%M:%S')])

        if exclude_appointment_id is not None:
            query += " AND appointment_id != %s"
            params.append(exclude_appointment_id)

        cursor.execute(query, tuple(params))
        conflict = cursor.fetchone()
        if conflict:
             current_app.logger.warning(f"Conflict detected for doctor {doctor_user_id} on {appointment_date} at {start_time}-{end_time}. Conflicting ID: {conflict['appointment_id']}")
        return conflict is not None

    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error checking conflict for doctor {doctor_user_id}: {err}")
        return True # Assume conflict on DB error
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- NEW: Follow-up Helper ---
def create_followup_task(appointment_id, reason="Missed Appointment"):
    """Creates a pending follow-up task for an appointment."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: return False
        cursor = conn.cursor()
        # Check if a pending followup already exists for this appointment
        cursor.execute("""
            SELECT followup_id FROM appointment_followups
            WHERE appointment_id = %s AND followup_status = 'pending'
        """, (appointment_id,))
        if cursor.fetchone():
             current_app.logger.info(f"Pending followup already exists for appointment {appointment_id}. Skipping creation.")
             return True # Or False depending on desired behavior

        sql = """
            INSERT INTO appointment_followups (appointment_id, notes)
            VALUES (%s, %s)
        """
        cursor.execute(sql, (appointment_id, f"Automated follow-up required: {reason}"))
        conn.commit()
        current_app.logger.info(f"Created follow-up task for appointment {appointment_id}")
        return True
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error creating follow-up for appointment {appointment_id}: {err}")
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- Routes ---

@admin_appointments_bp.route('/', methods=['GET'])
@require_admin
def list_appointments():
    """View all scheduled appointments across the system with filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ADMIN_ITEMS_PER_PAGE', 15)
    offset = (page - 1) * per_page

    # Filters (keep existing)
    search_term = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    doctor_filter = request.args.get('doctor_id', type=int)
    patient_filter = request.args.get('patient_id', type=int)
    date_from_filter = request.args.get('date_from', '').strip()
    date_to_filter = request.args.get('date_to', '').strip()
    type_filter = request.args.get('type', '').strip()
    status_filter = request.args.get('status', '').strip() # Keep status filter

    conn = None
    cursor = None
    appointment_statuses_list = get_appointment_statuses(active_only=False) # Get all for filter
    valid_status_names = [s['status_name'] for s in appointment_statuses_list] # Get valid names
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "danger")
            return render_template('Admin_Portal/appointments/list.html', appointments=[], total_pages=0, current_page=1, doctors=[], patients=[], statuses=APPOINTMENT_STATUSES, types=[])

        cursor = conn.cursor(dictionary=True)
        base_query = """
            SELECT SQL_CALC_FOUND_ROWS
                   a.*,
                   CONCAT(up.first_name, ' ', up.last_name) AS patient_name,
                   CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name
            FROM appointments a
            LEFT JOIN users up ON a.patient_id = up.user_id
            LEFT JOIN users ud ON a.doctor_id = ud.user_id
            WHERE 1=1
        """
        params = []

        # Apply filters (existing + new type filter)
        if search_term:
            base_query += " AND (CONCAT(up.first_name, ' ', up.last_name) LIKE %s OR CONCAT(ud.first_name, ' ', ud.last_name) LIKE %s OR a.reason LIKE %s OR a.notes LIKE %s)"
            term_like = f"%{search_term}%"
            params.extend([term_like, term_like, term_like, term_like])
        if status_filter and status_filter in valid_status_names: # Validate against fetched statuses
            base_query += " AND a.status = %s"
            params.append(status_filter)
        if doctor_filter:
            base_query += " AND a.doctor_id = %s"
            params.append(doctor_filter)
        if patient_filter:
            base_query += " AND a.patient_id = %s"
            params.append(patient_filter)
        if date_from_filter:
            try: datetime.datetime.strptime(date_from_filter, '%Y-%m-%d'); base_query += " AND a.appointment_date >= %s"; params.append(date_from_filter)
            except ValueError: flash("Invalid 'Date From'. Use YYYY-MM-DD.", "warning")
        if date_to_filter:
            try: datetime.datetime.strptime(date_to_filter, '%Y-%m-%d'); base_query += " AND a.appointment_date <= %s"; params.append(date_to_filter)
            except ValueError: flash("Invalid 'Date To'. Use YYYY-MM-DD.", "warning")
        if type_filter:
             base_query += " AND a.appointment_type = %s"
             params.append(type_filter)

        # Ordering and Pagination
        base_query += " ORDER BY a.appointment_date DESC, a.start_time ASC LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(base_query, tuple(params))
        appointments_raw = cursor.fetchall()

        # Convert types after fetching
        appointments = []
        for appt in appointments_raw:
             # Reuse logic from get_appointment_or_404 for type conversion
            for field in ['appointment_date']:
                 if appt.get(field) and not isinstance(appt[field], datetime.date):
                     try: appt[field] = datetime.datetime.strptime(str(appt[field]), '%Y-%m-%d').date()
                     except ValueError: appt[field] = None
            for field in ['start_time', 'end_time']:
                 if appt.get(field) and not isinstance(appt[field], datetime.time):
                     try:
                         if isinstance(appt[field], datetime.timedelta):
                             total_seconds = int(appt[field].total_seconds())
                             h, rem = divmod(total_seconds, 3600); m, s = divmod(rem, 60)
                             appt[field] = datetime.time(h % 24, m, s)
                         else: appt[field] = datetime.datetime.strptime(str(appt[field]), '%H:%M:%S').time()
                     except (ValueError, TypeError): appt[field] = None
            appointments.append(appt)


        cursor.execute("SELECT FOUND_ROWS() as total")
        total_items = cursor.fetchone()['total']
        total_pages = math.ceil(total_items / per_page)

        # Fetch dynamic data for filters
        doctors = get_all_doctors()
        patients = get_all_patients()
        appointment_types_list = get_appointment_types(active_only=True) # Fetch from DB

        return render_template(
            'Admin_Portal/appointments/list.html',
            appointments=appointments,
            current_page=page,
            total_pages=total_pages,
            total_items=total_items,
            doctors=doctors,
            patients=patients,
            statuses=appointment_statuses_list, # Pass dynamic statuses
            types=appointment_types_list,
            type_filter=type_filter,
            # Pass filter values back
            search_term=search_term, status_filter=status_filter,
            doctor_filter=doctor_filter, patient_filter=patient_filter,
            date_from_filter=date_from_filter, date_to_filter=date_to_filter,
        )

    except mysql.connector.Error as err:
        current_app.logger.error(f"Database error listing appointments: {err}")
        flash("Error retrieving appointments list.", "danger")
        # Pass empty lists/defaults on error
        return render_template('Admin_Portal/appointments/list.html', appointments=[], total_pages=0, current_page=1, doctors=[], patients=[], statuses=APPOINTMENT_STATUSES, types=[])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@admin_appointments_bp.route('/<int:appointment_id>/edit', methods=['GET', 'POST'])
@require_admin
def edit_appointment(appointment_id):
    """Modify appointments, including status and check rescheduling rules."""
    appointment = get_appointment_or_404(appointment_id)
    reschedule_limit = get_int_setting('reschedule_limit', 3)
    min_notice_hours = get_int_setting('min_reschedule_notice_hours', 24) # Get notice period setting
    dynamic_appointment_types = get_appointment_types(active_only=True)
    dynamic_appointment_statuses = get_appointment_statuses(active_only=True) # Fetch statuses for dropdown
    valid_status_names = [s['status_name'] for s in dynamic_appointment_statuses]


    if request.method == 'POST':
        conn = None
        cursor = None
        try:
            # Collect form data (keep existing)
            patient_user_id = request.form.get('patient_id', type=int)
            doctor_user_id = request.form.get('doctor_id', type=int)
            appointment_date_str = request.form.get('appointment_date')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            appointment_type = request.form.get('appointment_type') # Name string
            status = request.form.get('status')
            reason = request.form.get('reason', '').strip()
            notes = request.form.get('notes', '').strip()
            override_restrictions = 'override_restrictions' in request.form
            status = request.form.get('status')


            # --- Validation (similar to add, but check against original appointment) ---
            errors = {}
            appointment_date, start_time, end_time = None, None, None

            # Type validation (use fetched types)
            valid_type_names = [t['type_name'] for t in dynamic_appointment_types]
            if appointment_type not in valid_type_names:
                errors['appointment_type'] = "Invalid appointment type selected."

            if status not in APPOINTMENT_STATUSES: errors['status'] = "Invalid status selected."

            # Date/Time validation (same as add)
            if not patient_user_id: errors['patient_id'] = "Patient selection is required."
            if not doctor_user_id: errors['doctor_id'] = "Doctor selection is required."
            if not appointment_date_str: errors['appointment_date'] = "Date required."
            else:
                 try: appointment_date = datetime.datetime.strptime(appointment_date_str, '%Y-%m-%d').date()
                 except ValueError: errors['appointment_date'] = "Invalid date (YYYY-MM-DD)."
            if not start_time_str: errors['start_time'] = "Start time required."
            else:
                 try: start_time = datetime.datetime.strptime(start_time_str.split(':')[0]+':'+start_time_str.split(':')[1], '%H:%M').time()
                 except (ValueError, IndexError): errors['start_time'] = "Invalid time (HH:MM)."
            if not end_time_str: errors['end_time'] = "End time required."
            else:
                 try: end_time = datetime.datetime.strptime(end_time_str.split(':')[0]+':'+end_time_str.split(':')[1], '%H:%M').time()
                 except (ValueError, IndexError): errors['end_time'] = "Invalid time (HH:MM)."

            if start_time and end_time and start_time >= end_time: errors['end_time'] = "End time must be after start time."

            # --- Check Rescheduling Rules ---
            is_rescheduling = False
            if appointment_date and start_time: # Check if date or time changed significantly
                original_date = appointment.get('appointment_date')
                original_start_time = appointment.get('start_time')
                if original_date != appointment_date or original_start_time != start_time:
                    is_rescheduling = True
            if status == 'rescheduled' and appointment.get('status') != 'rescheduled':
                is_rescheduling = True # Explicit status change counts

            if is_rescheduling and not override_restrictions:
                 current_reschedule_count = appointment.get('reschedule_count', 0)
                 if current_reschedule_count >= reschedule_limit:
                     errors['reschedule'] = f"Reschedule limit ({reschedule_limit}) reached. Use override if necessary."
                 # Optional: Check min notice period (more complex, involves comparing old date/time with now)
                 # min_notice_hours = get_int_setting('min_reschedule_notice_hours', 24)
                 # if min_notice_hours > 0 and original_date and original_start_time:
                 #    original_datetime = datetime.datetime.combine(original_date, original_start_time)
                 #    if datetime.datetime.now() > original_datetime - datetime.timedelta(hours=min_notice_hours):
                 #         errors['reschedule_notice'] = f"Cannot reschedule less than {min_notice_hours} hours before appointment."

            # --- Check Conflict ---
            if not errors.get('reschedule') and not errors.get('reschedule_notice'): # Don't check conflict if reschedule failed
                 if not errors and appointment_date and start_time and end_time and not override_restrictions:
                      if check_appointment_conflict(doctor_user_id, appointment_date, start_time, end_time, exclude_appointment_id=appointment_id):
                         errors['conflict'] = "Time slot conflict detected. Check schedule or use override."
            

            # --- End Validation ---

            if errors:
                for field, msg in errors.items(): flash(f"{msg}", "danger")
                form_data = {**appointment, **request.form.to_dict()}
                return render_template(
                    'Admin_Portal/appointments/edit.html',
                    appointment=form_data,
                    appointment_types=dynamic_appointment_types, # Pass dynamic types
                    appointment_statuses=APPOINTMENT_STATUSES,
                    patients=get_all_patients(), doctors=get_all_doctors(),
                    reschedule_limit=reschedule_limit, # Pass limit info
                    errors=errors
                )

            # --- Proceed with Update ---
            conn = get_db_connection()
            if not conn: raise mysql.connector.Error("Database connection failed")
            cursor = conn.cursor()

            # Calculate reschedule count increment
            reschedule_increment = 1 if is_rescheduling else 0

            # Update Check-in/Treatment times based on status change (basic implementation)
            now_dt = datetime.datetime.now()
            check_in_time_sql = appointment.get('check_in_time') # Keep existing if not changing status
            start_treatment_time_sql = appointment.get('start_treatment_time')
            end_treatment_time_sql = appointment.get('end_treatment_time')

            if status == 'checked-in' and appointment.get('status') != 'checked-in':
                check_in_time_sql = now_dt
            # Example: Clear check-in if status goes back from checked-in? (Policy dependent)
            elif status != 'checked-in' and appointment.get('status') == 'checked-in':
                 check_in_time_sql = None # Or keep history? Policy decision.

            # Status 'completed' might imply end_treatment_time
            if status == 'completed' and appointment.get('status') != 'completed':
                end_treatment_time_sql = now_dt
                # Maybe set start_treatment_time too if not already set?
                if not start_treatment_time_sql and check_in_time_sql:
                    start_treatment_time_sql = check_in_time_sql # Default start = checkin if completed directly

            sql = """
                UPDATE appointments SET
                    patient_id = %s, doctor_id = %s, appointment_date = %s,
                    start_time = %s, end_time = %s, appointment_type = %s, status = %s,
                    reason = %s, notes = %s,
                    reschedule_count = reschedule_count + %s, -- Increment count
                    check_in_time = %s, -- Update timestamp based on status logic
                    start_treatment_time = %s,
                    end_treatment_time = %s,
                    updated_by = %s, updated_at = CURRENT_TIMESTAMP
                WHERE appointment_id = %s
            """
            params = (
                patient_user_id, doctor_user_id, appointment_date,
                start_time.strftime('%H:%M:%S'), end_time.strftime('%H:%M:%S'),
                appointment_type, status, reason, notes,
                reschedule_increment, # Increment value
                check_in_time_sql,
                start_treatment_time_sql,
                end_treatment_time_sql,
                current_user.id,
                appointment_id
            )
            cursor.execute(sql, params)

            # --- Trigger Follow-up for No-Show ---
            if status == 'no-show' and appointment.get('status') != 'no-show':
                 create_followup_task(appointment_id, reason="No-Show")

            conn.commit()
            flash(f"Appointment #{appointment_id} updated successfully.", "success")
            if override_restrictions: flash("Scheduling restrictions were overridden.", "info")
            if is_rescheduling and reschedule_increment > 0: flash(f"Reschedule count updated to {current_reschedule_count + 1}.", "info")

            return redirect(url_for('.list_appointments'))

        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error updating appointment {appointment_id}: {err}")
            flash(f"Database error updating appointment: {err}", "danger")
        except Exception as e:
             current_app.logger.error(f"Unexpected error updating appointment {appointment_id}: {e}", exc_info=True)
             flash("An unexpected error occurred while updating.", "danger")
             if conn: conn.rollback()
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

        # Fallback render on error
        form_data = {**appointment, **request.form.to_dict()}
        return render_template(
            'Admin_Portal/appointments/edit.html',
            appointment=form_data,
            appointment_types=dynamic_appointment_types,
            appointment_statuses=APPOINTMENT_STATUSES,
            patients=get_all_patients(), doctors=get_all_doctors(),
            reschedule_limit=reschedule_limit,
            errors=errors if 'errors' in locals() else {'general': 'An error occurred.'}
        )

    # --- GET Request ---
    # Prepare data for the form, including formatting
    if appointment.get('appointment_date'): appointment['appointment_date_str'] = appointment['appointment_date'].strftime('%Y-%m-%d')
    if appointment.get('start_time'): appointment['start_time_str'] = appointment['start_time'].strftime('%H:%M')
    if appointment.get('end_time'): appointment['end_time_str'] = appointment['end_time'].strftime('%H:%M')
    # Add timestamps for display if they exist
    if appointment.get('check_in_time'): appointment['check_in_time_str'] = appointment['check_in_time'].strftime('%Y-%m-%d %H:%M')
    if appointment.get('start_treatment_time'): appointment['start_treatment_time_str'] = appointment['start_treatment_time'].strftime('%Y-%m-%d %H:%M')
    if appointment.get('end_treatment_time'): appointment['end_treatment_time_str'] = appointment['end_treatment_time'].strftime('%Y-%m-%d %H:%M')


    return render_template(
        'Admin_Portal/appointments/edit.html',
        appointment=appointment,
        appointment_types=dynamic_appointment_types, # Use dynamic types
        appointment_statuses=APPOINTMENT_STATUSES,
        patients=get_all_patients(), doctors=get_all_doctors(),
        reschedule_limit=reschedule_limit, # Pass limit for display/info
        errors={}
    )

# ... (add_appointment route needs similar updates to use dynamic types and check rules) ...
@admin_appointments_bp.route('/add', methods=['GET', 'POST'])
@require_admin
def add_appointment():
    """Allow Admins to create new appointments, using settings and dynamic types."""
    dynamic_appointment_types = get_appointment_types(active_only=True)
    default_status = get_setting('default_appointment_status', 'scheduled')

    if request.method == 'POST':
        conn = None
        cursor = None
        try:
            # Collect form data
            patient_user_id = request.form.get('patient_id', type=int)
            doctor_user_id = request.form.get('doctor_id', type=int)
            appointment_date_str = request.form.get('appointment_date')
            start_time_str = request.form.get('start_time')
            end_time_str = request.form.get('end_time')
            appointment_type = request.form.get('appointment_type') # Name string
            status = request.form.get('status', default_status) # Use fetched default
            reason = request.form.get('reason', '').strip()
            notes = request.form.get('notes', '').strip()
            override_restrictions = 'override_restrictions' in request.form

            # --- Validation ---
            errors = {}
            appointment_date, start_time, end_time = None, None, None

            valid_type_names = [t['type_name'] for t in dynamic_appointment_types]
            if appointment_type not in valid_type_names: errors['appointment_type'] = "Invalid appointment type selected."

            if status not in APPOINTMENT_STATUSES: errors['status'] = "Invalid status selected." # Basic check

            # Date/Time validation (same as before)
            if not patient_user_id: errors['patient_id'] = "Patient required."
            if not doctor_user_id: errors['doctor_id'] = "Doctor required."
            if not appointment_date_str: errors['appointment_date'] = "Date required."
            else:
                 try:
                     appointment_date = datetime.datetime.strptime(appointment_date_str, '%Y-%m-%d').date()
                     if appointment_date < datetime.date.today() and not override_restrictions:
                          errors['appointment_date'] = "Cannot schedule in the past (use override)."
                 except ValueError: errors['appointment_date'] = "Invalid date (YYYY-MM-DD)."
            if not start_time_str: errors['start_time'] = "Start time required."
            else:
                 try: start_time = datetime.datetime.strptime(start_time_str.split(':')[0]+':'+start_time_str.split(':')[1], '%H:%M').time()
                 except (ValueError, IndexError): errors['start_time'] = "Invalid time (HH:MM)."
            if not end_time_str: errors['end_time'] = "End time required."
            else:
                 try: end_time = datetime.datetime.strptime(end_time_str.split(':')[0]+':'+end_time_str.split(':')[1], '%H:%M').time()
                 except (ValueError, IndexError): errors['end_time'] = "Invalid time (HH:MM)."

            if start_time and end_time and start_time >= end_time: errors['end_time'] = "End time must be after start time."

            # Check conflict
            if not errors and appointment_date and start_time and end_time and not override_restrictions:
                if check_appointment_conflict(doctor_user_id, appointment_date, start_time, end_time):
                     errors['conflict'] = "Time slot conflict detected. Check schedule or use override."
            # --- End Validation ---

            if errors:
                for field, msg in errors.items(): flash(f"{msg}", "danger")
                return render_template(
                    'Admin_Portal/appointments/add.html',
                    appointment=request.form.to_dict(),
                    appointment_types=dynamic_appointment_types, # Pass dynamic types
                    appointment_statuses=APPOINTMENT_STATUSES, # For status dropdown if editable
                    patients=get_all_patients(), doctors=get_all_doctors(),
                    default_status=default_status, # Pass default status
                    errors=errors
                )

            # Proceed with insert
            conn = get_db_connection()
            if not conn: raise mysql.connector.Error("Database connection failed")
            cursor = conn.cursor()
            sql = """
                INSERT INTO appointments
                    (patient_id, doctor_id, appointment_date, start_time, end_time,
                     appointment_type, status, reason, notes, created_by, updated_by, reschedule_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0) -- Start count at 0
            """
            params = (
                patient_user_id, doctor_user_id, appointment_date,
                start_time.strftime('%H:%M:%S'), end_time.strftime('%H:%M:%S'),
                appointment_type, status, reason, notes,
                current_user.id, current_user.id
            )
            cursor.execute(sql, params)
            new_appointment_id = cursor.lastrowid
            conn.commit()

            flash(f"Appointment created successfully (ID: {new_appointment_id}).", "success")
            if override_restrictions: flash("Scheduling restrictions were overridden.", "info")
            return redirect(url_for('.list_appointments'))

        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"Database error adding appointment: {err}")
            flash(f"Database error adding appointment: {err}", "danger")
        except Exception as e:
             current_app.logger.error(f"Unexpected error adding appointment: {e}", exc_info=True)
             flash("An unexpected error occurred adding appointment.", "danger")
             if conn: conn.rollback()
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

        # Fallback render on error
        return render_template(
            'Admin_Portal/appointments/add.html',
            appointment=request.form.to_dict(),
            appointment_types=dynamic_appointment_types,
            appointment_statuses=APPOINTMENT_STATUSES,
            patients=get_all_patients(), doctors=get_all_doctors(),
            default_status=default_status,
            errors=errors if 'errors' in locals() else {'general': 'Failed to create appointment.'}
        )

    # --- GET Request ---
    return render_template(
        'Admin_Portal/appointments/add.html',
        appointment={},
        appointment_types=dynamic_appointment_types, # Use dynamic types
        appointment_statuses=APPOINTMENT_STATUSES, # For status dropdown if editable
        patients=get_all_patients(), doctors=get_all_doctors(),
        default_status=default_status, # Pass default status
        errors={}
    )


@admin_appointments_bp.route('/<int:appointment_id>/status', methods=['POST'])
@require_admin
def update_appointment_status(appointment_id):
    """Quickly update status, handle check-in, rescheduling limits, and follow-ups."""
    new_status = request.form.get('status')
    reschedule_limit = get_int_setting('reschedule_limit', 3)

    if not new_status or new_status not in APPOINTMENT_STATUSES:
        flash("Invalid or missing status provided.", "danger")
        return redirect(request.referrer or url_for('.list_appointments'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "danger")
            return redirect(request.referrer or url_for('.list_appointments'))

        # Get current appointment state BEFORE update
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, reschedule_count FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appointment = cursor.fetchone()
        if not appointment:
            flash(f"Appointment #{appointment_id} not found.", "warning")
            return redirect(request.referrer or url_for('.list_appointments'))

        current_status = appointment['status']
        current_reschedule_count = appointment['reschedule_count']

        # --- Check Rescheduling Limit ---
        is_rescheduling = (new_status == 'rescheduled' and current_status != 'rescheduled')
        if is_rescheduling and current_reschedule_count >= reschedule_limit:
            flash(f"Cannot set status to 'Rescheduled'. Limit ({reschedule_limit}) reached.", "danger")
            # Note: We don't have an override mechanism in this simple status update route
            return redirect(request.referrer or url_for('.list_appointments'))

        # --- Prepare Updates ---
        now_dt = datetime.datetime.now()
        set_clauses = ["status = %s", "updated_by = %s", "updated_at = CURRENT_TIMESTAMP"]
        params = [new_status, current_user.id]

        # Handle check-in time
        if new_status == 'checked-in' and current_status != 'checked-in':
            set_clauses.append("check_in_time = %s")
            params.append(now_dt)
        # Optional: Clear check-in if moving away from it?
        # elif new_status != 'checked-in' and current_status == 'checked-in':
        #    set_clauses.append("check_in_time = NULL")

        # Handle completion time (simple version)
        if new_status == 'completed' and current_status != 'completed':
             set_clauses.append("end_treatment_time = %s")
             params.append(now_dt)
             # Optionally set start_treatment_time if not already set?
             # set_clauses.append("start_treatment_time = COALESCE(start_treatment_time, check_in_time, %s)")
             # params.append(now_dt)

        # Increment reschedule count if applicable
        if is_rescheduling:
            set_clauses.append("reschedule_count = reschedule_count + 1")

        params.append(appointment_id) # Add appointment_id for WHERE clause

        # --- Execute Update ---
        cursor = conn.cursor() # Re-init cursor without dictionary=True for update
        sql = f"UPDATE appointments SET {', '.join(set_clauses)} WHERE appointment_id = %s"
        cursor.execute(sql, tuple(params))

        if cursor.rowcount == 0:
             # This might happen if the status was already the new_status, or ID was wrong (checked earlier though)
             flash(f"Appointment #{appointment_id} status unchanged or appointment not found.", "warning")
        else:
            # --- Trigger Follow-up for No-Show ---
            if new_status == 'no-show' and current_status != 'no-show':
                 create_followup_task(appointment_id, reason="No-Show Status Update")

            conn.commit()
            flash(f"Appointment #{appointment_id} status updated to '{new_status}'.", "success")
            if is_rescheduling: flash(f"Reschedule count updated to {current_reschedule_count + 1}.", "info")

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB error updating status for appointment {appointment_id}: {err}")
        flash("Database error occurred while updating status.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(request.referrer or url_for('.list_appointments'))


# --- Configuration Routes ---

@admin_appointments_bp.route('/config/types', methods=['GET', 'POST'])
@require_admin
def configure_appointment_types():
    """Configure appointment types and their default durations."""
    conn = None
    cursor = None

    if request.method == 'POST':
        action = request.form.get('action')
        type_id = request.form.get('type_id', type=int)
        type_name = request.form.get('type_name', '').strip()
        duration = request.form.get('default_duration_minutes', type=int)
        description = request.form.get('description', '').strip()
        is_active = 'is_active' in request.form

        if not type_name:
            flash("Type Name is required.", "danger")
        elif duration is None or duration <= 0:
             flash("Default Duration must be a positive number.", "danger")
        else:
            try:
                conn = get_db_connection()
                if not conn: raise mysql.connector.Error("DB Connection failed")
                cursor = conn.cursor()

                if action == 'add':
                    sql = """
                        INSERT INTO appointment_types (type_name, default_duration_minutes, description, is_active)
                        VALUES (%s, %s, %s, %s)
                    """
                    params = (type_name, duration, description or None, is_active)
                    cursor.execute(sql, params)
                    flash(f"Appointment type '{type_name}' added successfully.", "success")
                elif action == 'update' and type_id:
                    sql = """
                        UPDATE appointment_types SET
                            type_name = %s, default_duration_minutes = %s, description = %s, is_active = %s
                        WHERE type_id = %s
                    """
                    params = (type_name, duration, description or None, is_active, type_id)
                    cursor.execute(sql, params)
                    if cursor.rowcount > 0:
                         flash(f"Appointment type '{type_name}' updated successfully.", "success")
                    else:
                         flash("Appointment type not found or no changes made.", "warning")
                else:
                     flash("Invalid action or missing Type ID for update.", "danger")

                if cursor.lastrowid or cursor.rowcount > 0: # Check if insert or update happened
                    conn.commit()
                else:
                     if conn: conn.rollback() # Rollback if error or no change

            except mysql.connector.Error as err:
                if conn: conn.rollback()
                if err.errno == 1062: # Duplicate entry
                    flash(f"Appointment type name '{type_name}' already exists.", "danger")
                else:
                    flash(f"Database error saving appointment type: {err}", "danger")
                current_app.logger.error(f"DB error saving appointment type: {err}")
            finally:
                if cursor: cursor.close()
                if conn: conn.close()

        # Redirect to GET to show updated list/form
        return redirect(url_for('.configure_appointment_types'))

    # --- GET Request ---
    current_types = get_appointment_types(active_only=False) # Show all for configuration
    return render_template('Admin_Portal/config/types.html', types=current_types)


@admin_appointments_bp.route('/config/rules', methods=['GET', 'POST'])
@require_admin
def configure_scheduling_rules():
    """Configure system-wide scheduling rules."""
    if request.method == 'POST':
        settings_to_save = {
            'allow_double_booking': request.form.get('allow_double_booking') == 'true', # Convert checkbox/select value
            'reschedule_limit': request.form.get('reschedule_limit', type=int),
            'min_reschedule_notice_hours': request.form.get('min_reschedule_notice_hours', type=int),
            'missed_appt_followup_days': request.form.get('missed_appt_followup_days', type=int),
            'default_appointment_status': request.form.get('default_appointment_status')
        }
        success = True
        for key, value in settings_to_save.items():
            # Basic validation (ensure numeric are numbers, status is valid)
            if value is None and key in ['reschedule_limit', 'min_reschedule_notice_hours', 'missed_appt_followup_days']:
                 flash(f"Invalid numeric value provided for {key.replace('_', ' ').title()}.", "danger")
                 success = False
                 break
            if key == 'default_appointment_status' and value not in APPOINTMENT_STATUSES:
                 flash(f"Invalid Default Appointment Status selected.", "danger")
                 success = False
                 break

            if not set_setting(key, str(value).lower() if isinstance(value, bool) else str(value)): # Save bools as 'true'/'false'
                success = False # set_setting will flash specific DB errors

        if success:
            flash("Scheduling rules updated successfully.", "success")
        # Redirect to GET to show saved values
        return redirect(url_for('.configure_scheduling_rules'))

    # --- GET Request ---
    # Fetch current settings to display in the form
    current_settings = {
        'allow_double_booking': get_bool_setting('allow_double_booking', False),
        'reschedule_limit': get_int_setting('reschedule_limit', 3),
        'min_reschedule_notice_hours': get_int_setting('min_reschedule_notice_hours', 24),
        'missed_appt_followup_days': get_int_setting('missed_appt_followup_days', 2),
        'default_appointment_status': get_setting('default_appointment_status', 'scheduled')
    }
    return render_template('Admin_Portal/config/rules.html',
                           settings=current_settings,
                           statuses=APPOINTMENT_STATUSES) # Pass statuses for dropdown


# --- Reporting Route ---
@admin_appointments_bp.route('/reports', methods=['GET'])
@require_admin
def view_reports():
    """Generate and display reports, including cancellations and wait times."""
    report_type = request.args.get('type', 'summary')
    # Add date range filters for reports
    report_date_from_str = request.args.get('report_date_from', (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d'))
    report_date_to_str = request.args.get('report_date_to', datetime.date.today().strftime('%Y-%m-%d'))

    report_data = {}
    conn = None
    cursor = None
    try:
        # Validate date range
        report_date_from = datetime.datetime.strptime(report_date_from_str, '%Y-%m-%d').date()
        report_date_to = datetime.datetime.strptime(report_date_to_str, '%Y-%m-%d').date()
        if report_date_from > report_date_to:
             flash("Report 'Date From' cannot be after 'Date To'.", "warning")
             # Swap dates or default range? Swap for now.
             report_date_from, report_date_to = report_date_to, report_date_from
             report_date_from_str, report_date_to_str = report_date_to_str, report_date_from_str

        conn = get_db_connection()
        if not conn: raise mysql.connector.Error("DB connection failed")
        cursor = conn.cursor(dictionary=True)

        # --- Build Reports ---
        params = [report_date_from, report_date_to] # Base date range params

        if report_type == 'cancellation':
            # Cancellation patterns (Example: by type, by doctor)
            query_by_type = """
                SELECT appointment_type, COUNT(*) as count
                FROM appointments
                WHERE status = 'canceled' AND appointment_date BETWEEN %s AND %s
                GROUP BY appointment_type ORDER BY count DESC;
            """
            cursor.execute(query_by_type, tuple(params))
            report_data['cancellation_by_type'] = cursor.fetchall()

            query_by_doctor = """
                 SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name, COUNT(*) as count
                 FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                 WHERE a.status = 'canceled' AND a.appointment_date BETWEEN %s AND %s
                 GROUP BY a.doctor_id ORDER BY count DESC;
            """
            cursor.execute(query_by_doctor, tuple(params))
            report_data['cancellation_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"Cancellation Patterns ({report_date_from_str} to {report_date_to_str})"

        elif report_type == 'wait_time':
            # Average wait time (check_in_time to start_treatment_time) - REQUIRES DATA!
            query_avg_wait = """
                SELECT
                    CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name,
                    AVG(TIMESTAMPDIFF(MINUTE, check_in_time, start_treatment_time)) as avg_wait_minutes,
                    COUNT(*) as completed_with_times
                FROM appointments a
                JOIN users ud ON a.doctor_id = ud.user_id
                WHERE status = 'completed'
                  AND check_in_time IS NOT NULL
                  AND start_treatment_time IS NOT NULL
                  AND start_treatment_time > check_in_time -- Ensure valid range
                  AND appointment_date BETWEEN %s AND %s
                GROUP BY a.doctor_id
                ORDER BY avg_wait_minutes DESC;
            """
            cursor.execute(query_avg_wait, tuple(params))
            report_data['avg_wait_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"Average Wait Times ({report_date_from_str} to {report_date_to_str})"
            flash("Wait time reports depend on check-in and treatment start times being recorded.", "info")

        # Include existing reports (No-Show, Utilization, Summary) adapting date range
        elif report_type == 'utilization':
            query_util = """
                SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name, DATE_FORMAT(a.appointment_date, '%Y-%m') AS month,
                       COUNT(a.appointment_id) AS appointment_count, a.status
                FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                WHERE a.appointment_date BETWEEN %s AND %s
                GROUP BY doctor_name, month, a.status ORDER BY doctor_name, month, a.status;
            """
            cursor.execute(query_util, tuple(params))
            report_data['utilization_by_doctor_month'] = cursor.fetchall()
            report_data['report_title'] = f"Utilization by Doctor/Month ({report_date_from_str} to {report_date_to_str})"

        elif report_type == 'no-show':
            query_noshow = """
                SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name,
                       COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) AS no_show_count,
                       COUNT(a.appointment_id) AS total_appointments,
                       (COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) * 100.0 / COUNT(a.appointment_id)) AS no_show_rate
                FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                WHERE a.appointment_date BETWEEN %s AND %s
                  AND a.status IN ('completed', 'no-show') -- Base statuses for rate calculation
                GROUP BY a.doctor_id HAVING total_appointments > 0 ORDER BY no_show_rate DESC;
            """
            cursor.execute(query_noshow, tuple(params))
            report_data['no_show_rate_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"No-Show Rate by Doctor ({report_date_from_str} to {report_date_to_str})"

        else: # Default Summary Report
             query_status = "SELECT status, COUNT(*) as count FROM appointments WHERE appointment_date BETWEEN %s AND %s GROUP BY status;"
             cursor.execute(query_status, tuple(params))
             report_data['status_summary'] = cursor.fetchall()
             query_type = "SELECT appointment_type, COUNT(*) as count FROM appointments WHERE appointment_date BETWEEN %s AND %s GROUP BY appointment_type;"
             cursor.execute(query_type, tuple(params))
             report_data['type_summary'] = cursor.fetchall()
             report_data['report_title'] = f"Appointment Summary ({report_date_from_str} to {report_date_to_str})"
             report_type = 'summary' # Ensure default type is set

    except ValueError:
         flash("Invalid date format provided for report range. Use YYYY-MM-DD.", "danger")
         # Use default dates on error
         report_date_from_str = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
         report_date_to_str = datetime.date.today().strftime('%Y-%m-%d')
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error generating report '{report_type}': {err}")
        flash(f"Error generating report: {err}", "danger")
        report_data = {'error': str(err)}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template(
        'Admin_Portal/reports/summary.html', # Consider using dynamic templates per report type
        report_data=report_data,
        report_type=report_type,
        report_date_from=report_date_from_str,
        report_date_to=report_date_to_str
    )

# --- NEW: Follow-up Management Route (Basic Example) ---
@admin_appointments_bp.route('/followups', methods=['GET'])
@require_admin
def manage_followups():
    """List pending follow-up tasks."""
    conn = None
    cursor = None
    followups = []
    try:
        conn = get_db_connection()
        if not conn: raise mysql.connector.Error("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        # Fetch pending followups with appointment details
        query = """
            SELECT
                f.followup_id, f.appointment_id, f.followup_status, f.notes, f.created_at AS followup_created_at,
                a.appointment_date, a.start_time,
                CONCAT(up.first_name, ' ', up.last_name) AS patient_name, up.user_id AS patient_id,
                CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name
            FROM appointment_followups f
            JOIN appointments a ON f.appointment_id = a.appointment_id
            LEFT JOIN users up ON a.patient_id = up.user_id
            LEFT JOIN users ud ON a.doctor_id = ud.user_id
            WHERE f.followup_status = 'pending' -- Or allow filtering by status
            ORDER BY f.created_at DESC
        """
        cursor.execute(query)
        followups = cursor.fetchall()

        # Basic type conversion for display
        for item in followups:
             if item.get('appointment_date') and not isinstance(item['appointment_date'], datetime.date):
                 try: item['appointment_date'] = datetime.datetime.strptime(str(item['appointment_date']), '%Y-%m-%d').date()
                 except ValueError: item['appointment_date'] = None
             if item.get('start_time') and not isinstance(item['start_time'], datetime.time):
                  try: item['start_time'] = datetime.datetime.strptime(str(item['start_time']), '%H:%M:%S').time()
                  except (ValueError, TypeError): item['start_time'] = None # Handle potential timedelta conversion if needed
             if item.get('followup_created_at') and not isinstance(item['followup_created_at'], datetime.datetime):
                 try: item['followup_created_at'] = datetime.datetime.strptime(str(item['followup_created_at']), '%Y-%m-%d %H:%M:%S')
                 except (ValueError, TypeError): item['followup_created_at'] = None


    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error fetching followups: {err}")
        flash("Error fetching follow-up tasks.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return render_template('Admin_Portal/appointments/followups.html', followups=followups)

# --- NEW: Route to update follow-up status ---
@admin_appointments_bp.route('/followups/<int:followup_id>/update', methods=['POST'])
@require_admin
def update_followup_status(followup_id):
    """Update the status of a follow-up task."""
    new_status = request.form.get('followup_status')
    notes = request.form.get('notes', '').strip()
    valid_followup_statuses = ['pending', 'contacted', 'resolved', 'ignored'] # Define allowed statuses

    if not new_status or new_status not in valid_followup_statuses:
        flash("Invalid follow-up status provided.", "danger")
        return redirect(request.referrer or url_for('.manage_followups'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise mysql.connector.Error("DB connection failed")
        cursor = conn.cursor()
        sql = """
            UPDATE appointment_followups SET
                followup_status = %s,
                notes = CONCAT(COALESCE(notes, ''), '\nAdmin Update: ', %s), -- Append notes
                updated_by = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE followup_id = %s
        """
        params = (new_status, notes, current_user.id, followup_id)
        cursor.execute(sql, params)

        if cursor.rowcount == 0:
            flash(f"Follow-up task #{followup_id} not found.", "warning")
        else:
            conn.commit()
            flash(f"Follow-up task #{followup_id} updated to '{new_status}'.", "success")

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB error updating followup {followup_id}: {err}")
        flash("Database error updating follow-up task.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(request.referrer or url_for('.manage_followups'))


# --- NEW: Routes for Check-in / Wait Time Management (Example Actions) ---
# These might be better integrated into a dedicated "Clinic Flow" page or dashboard

@admin_appointments_bp.route('/<int:appointment_id>/checkin', methods=['POST'])
@require_admin
def checkin_appointment(appointment_id):
    """Explicitly mark an appointment as checked-in and record time."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise mysql.connector.Error("DB connection failed")

        # Check current status - maybe only allow check-in from 'scheduled' or 'confirmed'
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, check_in_time FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appointment = cursor.fetchone()
        if not appointment:
             flash("Appointment not found.", "warning")
             return redirect(request.referrer or url_for('.list_appointments'))
        if appointment['check_in_time']:
             flash("Patient already checked in.", "info")
             return redirect(request.referrer or url_for('.list_appointments'))
        # Add status check logic here if needed:
        # allowed_prev_statuses = ['scheduled', 'confirmed']
        # if appointment['status'] not in allowed_prev_statuses:
        #      flash(f"Cannot check-in from status '{appointment['status']}'.", "warning")
        #      return redirect(request.referrer or url_for('.list_appointments'))

        cursor = conn.cursor() # Re-init for update
        sql = """
            UPDATE appointments SET
                status = 'checked-in',
                check_in_time = CURRENT_TIMESTAMP,
                updated_by = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE appointment_id = %s AND check_in_time IS NULL -- Prevent race condition
        """
        cursor.execute(sql, (current_user.id, appointment_id))
        if cursor.rowcount > 0:
            conn.commit()
            flash(f"Appointment #{appointment_id} checked in successfully.", "success")
        else:
             # Could be race condition or already checked in
             flash(f"Failed to check in appointment #{appointment_id}. It might already be checked in.", "warning")
             if conn: conn.rollback()

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB error checking in appointment {appointment_id}: {err}")
        flash("Database error during check-in.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(request.referrer or url_for('.list_appointments'))
