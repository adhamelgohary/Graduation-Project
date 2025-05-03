# routes/Website/doctor.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app
)
# Import current_user to check authentication status
from flask_login import current_user
import mysql.connector
from db import get_db_connection
from math import ceil # Not used here currently, but keep if pagination added later

# Define the blueprint
doctor_bp = Blueprint(
    'doctor',
    __name__,
    template_folder='../../templates/Website',
    url_prefix='/doctors'
)

# --- Helper Functions (Keep as before or move to utils) ---

def get_specializations_list():
    """Fetches ID and Name for all specializations for filters."""
    conn = None; cursor = None; specializations = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT specialization_id, name FROM specializations WHERE name NOT IN ('Unknown', 'Other') ORDER BY name ASC"
        cursor.execute(query)
        specializations = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching specializations list: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specializations

def get_departments_list():
    """Fetches ID and Name for all departments for filters."""
    conn = None; cursor = None; departments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT department_id, name FROM departments WHERE name != 'Other/Unspecified' ORDER BY name ASC"
        cursor.execute(query)
        departments = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching departments list: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return departments

def get_filtered_doctors(search_name=None, specialization_id=None, department_id=None):
    """ Fetches approved doctors based on filter criteria with case-insensitive name search. """
    doctors_list = []
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name,
                d.profile_photo_url,
                s.name AS specialization_name,
                dept.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            WHERE u.user_type = 'doctor'
              AND u.account_status = 'active'
              AND d.verification_status = 'approved'
        """
        params = []

        if search_name:
            query += " AND (LOWER(u.first_name) LIKE LOWER(%s) OR LOWER(u.last_name) LIKE LOWER(%s))"
            like_term = f"%{search_name}%"
            params.extend([like_term, like_term])
        if specialization_id:
            query += " AND d.specialization_id = %s"
            params.append(specialization_id)
        if department_id:
            query += " AND d.department_id = %s"
            params.append(department_id)

        query += " ORDER BY u.last_name ASC, u.first_name ASC"
        cursor.execute(query, tuple(params))
        doctors_list = cursor.fetchall()

        default_pic = 'images/default_doctor.png'
        for doc in doctors_list:
            raw_path = doc.get('profile_photo_url')
            if raw_path and not raw_path.startswith('/') and not raw_path.startswith(('http://', 'https://')):
                doc['profile_picture_processed_url'] = raw_path
            else:
                doc['profile_picture_processed_url'] = default_pic
    except Exception as e:
        current_app.logger.error(f"Error fetching filtered doctors: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctors_list

def get_full_doctor_profile(doctor_id):
    """Fetches detailed profile information for a single approved, active doctor."""
    conn = None; cursor = None; doctor_profile = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name, u.email, u.phone,
                d.profile_photo_url, d.biography, d.accepting_new_patients,
                d.clinic_address, d.certifications,
                s.name AS specialization_name,
                dept.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            WHERE u.user_id = %s
              AND u.user_type = 'doctor'
              AND u.account_status = 'active'
              AND d.verification_status = 'approved'
        """
        cursor.execute(query, (doctor_id,))
        doctor_profile = cursor.fetchone()

        if doctor_profile:
            raw_path = doctor_profile.get('profile_photo_url')
            default_pic = 'images/default_doctor.png'
            if raw_path and not raw_path.startswith('/') and not raw_path.startswith(('http://', 'https://')):
                doctor_profile['profile_picture_processed_url'] = raw_path
            else:
                doctor_profile['profile_picture_processed_url'] = default_pic
    except Exception as e:
        current_app.logger.error(f"Error fetching full doctor profile for ID {doctor_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_profile


# --- Route to Display Doctors List (Public) ---
@doctor_bp.route('/')
@doctor_bp.route('/list')
def list_doctors():
    """Displays the filterable list of doctors."""
    search_name = request.args.get('search_name', '').strip()
    specialization_id = request.args.get('specialization_id', type=int)
    department_id = request.args.get('department_id', type=int)

    all_specializations = get_specializations_list()
    all_departments = get_departments_list()
    doctors = get_filtered_doctors(search_name, specialization_id, department_id)

    # Check login status to control modal display
    is_logged_in = current_user.is_authenticated

    return render_template(
        'doctor_list.html',
        doctors=doctors,
        specializations=all_specializations,
        departments=all_departments,
        selected_name=search_name,
        selected_spec_id=specialization_id,
        selected_dept_id=department_id,
        is_logged_in=is_logged_in # Pass status for modal JS
    )

# --- Route to Display Doctor Profile (Public) ---
# NO @login_required here
@doctor_bp.route('/profile/<int:doctor_id>')
def view_doctor_profile(doctor_id):
    """Displays the detailed profile page for a single doctor."""
    doctor = get_full_doctor_profile(doctor_id)

    if not doctor:
        flash("Doctor profile not found or unavailable.", "warning")
        return redirect(url_for('.list_doctors'))

    # Check login status to control modal display on this page
    is_logged_in = current_user.is_authenticated

    return render_template(
        'doctor_profile.html',
        doctor=doctor,
        is_logged_in=is_logged_in # Pass status for modal JS
        )