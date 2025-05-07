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
