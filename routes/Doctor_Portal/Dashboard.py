# routes/Doctor_Portal/Dashboard.py
import mysql.connector
from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection
# Assuming the import path is correct relative to app.py
# Ensure this helper exists and contains the 'format_timedelta_as_time' function
from utils.template_helpers import format_timedelta_as_time
from datetime import timedelta, datetime, date

# Define the Blueprint for doctor routes
doctor_main = Blueprint(
    'doctor_main',
    __name__,
    url_prefix='/doctor',
    template_folder='../../templates' # Adjust if templates are elsewhere relative to this file
)

# --- Helper Functions ---

def check_doctor_authorization(user):
    """Checks if the logged-in user is authenticated and is a doctor."""
    if not user or not user.is_authenticated:
        return False
    # Check user_type attribute exists before comparing
    return getattr(user, 'user_type', None) == 'doctor'

def get_doctor_details(doctor_user_id):
    """Fetches comprehensive doctor details joining users, doctors, specializations, and departments."""
    conn = None
    cursor = None
    doctor_info = None
    try:
        conn = get_db_connection()
        if conn is None:
            # Log the error: failed to get a connection object
            current_app.logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id}): Could not establish connection.")
            return None
        if not conn.is_connected():
             # Log the error: connection object exists but is not connected
             current_app.logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id}): Connection is not active.")
             # Attempt to close it just in case
             try: conn.close()
             except: pass
             return None

        cursor = conn.cursor(dictionary=True)

        # === THE CORRECTED QUERY ===
        # Ensure 'd.created_at' is completely removed from this SELECT list.
        query = """
            SELECT
                u.user_id, u.username, u.email, u.first_name, u.last_name,
                u.phone, u.country, u.account_status,
                u.created_at as user_created_at, -- User registration time
                d.user_id as doctor_user_id,
                d.specialization_id,
                s.name AS specialization_name,
                d.license_number, d.license_state, d.license_expiration,
                d.npi_number, d.medical_school, d.graduation_year, d.certifications,
                d.accepting_new_patients, d.biography, d.profile_photo_url,
                d.clinic_address, d.verification_status,
                d.department_id,
                dep.name AS department_name
                -- d.created_at WAS REMOVED FROM HERE
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        # Optional: Add debug logging right before execute if still having issues
        # current_app.logger.debug(f"Executing get_doctor_details query for user {doctor_user_id}")

        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone() # Fetch the single result

        # Explicitly consume any potential remaining results, just in case fetchone didn't get everything (unlikely for this query)
        # cursor.fetchall() # Usually not needed after fetchone on a single-row query

    except mysql.connector.Error as err:
        # Log the specific MySQL error
        current_app.logger.error(f"DB error in get_doctor_details for user_id {doctor_user_id}: {err}")
        return None # Return None on error
    except Exception as e:
        # Log any other unexpected errors
        current_app.logger.error(f"Unexpected error in get_doctor_details for user_id {doctor_user_id}: {e}", exc_info=True)
        return None # Return None on error
    finally:
        # Use separate try-except for closing cursor and connection
        if cursor:
            try:
                cursor.close()
            except Exception as cur_err:
                current_app.logger.error(f"Error closing cursor in get_doctor_details: {cur_err}", exc_info=False) # Log quietly
        if conn and conn.is_connected():
            try:
                conn.close()
            except Exception as conn_err:
                current_app.logger.error(f"Error closing connection in get_doctor_details: {conn_err}", exc_info=False) # Log quietly
    return doctor_info # Return the fetched info or None


# --- Dashboard Route ---
@doctor_main.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    # Check authorization first
    if not check_doctor_authorization(current_user):
        flash("Access denied. You must be logged in as a doctor.", "warning")
        return redirect(url_for('login.login_route')) # Verify this route name

    doctor_user_id = current_user.id

    # Initialize all expected data keys to prevent template errors
    dashboard_data = {
        'doctor_info': None,
        'upcoming_appointments': [],
        'patient_count': 0,
        'unread_messages': 0,
        'appointments_today_count': 0, # Initialize count for today
    }

    conn = None
    cursor = None

    try:
        # 1. Fetch Doctor Info (calls the corrected function above)
        dashboard_data['doctor_info'] = get_doctor_details(doctor_user_id)
        if not dashboard_data['doctor_info']:
             # Log warning, but proceed to try fetching other data
             current_app.logger.warning(f"Doctor profile details not found for user_id {doctor_user_id}. Dashboard may be incomplete.")

        # 2. Establish Connection for dashboard queries
        conn = get_db_connection()
        if conn is None or not conn.is_connected():
             current_app.logger.error(f"DB connection failed for doctor dashboard data (Doctor User ID: {doctor_user_id})")
             flash("Database connection error. Cannot load dashboard data.", "danger")
             # Render template with whatever data was fetched (maybe just doctor_info or nothing)
             return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)

        cursor = conn.cursor(dictionary=True)

        # 3. Fetch Upcoming Appointments
        query_appointments = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                a.appointment_type, a.status,
                p_user.first_name AS patient_first_name,
                p_user.last_name AS patient_last_name,
                a.patient_id AS patient_user_id
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            WHERE a.doctor_id = %s AND a.appointment_date >= CURDATE()
              AND a.status IN ('scheduled', 'confirmed', 'rescheduled')
            ORDER BY a.appointment_date ASC, a.start_time ASC LIMIT 5;
        """
        cursor.execute(query_appointments, (doctor_user_id,))
        dashboard_data['upcoming_appointments'] = cursor.fetchall() # Fetch all results

        # 3b. Fetch Appointments Today Count
        query_today_count = """
            SELECT COUNT(appointment_id) as count FROM appointments
            WHERE doctor_id = %s AND appointment_date = CURDATE()
            AND status NOT IN ('canceled', 'no-show', 'completed');
        """
        cursor.execute(query_today_count, (doctor_user_id,))
        result_today = cursor.fetchone() # Fetch the single count row
        dashboard_data['appointments_today_count'] = result_today['count'] if result_today else 0
        # cursor.fetchall() # Consume any potential remaining rows (unlikely for COUNT)

        # 4. Fetch Patient Count
        query_patient_count = "SELECT COUNT(DISTINCT patient_id) AS count FROM appointments WHERE doctor_id = %s;"
        cursor.execute(query_patient_count, (doctor_user_id,))
        result_patients = cursor.fetchone() # Fetch the single count row
        dashboard_data['patient_count'] = result_patients['count'] if result_patients else 0
        # cursor.fetchall() # Consume any potential remaining rows (unlikely for COUNT)

        # 5. Fetch Unread Message Count
        query_unread_messages = """
            SELECT COUNT(cm.message_id) AS count FROM chat_messages cm
            JOIN chats c ON cm.chat_id = c.chat_id
            WHERE c.doctor_id = %s AND cm.sender_type = 'patient'
            AND cm.read_at IS NULL AND cm.is_deleted = FALSE;
        """
        cursor.execute(query_unread_messages, (doctor_user_id,))
        result_messages = cursor.fetchone() # Fetch the single count row
        dashboard_data['unread_messages'] = result_messages['count'] if result_messages else 0
        # cursor.fetchall() # Consume any potential remaining rows (unlikely for COUNT)

    except mysql.connector.Error as err:
        # Log errors specifically from the dashboard queries
        current_app.logger.error(f"DB error during doctor dashboard queries (User ID: {doctor_user_id}): {err}")
        flash("An error occurred loading some dashboard data.", "danger")
        # Continue to finally block
    except Exception as e:
        # Log any other unexpected errors during dashboard queries
        current_app.logger.error(f"Unexpected error during doctor dashboard queries (User ID: {doctor_user_id}): {e}", exc_info=True)
        flash("An unexpected error occurred loading dashboard data.", "danger")
        # Continue to finally block
    finally:
        # Robust finally block to close cursor and connection
        cursor_closed_ok = False
        conn_closed_ok = False
        if cursor:
            try:
                # Optional: Consume remaining results before closing cursor if paranoid
                # while cursor.nextset(): pass # For stored procedures primarily
                # cursor.fetchall() # Consume any results from the *last* executed query if error happened before fetch
                cursor.close()
                cursor_closed_ok = True
            except mysql.connector.errors.InternalError as ie:
                if "Unread result found" in str(ie):
                    current_app.logger.warning(f"Cursor close for Doctor ID {doctor_user_id} encountered 'Unread result found'. Attempting connection close.")
                    cursor_closed_ok = True # Treat as handled for logging
                else:
                    current_app.logger.error(f"InternalError closing dashboard cursor for Doctor ID {doctor_user_id}: {ie}", exc_info=True)
            except Exception as cur_err:
                current_app.logger.error(f"Error closing dashboard cursor for Doctor ID {doctor_user_id}: {cur_err}", exc_info=True)

        if conn and conn.is_connected():
            try:
                conn.close()
                conn_closed_ok = True
            except Exception as conn_err:
                current_app.logger.error(f"Error closing dashboard connection for Doctor ID {doctor_user_id}: {conn_err}", exc_info=True)

        if not cursor_closed_ok or not conn_closed_ok:
             current_app.logger.warning(f"DB cleanup may not have completed cleanly for doctor dashboard (User ID: {doctor_user_id}). Cursor closed: {cursor_closed_ok}, Conn closed: {conn_closed_ok}")

    # Render the template with the collected data
    # Ensure the filter `timedelta_to_time` is globally registered in app.py using the correct function name
    return render_template('Doctor_Portal/Dashboard.html', **dashboard_data)