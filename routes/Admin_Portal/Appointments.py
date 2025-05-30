# Appointments.py (Admin - Config & Reports ONLY, No Wait Times)

import datetime
import math
import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app
)
from flask_login import login_required, current_user
from db import get_db_connection
from functools import wraps
import re 

admin_appointments_bp = Blueprint(
    'admin_appointments',
    __name__,
    template_folder='../templates', 
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

def get_appointment_types(active_only=False):
    conn = None; cursor = None; types = []
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            current_app.logger.error("Failed to connect to DB for get_appointment_types")
            return []
        cursor = conn.cursor(dictionary=True)
        query = "SELECT type_id, type_name, default_duration_minutes, description, is_active FROM appointment_types"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY type_name"
        cursor.execute(query)
        types = cursor.fetchall()
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error getting appointment types: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return types if types else []


# --- Appointment Type Configuration ---
@admin_appointments_bp.route('/config/types', methods=['GET', 'POST'])
@require_admin
def configure_appointment_types():
    conn = None; cursor = None
    if request.method == 'POST':
        action = request.form.get('action')
        type_id_str = request.form.get('type_id') 
        type_name = request.form.get('type_name', '').strip()
        duration_str = request.form.get('default_duration_minutes')
        description = request.form.get('description', '').strip() or None
        is_active = 'is_active' in request.form 

        type_id = None
        if type_id_str:
            try: type_id = int(type_id_str)
            except ValueError: flash("Invalid Type ID format.", "danger"); action = None

        duration = None
        if duration_str:
            try: duration = int(duration_str)
            except ValueError: flash("Duration must be a number.", "danger"); action = None
        
        if action and not type_name:
            flash("Type Name is required.", "danger")
        elif action and (duration is None or duration <= 0):
             flash("Default Duration must be a positive number.", "danger")
        elif action: 
            try:
                conn = get_db_connection()
                if not conn or not conn.is_connected(): 
                    raise mysql.connector.Error("DB Connection failed")
                cursor = conn.cursor()
                conn.autocommit = False

                if action == 'add':
                    sql = "INSERT INTO appointment_types (type_name, default_duration_minutes, description, is_active) VALUES (%s, %s, %s, %s)"
                    params = (type_name, duration, description, is_active)
                    cursor.execute(sql, params)
                    flash(f"Appointment type '{type_name}' added.", "success")
                elif action == 'update' and type_id is not None:
                    sql = "UPDATE appointment_types SET type_name = %s, default_duration_minutes = %s, description = %s, is_active = %s WHERE type_id = %s"
                    params = (type_name, duration, description, is_active, type_id)
                    cursor.execute(sql, params)
                    flash(f"Type '{type_name}' updated." if cursor.rowcount > 0 else "No changes or type not found.", "info" if cursor.rowcount > 0 else "warning")
                elif action == 'update' and type_id is None:
                    flash("Type ID missing for update action.", "danger")
                else:
                     flash("Invalid action specified.", "danger")

                if action in ['add', 'update']: conn.commit()

            except mysql.connector.Error as err:
                if conn and conn.is_connected() and not conn.autocommit : conn.rollback()
                if err.errno == 1062: flash(f"Type name '{type_name}' already exists.", "danger")
                else: flash(f"Database error: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
                current_app.logger.error(f"DB error saving appointment type: {err}")
            except Exception as e:
                if conn and conn.is_connected() and not conn.autocommit : conn.rollback()
                current_app.logger.error(f"Unexpected error saving appointment type: {e}", exc_info=True)
                flash(f"An unexpected error occurred: {str(e)}", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): 
                    if not conn.autocommit : conn.autocommit = True 
                    conn.close()
        return redirect(url_for('.configure_appointment_types'))

    current_types = get_appointment_types(active_only=False)
    return render_template('Admin_Portal/appointments/config_types.html', types=current_types)


# --- Reports ---
@admin_appointments_bp.route('/reports', methods=['GET'])
@require_admin
def view_reports():
    report_type = request.args.get('type', 'summary').lower()
    report_date_from_str = request.args.get('report_date_from', (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d'))
    report_date_to_str = request.args.get('report_date_to', datetime.date.today().strftime('%Y-%m-%d'))
    
    report_data = {}
    report_date_from, report_date_to = None, None 
    conn = None; cursor = None
    try:
        report_date_from = datetime.datetime.strptime(report_date_from_str, '%Y-%m-%d').date()
        report_date_to = datetime.datetime.strptime(report_date_to_str, '%Y-%m-%d').date()
        if report_date_from > report_date_to:
             report_date_from, report_date_to = report_date_to, report_date_from
             report_date_from_str, report_date_to_str = report_date_to_str, report_date_from_str
             flash("Report 'Date From' was after 'Date To'; dates have been swapped.", "info")

        conn = get_db_connection()
        if not conn or not conn.is_connected(): 
            raise mysql.connector.Error("DB connection failed for reports")
        cursor = conn.cursor(dictionary=True)
        params = [report_date_from, report_date_to]
        
        # Allowed report types (Wait Times removed)
        valid_report_types = ['summary', 'cancellation', 'no-show', 'utilization']
        if report_type not in valid_report_types:
            report_type = 'summary' 
            flash(f"Invalid report type requested. Showing summary.", "warning")


        if report_type == 'cancellation':
            query_by_type = """
                SELECT COALESCE(at.type_name, 'Unspecified Type') as type_name, COUNT(a.appointment_id) as count
                FROM appointments a LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.status = 'canceled' AND a.appointment_date BETWEEN %s AND %s
                GROUP BY at.type_name ORDER BY count DESC;
            """
            cursor.execute(query_by_type, tuple(params))
            report_data['cancellation_by_type'] = cursor.fetchall()
            query_by_doctor = """
                 SELECT CONCAT('Dr. ', ud.first_name, ' ', ud.last_name) AS doctor_name, COUNT(a.appointment_id) as count
                 FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                 WHERE a.status = 'canceled' AND a.appointment_date BETWEEN %s AND %s
                 GROUP BY a.doctor_id ORDER BY count DESC;
            """
            cursor.execute(query_by_doctor, tuple(params))
            report_data['cancellation_by_doctor'] = cursor.fetchall()
        # "Wait Time" report section REMOVED
        elif report_type == 'utilization':
            query_util = """
                SELECT CONCAT('Dr. ', ud.first_name, ' ', ud.last_name) AS doctor_name, 
                       DATE_FORMAT(a.appointment_date, '%Y-%m') AS month,
                       COALESCE(at.type_name, 'Unspecified Type') AS appointment_type_name,
                       COUNT(a.appointment_id) AS appointment_count, a.status
                FROM appointments a 
                JOIN users ud ON a.doctor_id = ud.user_id
                LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.appointment_date BETWEEN %s AND %s
                GROUP BY doctor_name, month, appointment_type_name, a.status ORDER BY doctor_name, month, appointment_count DESC;
            """
            cursor.execute(query_util, tuple(params))
            report_data['utilization_by_doctor_month_type'] = cursor.fetchall()
        elif report_type == 'no-show':
            query_noshow = """
                SELECT CONCAT('Dr. ', ud.first_name, ' ', ud.last_name) AS doctor_name,
                       COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) AS no_show_count,
                       COUNT(CASE WHEN a.status IN ('completed', 'no-show', 'scheduled', 'confirmed') THEN 1 END) AS total_relevant_appointments,
                       (COUNT(CASE WHEN a.status = 'no-show' THEN 1 END) * 100.0 / 
                        NULLIF(COUNT(CASE WHEN a.status IN ('completed', 'no-show', 'scheduled', 'confirmed') THEN 1 END), 0) 
                       ) AS no_show_rate
                FROM appointments a JOIN users ud ON a.doctor_id = ud.user_id
                WHERE a.appointment_date BETWEEN %s AND %s
                GROUP BY a.doctor_id HAVING COUNT(CASE WHEN a.status IN ('completed', 'no-show', 'scheduled', 'confirmed') THEN 1 END) > 0 
                ORDER BY no_show_rate DESC, no_show_count DESC;
            """
            cursor.execute(query_noshow, tuple(params))
            report_data['no_show_rate_by_doctor'] = cursor.fetchall()
        else: # Default Summary Report (report_type will be 'summary')
             query_status = "SELECT status, COUNT(*) as count FROM appointments WHERE appointment_date BETWEEN %s AND %s GROUP BY status;"
             cursor.execute(query_status, tuple(params))
             report_data['status_summary'] = cursor.fetchall()
             query_type_summary = """
                SELECT COALESCE(at.type_name, 'Unspecified Type') as type_name, COUNT(a.appointment_id) as count 
                FROM appointments a
                LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
                WHERE a.appointment_date BETWEEN %s AND %s 
                GROUP BY at.type_name ORDER BY count DESC;
             """
             cursor.execute(query_type_summary, tuple(params))
             report_data['type_summary'] = cursor.fetchall()
        
        report_data['report_title'] = f"{report_type.replace('_', ' ').title()} Report ({report_date_from_str} to {report_date_to_str})"

    except ValueError:
         flash("Invalid date format. Please use YYYY-MM-DD.", "danger")
         report_date_from_str = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
         report_date_to_str = datetime.date.today().strftime('%Y-%m-%d')
         report_data['error'] = "Invalid date format provided."
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error generating report '{report_type}': {err}")
        flash(f"Error generating report: {err.msg if hasattr(err, 'msg') else str(err)}", "danger"); report_data = {'error': str(err)}
    except Exception as e:
        current_app.logger.error(f"Unexpected error generating report '{report_type}': {e}", exc_info=True)
        flash(f"An unexpected error occurred: {str(e)}", "danger"); report_data = {'error': str(e)}
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return render_template(
        'Admin_Portal/reports/appointment_reports.html',
        report_data=report_data,
        report_type=report_type,
        report_date_from=report_date_from_str,
        report_date_to=report_date_to_str
    )