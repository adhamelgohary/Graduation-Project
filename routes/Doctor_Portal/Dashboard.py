# routes/Doctor_Portal/Dashboard.py
import mysql.connector
from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection
from utils.template_helpers import format_timedelta_as_time # Assuming this is correctly registered
from datetime import timedelta, datetime, date, time

from .utils import (
    check_doctor_authorization,
    get_provider_id,
    get_doctor_details
    # Add other specific utils if they become necessary for dashboard enhancements
)

doctor_main = Blueprint(
    'doctor_main',
    __name__,
    url_prefix='/doctor',
    template_folder='../../templates'
)

@doctor_main.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    if not check_doctor_authorization(current_user):
        flash("Access denied. You must be logged in as a doctor.", "warning")
        return redirect(url_for('login.login_route')) # Adjust to your actual login route

    doctor_user_id = current_user.id

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
        dashboard_data['doctor_info'] = get_doctor_details(doctor_user_id)
        if not dashboard_data['doctor_info']:
             current_app.logger.warning(f"Doctor profile details not found for user_id {doctor_user_id}.")

        conn = get_db_connection()
        if not conn or not conn.is_connected():
             current_app.logger.error(f"DB connection failed for doctor dashboard (User ID: {doctor_user_id})")
             flash("Database connection error. Cannot load dashboard data.", "danger")
             return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)

        cursor = conn.cursor(dictionary=True)

        # Upcoming Appointments
        query_appointments = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                at.type_name AS appointment_types, a.status,
                p_user.first_name AS patient_first_name,
                p_user.last_name AS patient_last_name,
                a.patient_id AS patient_user_id
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
            WHERE a.doctor_id = %s
              AND a.appointment_date >= CURDATE()
              AND a.status IN ('scheduled', 'confirmed', 'rescheduled')
            ORDER BY a.appointment_date ASC, a.start_time ASC
            LIMIT 5;
        """
        cursor.execute(query_appointments, (doctor_user_id,))
        dashboard_data['upcoming_appointments'] = cursor.fetchall()

        # Appointments Today Count
        query_today_count = """
            SELECT COUNT(appointment_id) as count FROM appointments
            WHERE doctor_id = %s AND appointment_date = CURDATE()
            AND status NOT IN ('canceled', 'no-show', 'completed');
        """
        cursor.execute(query_today_count, (doctor_user_id,))
        result_today = cursor.fetchone()
        dashboard_data['appointments_today_count'] = result_today['count'] if result_today else 0

        # Patient Count
        query_patient_count = """
            SELECT COUNT(DISTINCT patient_id) AS count
            FROM appointments
            WHERE doctor_id = %s;
        """
        cursor.execute(query_patient_count, (doctor_user_id,))
        result_patients = cursor.fetchone()
        dashboard_data['patient_count'] = result_patients['count'] if result_patients else 0

        # Unread Message Count
        query_unread_messages = """
            SELECT COUNT(cm.message_id) AS count FROM chat_messages cm
            JOIN chats c ON cm.chat_id = c.chat_id
            WHERE c.doctor_id = %s
              AND cm.sender_type = 'patient'
              AND cm.read_at IS NULL
              AND cm.is_deleted = FALSE;
        """
        cursor.execute(query_unread_messages, (doctor_user_id,))
        result_messages = cursor.fetchone()
        dashboard_data['unread_messages'] = result_messages['count'] if result_messages else 0

    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error on doctor dashboard (User ID: {doctor_user_id}): {err}")
        flash("An error occurred loading some dashboard data.", "danger")
    except Exception as e:
        current_app.logger.error(f"Unexpected error on doctor dashboard (User ID: {doctor_user_id}): {e}", exc_info=True)
        flash("An unexpected error occurred loading dashboard data.", "danger")
    finally:
        if cursor:
            try: cursor.close()
            except Exception as cur_err: current_app.logger.error(f"Error closing dashboard cursor: {cur_err}")
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as conn_err: current_app.logger.error(f"Error closing dashboard connection: {conn_err}")

    return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)