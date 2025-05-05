# routes/Doctor_Portal/Dashboard.py
import mysql.connector
from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection
# Correctly import the helper function
from utils.template_helpers import format_timedelta_as_time
from datetime import timedelta, datetime, date, time # Import time

from .utils import (
    check_doctor_authorization,
    check_provider_authorization,      # Import if used
    check_doctor_or_dietitian_authorization, # Import if used
    is_doctor_authorized_for_patient, # Import if used
    get_provider_id,
    get_enum_values,                 # Import if used
    get_all_simple,                  # Import if used
    calculate_age,                   # Import if used
    allowed_file,                    # Import if used
    generate_secure_filename,
    can_modify_appointment,
    get_doctor_details         # Import if used
)

# Define the Blueprint for doctor routes
doctor_main = Blueprint(
    'doctor_main',
    __name__,
    url_prefix='/doctor',
    template_folder='../../templates' # Adjust if templates are elsewhere relative to this file
)

# --- Dashboard Route ---
@doctor_main.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    # Check authorization first
    if not check_doctor_authorization(current_user):
        flash("Access denied. You must be logged in as a doctor.", "warning")
        # Adjust redirect target as needed (e.g., to a general login or home page)
        return redirect(url_for('auth.login')) # Assuming 'auth.login' is your login route

    doctor_user_id = current_user.id

    # Initialize all expected data keys to prevent template errors
    dashboard_data = {
        'doctor_info': None,
        'upcoming_appointments': [],
        'patient_count': 0,
        'unread_messages': 0,
        'appointments_today_count': 0,
    }

    conn = None
    cursor = None

    try:
        # 1. Fetch Doctor Info
        dashboard_data['doctor_info'] = get_doctor_details(doctor_user_id)
        if not dashboard_data['doctor_info']:
             current_app.logger.warning(f"Doctor profile details not found for user_id {doctor_user_id}. Dashboard may be incomplete.")
             # Decide if this is critical. If so, flash error and redirect or render with minimal data.
             # flash("Could not load your doctor profile information.", "warning")

        # 2. Establish Connection for dashboard queries
        conn = get_db_connection()
        if conn is None or not conn.is_connected():
             current_app.logger.error(f"DB connection failed for doctor dashboard data (Doctor User ID: {doctor_user_id})")
             flash("Database connection error. Cannot load dashboard data.", "danger")
             # Render template with whatever data was fetched (maybe just doctor_info or nothing)
             return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)

        cursor = conn.cursor(dictionary=True)

        # 3. Fetch Upcoming Appointments (Corrected Query)
        # Using CURDATE() is generally fine, but consider timezones if appointments span different zones.
        query_appointments = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                a.appointment_type, a.status,
                p_user.first_name AS patient_first_name,
                p_user.last_name AS patient_last_name,
                a.patient_id AS patient_user_id
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            WHERE a.doctor_id = %s
              AND a.appointment_date >= CURDATE()
              AND a.status IN ('scheduled', 'confirmed', 'rescheduled')
            ORDER BY a.appointment_date ASC, a.start_time ASC
            LIMIT 5;
        """
        cursor.execute(query_appointments, (doctor_user_id,))
        dashboard_data['upcoming_appointments'] = cursor.fetchall()
        # NOTE: Time formatting is now handled by the Jinja filter

        # 4. Fetch Appointments Today Count (Corrected Query)
        query_today_count = """
            SELECT COUNT(appointment_id) as count FROM appointments
            WHERE doctor_id = %s AND appointment_date = CURDATE()
            AND status NOT IN ('canceled', 'no-show', 'completed');
        """
        cursor.execute(query_today_count, (doctor_user_id,))
        result_today = cursor.fetchone()
        dashboard_data['appointments_today_count'] = result_today['count'] if result_today else 0

        # 5. Fetch Patient Count (Corrected Query)
        # Counts distinct patients who have had *any* appointment with this doctor
        query_patient_count = """
            SELECT COUNT(DISTINCT patient_id) AS count
            FROM appointments
            WHERE doctor_id = %s;
        """
        cursor.execute(query_patient_count, (doctor_user_id,))
        result_patients = cursor.fetchone()
        dashboard_data['patient_count'] = result_patients['count'] if result_patients else 0

        # 6. Fetch Unread Message Count (Corrected Query)
        query_unread_messages = """
            SELECT COUNT(cm.message_id) AS count FROM chat_messages cm
            JOIN chats c ON cm.chat_id = c.chat_id
            WHERE c.doctor_id = %s
              AND cm.sender_type = 'patient'
              AND cm.read_at IS NULL
              AND cm.is_deleted = FALSE;
        """
        # Pass doctor_user_id for the WHERE clause
        cursor.execute(query_unread_messages, (doctor_user_id,))
        result_messages = cursor.fetchone()
        dashboard_data['unread_messages'] = result_messages['count'] if result_messages else 0

    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error during doctor dashboard queries (User ID: {doctor_user_id}): {err}")
        flash("An error occurred loading some dashboard data.", "danger")
    except Exception as e:
        current_app.logger.error(f"Unexpected error during doctor dashboard queries (User ID: {doctor_user_id}): {e}", exc_info=True)
        flash("An unexpected error occurred loading dashboard data.", "danger")
    finally:
        # Ensure cursor and connection are closed
        if cursor:
            try: cursor.close()
            except Exception as cur_err: current_app.logger.error(f"Error closing dashboard cursor: {cur_err}")
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as conn_err: current_app.logger.error(f"Error closing dashboard connection: {conn_err}")

    # Render the template with the collected data
    # The template helper 'format_timedelta_as_time' should be registered globally for Jinja
    return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)


# --- Other Placeholder Routes (Removed - Implement in respective blueprints) ---
# It's better practice to define these routes within their dedicated blueprints
# (e.g., patients.py, appointments.py, messaging.py, settings.py)
# rather than having placeholder redirects here.