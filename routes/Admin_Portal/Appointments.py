# Appointments.py

import datetime
import math
import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app, abort, jsonify
)
from flask_login import login_required, current_user
from db import get_db_connection
from functools import wraps
import re # For get_enum_values

# Define the Blueprint for Admin Appointment Management
admin_appointments_bp = Blueprint(
    'admin_appointments',
    __name__,
    template_folder='../templates', # Adjusted to look in templates/Admin_Portal/appointments
    url_prefix='/admin/appointments'
)

# --- Helper Functions ---

def is_admin():
    return (current_user and
            hasattr(current_user, 'is_authenticated') and
            current_user.is_authenticated and
            hasattr(current_user, 'user_type') and
            current_user.user_type == "admin")

def require_admin(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not is_admin():
            flash("Access denied. Administrator privileges required.", "danger")
            return redirect(url_for('login.login_route', next=request.url))
        return func(*args, **kwargs)
    return decorated_view

# --- COPIED/ADAPTED get_enum_values (from Doctors_Management.py or similar) ---
DEFAULT_APPOINTMENT_STATUSES = ['scheduled', 'confirmed', 'completed', 'canceled', 'no-show', 'rescheduled']

def get_enum_values_from_db(table_name, column_name, default_values=None):
    """Fetches possible ENUM values for a given table and column from DB."""
    connection = None
    cursor = None
    enum_values = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed for ENUM fetch: {table_name}.{column_name}")
            return default_values or []
        
        cursor = connection.cursor()
        # Determine database name dynamically or from config
        db_name = connection.database
        if not db_name: # Fallback if not set on connection object
            db_name = current_app.config.get('MYSQL_DB') 
        
        if not db_name:
            current_app.logger.warning(f"Could not determine database name for ENUM fetch of {table_name}.{column_name}.")
            return default_values or []

        query = """
            SELECT COLUMN_TYPE 
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s 
              AND TABLE_NAME = %s 
              AND COLUMN_NAME = %s
        """
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()

        if result and result[0]:
            # Format is ENUM('val1','val2',...)
            type_info = result[0].decode('utf-8') if isinstance(result[0], bytearray) else result[0]
            if type_info.lower().startswith("enum("):
                # Extract values between parentheses and split by comma
                # Ensure to strip single quotes from each value
                content = type_info[5:-1] # Remove "enum(" and ")"
                enum_values = [val.strip().strip("'") for val in content.split(',')]
            else:
                current_app.logger.warning(f"Column {table_name}.{column_name} is not an ENUM or format not recognized: {type_info}")
        else:
            current_app.logger.warning(f"ENUM definition not found for {table_name}.{column_name} in database {db_name}.")
            
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching ENUM values for {table_name}.{column_name}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"General error fetching ENUM values for {table_name}.{column_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return enum_values if enum_values else (default_values or [])


# --- Settings Helpers ---
def get_setting(key, default=None):
    conn = None; cursor = None
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
        if conn and conn.is_connected(): conn.close()

def get_bool_setting(key, default=False):
    value = get_setting(key, 'true' if default else 'false') # Ensure default matches string 'true'/'false'
    return value.lower() == 'true'

def get_int_setting(key, default=0):
    value_str = get_setting(key, str(default))
    try:
        return int(value_str)
    except (ValueError, TypeError):
        current_app.logger.warning(f"Setting '{key}' ('{value_str}') is not a valid integer. Using default {default}.")
        return default

def set_setting(key, value, description=None):
    conn = None; cursor = None
    success = False
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "danger")
            return False # Indicate failure
        cursor = conn.cursor()
        
        # Ensure value is a string for the database
        db_value = str(value).lower() if isinstance(value, bool) else str(value)

        if description is not None: # Only include description if provided
            sql = """
                INSERT INTO settings (setting_key, setting_value, description)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value), 
                    description = VALUES(description),
                    updated_at = CURRENT_TIMESTAMP 
            """
            params = (key, db_value, description)
        else: # If description is None, don't try to update it, only update if new
             sql = """
                INSERT INTO settings (setting_key, setting_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value),
                    updated_at = CURRENT_TIMESTAMP
            """
             params = (key, db_value)
        
        cursor.execute(sql, params)
        conn.commit()
        success = True
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error setting setting '{key}': {err}")
        flash(f"Database error saving setting '{key}': {err}", "danger")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return success

# --- Appointment Type Helper ---
def get_appointment_types(active_only=True):
    conn = None; cursor = None; types = []
    try:
        conn = get_db_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        query = "SELECT type_id, type_name, default_duration_minutes, description, is_active FROM appointment_types"
        if active_only:
            query += " WHERE is_active = TRUE" # Note: SQL TRUE is 1
        query += " ORDER BY type_name"
        cursor.execute(query)
        types = cursor.fetchall()
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error getting appointment types: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return types if types else []


# --- Routes ---
@admin_appointments_bp.route('/config/types', methods=['GET', 'POST'])
@require_admin
def configure_appointment_types():
    conn = None
    cursor = None
    if request.method == 'POST':
        action = request.form.get('action')
        type_id_str = request.form.get('type_id') # Get as string first
        type_name = request.form.get('type_name', '').strip()
        duration_str = request.form.get('default_duration_minutes')
        description = request.form.get('description', '').strip() or None # Ensure None if empty
        is_active = 'is_active' in request.form # Checkbox value

        type_id = None
        if type_id_str:
            try: type_id = int(type_id_str)
            except ValueError: flash("Invalid Type ID format.", "danger"); action = None # Invalidate action

        duration = None
        if duration_str:
            try: duration = int(duration_str)
            except ValueError: flash("Duration must be a number.", "danger"); action = None # Invalidate action
        
        if action and not type_name: # Action depends on valid inputs
            flash("Type Name is required.", "danger")
        elif action and (duration is None or duration <= 0):
             flash("Default Duration must be a positive number.", "danger")
        elif action: # Proceed if basic validations pass
            try:
                conn = get_db_connection()
                if not conn: raise mysql.connector.Error("DB Connection failed")
                cursor = conn.cursor()

                if action == 'add':
                    sql = "INSERT INTO appointment_types (type_name, default_duration_minutes, description, is_active) VALUES (%s, %s, %s, %s)"
                    params = (type_name, duration, description, is_active)
                    cursor.execute(sql, params)
                    flash(f"Appointment type '{type_name}' added.", "success")
                elif action == 'update' and type_id:
                    sql = "UPDATE appointment_types SET type_name = %s, default_duration_minutes = %s, description = %s, is_active = %s WHERE type_id = %s"
                    params = (type_name, duration, description, is_active, type_id)
                    cursor.execute(sql, params)
                    flash(f"Type '{type_name}' updated." if cursor.rowcount > 0 else "No changes or type not found.", "info" if cursor.rowcount > 0 else "warning")
                else:
                     flash("Invalid action or missing Type ID for update.", "danger")

                conn.commit() # Commit if no error

            except mysql.connector.Error as err:
                if conn: conn.rollback()
                if err.errno == 1062: flash(f"Type name '{type_name}' already exists.", "danger")
                else: flash(f"Database error: {err}", "danger")
                current_app.logger.error(f"DB error saving appointment type: {err}")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
        return redirect(url_for('.configure_appointment_types'))

    current_types = get_appointment_types(active_only=False)
    return render_template('Admin_Portal/config/types.html', types=current_types) # Corrected template path


@admin_appointments_bp.route('/config/rules', methods=['GET', 'POST'])
@require_admin
def configure_scheduling_rules():
    # Fetch ENUM values for appointment status dropdown
    appointment_statuses = get_enum_values_from_db('appointments', 'status', DEFAULT_APPOINTMENT_STATUSES)

    if request.method == 'POST':
        settings_to_save = {
            'allow_double_booking': request.form.get('allow_double_booking') == 'true',
            'reschedule_limit': request.form.get('reschedule_limit'),
            'min_reschedule_notice_hours': request.form.get('min_reschedule_notice_hours'),
            'missed_appt_followup_days': request.form.get('missed_appt_followup_days'),
            'default_appointment_status': request.form.get('default_appointment_status')
        }
        success_all = True
        for key, value_str in settings_to_save.items():
            value_to_save = value_str
            # Validate and convert numeric types
            if key in ['reschedule_limit', 'min_reschedule_notice_hours', 'missed_appt_followup_days']:
                try:
                    value_to_save = int(value_str)
                    if value_to_save < 0:
                         flash(f"{key.replace('_', ' ').title()} cannot be negative.", "danger")
                         success_all = False; break
                except (ValueError, TypeError):
                    flash(f"Invalid numeric value for {key.replace('_', ' ').title()}.", "danger")
                    success_all = False; break
            
            if key == 'default_appointment_status' and value_to_save not in appointment_statuses:
                 flash(f"Invalid Default Appointment Status selected: '{value_to_save}'.", "danger")
                 success_all = False; break

            if not success_all: break # Stop if validation failed

            if not set_setting(key, value_to_save): # set_setting handles bool to string conversion
                success_all = False # set_setting will flash specific DB errors

        if success_all:
            flash("Scheduling rules updated successfully.", "success")
        return redirect(url_for('.configure_scheduling_rules'))

    current_settings = {
        'allow_double_booking': get_bool_setting('allow_double_booking', False),
        'reschedule_limit': get_int_setting('reschedule_limit', 3),
        'min_reschedule_notice_hours': get_int_setting('min_reschedule_notice_hours', 24),
        'missed_appt_followup_days': get_int_setting('missed_appt_followup_days', 2),
        'default_appointment_status': get_setting('default_appointment_status', 'scheduled')
    }
    return render_template('Admin_Portal/config/rules.html', # Corrected template path
                           settings=current_settings,
                           statuses=appointment_statuses)


@admin_appointments_bp.route('/reports', methods=['GET'])
@require_admin
def view_reports():
    report_type = request.args.get('type', 'summary')
    report_date_from_str = request.args.get('report_date_from', (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d'))
    report_date_to_str = request.args.get('report_date_to', datetime.date.today().strftime('%Y-%m-%d'))
    appointment_types_for_filter = get_appointment_types(active_only=False) # Get all for filtering

    report_data = {}
    conn = None; cursor = None
    try:
        report_date_from = datetime.datetime.strptime(report_date_from_str, '%Y-%m-%d').date()
        report_date_to = datetime.datetime.strptime(report_date_to_str, '%Y-%m-%d').date()
        if report_date_from > report_date_to:
             report_date_from, report_date_to = report_date_to, report_date_from
             report_date_from_str, report_date_to_str = report_date_to_str, report_date_from_str
             flash("Report 'Date From' was after 'Date To'; dates have been swapped.", "info")

        conn = get_db_connection()
        if not conn: raise mysql.connector.Error("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        params = [report_date_from, report_date_to]

        if report_type == 'cancellation':
            query_by_type = """
                SELECT at.type_name, COUNT(a.appointment_id) as count
                FROM appointments a
                LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.status = 'canceled' AND a.appointment_date BETWEEN %s AND %s
                GROUP BY at.type_name ORDER BY count DESC;
            """
            cursor.execute(query_by_type, tuple(params))
            report_data['cancellation_by_type'] = cursor.fetchall()
            query_by_doctor = """
                 SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name, COUNT(a.appointment_id) as count
                 FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                 WHERE a.status = 'canceled' AND a.appointment_date BETWEEN %s AND %s
                 GROUP BY a.doctor_id ORDER BY count DESC;
            """
            cursor.execute(query_by_doctor, tuple(params))
            report_data['cancellation_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"Cancellation Patterns ({report_date_from_str} to {report_date_to_str})"
        elif report_type == 'wait_time':
            query_avg_wait = """
                SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name,
                       AVG(TIMESTAMPDIFF(MINUTE, a.check_in_time, a.start_treatment_time)) as avg_wait_minutes,
                       COUNT(a.appointment_id) as completed_with_times
                FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                WHERE a.status = 'completed' AND a.check_in_time IS NOT NULL AND a.start_treatment_time IS NOT NULL
                  AND a.start_treatment_time > a.check_in_time AND a.appointment_date BETWEEN %s AND %s
                GROUP BY a.doctor_id ORDER BY avg_wait_minutes DESC;
            """
            cursor.execute(query_avg_wait, tuple(params))
            report_data['avg_wait_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"Average Wait Times ({report_date_from_str} to {report_date_to_str})"
            flash("Wait time reports depend on check-in and treatment start times being recorded.", "info")
        elif report_type == 'utilization':
            query_util = """
                SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name, 
                       DATE_FORMAT(a.appointment_date, '%Y-%m') AS month,
                       at.type_name AS appointment_type_name,
                       COUNT(a.appointment_id) AS appointment_count, a.status
                FROM appointments a 
                JOIN users ud ON a.doctor_id = ud.user_id
                LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.appointment_date BETWEEN %s AND %s
                GROUP BY doctor_name, month, appointment_type_name, a.status ORDER BY doctor_name, month, appointment_type_name, a.status;
            """
            cursor.execute(query_util, tuple(params))
            report_data['utilization_by_doctor_month_type'] = cursor.fetchall()
            report_data['report_title'] = f"Utilization by Doctor/Month/Type ({report_date_from_str} to {report_date_to_str})"
        elif report_type == 'no-show':
            query_noshow = """
                SELECT CONCAT(ud.first_name, ' ', ud.last_name) AS doctor_name,
                       COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) AS no_show_count,
                       COUNT(a.appointment_id) AS total_appointments,
                       (COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) * 100.0 / COUNT(a.appointment_id)) AS no_show_rate
                FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                WHERE a.appointment_date BETWEEN %s AND %s
                  AND a.status IN ('completed', 'no-show', 'scheduled', 'confirmed') 
                GROUP BY a.doctor_id HAVING total_appointments > 0 ORDER BY no_show_rate DESC;
            """ # Broadened total_appointments base for rate
            cursor.execute(query_noshow, tuple(params))
            report_data['no_show_rate_by_doctor'] = cursor.fetchall()
            report_data['report_title'] = f"No-Show Rate by Doctor ({report_date_from_str} to {report_date_to_str})"
        else: # Default Summary Report
             query_status = "SELECT status, COUNT(*) as count FROM appointments WHERE appointment_date BETWEEN %s AND %s GROUP BY status;"
             cursor.execute(query_status, tuple(params))
             report_data['status_summary'] = cursor.fetchall()
             query_type_summary = """
                SELECT at.type_name, COUNT(a.appointment_id) as count 
                FROM appointments a
                LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.appointment_date BETWEEN %s AND %s 
                GROUP BY at.type_name ORDER BY count DESC;
             """
             cursor.execute(query_type_summary, tuple(params))
             report_data['type_summary'] = cursor.fetchall()
             report_data['report_title'] = f"Appointment Summary ({report_date_from_str} to {report_date_to_str})"
             report_type = 'summary'
    except ValueError:
         flash("Invalid date format. Use YYYY-MM-DD.", "danger")
         report_date_from_str = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
         report_date_to_str = datetime.date.today().strftime('%Y-%m-%d')
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error generating report '{report_type}': {err}")
        flash(f"Error generating report: {err}", "danger"); report_data = {'error': str(err)}
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template(
        'Admin_Portal/reports/summary.html', # Standardized path
        report_data=report_data,
        report_type=report_type,
        report_date_from=report_date_from_str,
        report_date_to=report_date_to_str,
        appointment_types=appointment_types_for_filter # For potential dropdowns in report template
    )