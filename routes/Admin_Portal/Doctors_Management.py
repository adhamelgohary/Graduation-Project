# Doctors_Management.py
# Relies on DB connection having autocommit=True. Uses explicit commits in key areas.
# WARNING: Uses plain text passwords - highly insecure for production.
# Uses a two-step creation process assuming a DB trigger creates the initial doctors record.

import os
import datetime # Ensure datetime is imported
from flask import (Blueprint, render_template, request, flash, redirect, url_for,
                   Response, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
# Removed: from werkzeug.security import generate_password_hash
from db import get_db_connection
from math import ceil
import mysql.connector # For error handling

Doctors_Management = Blueprint('Doctors_Management', __name__)

# --- Constants ---
PER_PAGE_DOCTORS = 10
ALLOWED_DOCTOR_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'specialization', 'license_number',
    'verification_status', 'created_at'
}
# Ensure UPLOAD_FOLDER is configured in Flask app config

# --- Helper Functions ---

def get_doctor_details(doctor_id):
    """Fetches combined user and doctor details, including documents."""
    connection = None
    cursor = None
    doctor_data = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in get_doctor_details {doctor_id}")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        # Get core details (NO password)
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone,
                   u.account_status, u.created_at, d.*
            FROM users u JOIN doctors d ON u.user_id = d.user_id
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """, (doctor_id,))
        doctor_data = cursor.fetchone()
        if not doctor_data:
            current_app.logger.warning(f"Doctor not found for ID {doctor_id} in get_doctor_details")
            return None
        # Get documents
        cursor.execute("""SELECT document_id, document_type, file_name, file_path, upload_date, file_size
                          FROM doctor_documents WHERE doctor_id = %s ORDER BY upload_date DESC""", (doctor_id,))
        doctor_data['documents'] = cursor.fetchall()
        # Format dates if needed
        if doctor_data.get('license_expiration') and isinstance(doctor_data['license_expiration'], (datetime.date, datetime.datetime)):
             doctor_data['license_expiration_formatted'] = doctor_data['license_expiration'].strftime('%Y-%m-%d')
        else: doctor_data['license_expiration_formatted'] = ''
        return doctor_data
    except Exception as e:
        current_app.logger.error(f"Error fetching doctor details for {doctor_id}: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

def get_user_basic_info(user_id, expected_type='doctor'):
    """Fetches basic user info (username, names) for display, checking type."""
    connection = None
    cursor = None
    user_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for basic user info")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id, username, first_name, last_name, user_type
            FROM users
            WHERE user_id = %s
        """, (user_id,))
        user_info = cursor.fetchone()
        if user_info and user_info.get('user_type') != expected_type:
            current_app.logger.warning(f"User {user_id} found but type is '{user_info.get('user_type')}', expected '{expected_type}'.")
            return None
        current_app.logger.debug(f"get_user_basic_info for {user_id} (type {expected_type}) found: {user_info}")
    except Exception as e:
        current_app.logger.error(f"Error fetching basic info for user ID {user_id}: {e}")
        user_info = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user_info


def get_current_user_id_int():
    """Safely gets the user ID as an integer from Flask-Login's current_user."""
    user_id_str = getattr(current_user, 'id', None) # Use 'id'
    user_id_int = None
    if user_id_str is not None:
        try:
            user_id_int = int(user_id_str)
        except (ValueError, TypeError):
            current_app.logger.error(f"Could not convert current_user.id '{user_id_str}' to integer.")
    return user_id_int

# --- Routes ---

@Doctors_Management.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    """Displays a paginated list of doctors with search and sort."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by = request.args.get('sort_by', 'last_name').lower()
    if sort_by not in ALLOWED_DOCTOR_SORT_COLUMNS: sort_by = 'last_name'
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

    connection = None
    cursor = None
    doctors = []
    total_items = 0
    total_pages = 0
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in doctor index")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        # --- Query Building ---
        base_query = """ FROM users u JOIN doctors d ON u.user_id = d.user_id WHERE u.user_type = 'doctor' """
        params = []
        search_clause = ""
        if search_term:
            search_clause = """ AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s
                                OR d.specialization LIKE %s OR d.license_number LIKE %s
                                OR d.verification_status LIKE %s) """
            like_term = f"%{search_term}%"; params.extend([like_term] * 6)

        # Count total
        count_query = f"SELECT COUNT(u.user_id) as total {base_query} {search_clause}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_DOCTORS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_DOCTORS

        # Determine sort column prefix
        sort_prefix = "d." if sort_by in ['specialization', 'license_number', 'verification_status'] else "u."
        if sort_by == 'created_at': sort_prefix = "u."

        # Construct final data query (No password)
        data_query = f""" SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.created_at,
                           d.specialization, d.license_number, d.verification_status
                           {base_query} {search_clause} ORDER BY {sort_prefix}{sort_by} {sort_order}
                           LIMIT %s OFFSET %s """
        final_params = params + [PER_PAGE_DOCTORS, offset]
        cursor.execute(data_query, tuple(final_params)); doctors = cursor.fetchall()

    except Exception as e:
        flash(f"Database error fetching doctors: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching doctor list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Doctors/view_doctors.html',
        doctors=doctors, page=page, total_pages=total_pages, per_page=PER_PAGE_DOCTORS,
        total_items=total_items, search_term=search_term, sort_by=sort_by, sort_order=sort_order
    )

@Doctors_Management.route('/admin/doctors/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    doctor = get_doctor_details(doctor_id)
    if not doctor:
        flash("Doctor not found.", "danger") # Helper no longer flashes
        return redirect(url_for('Doctors_Management.index'))
    return render_template('Admin_Portal/Doctors/doctor_details.html', doctor=doctor)

# --- Add Doctor Step 1 ---

@Doctors_Management.route('/admin/doctors/add/step1', methods=['GET'])
@login_required
def add_doctor_step1_form():
    """Displays Step 1 of the add doctor form (User details)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data={})

@Doctors_Management.route('/admin/doctors/add/step1', methods=['POST'])
@login_required
def add_doctor_step1():
    """Processes Step 1: Creates the user record (plain text pass)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    username = request.form.get('username')
    email = request.form.get('email')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None
    temp_password = os.urandom(10).hex() # Consider better method

    form_data_for_render = request.form.copy()

    if not all([username, email, first_name, last_name]):
        flash("Missing required fields (Username, Email, First Name, Last Name).", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

    connection = None
    cursor = None
    user_id = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email or Username already exists.", "danger")
            return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name,
                              user_type, phone, account_status)
            VALUES (%s, %s, %s, %s, %s, 'doctor', %s, 'active')
        """, (username, email, temp_password, first_name, last_name, phone))

        user_id = cursor.lastrowid
        connection.commit() # Explicit commit after insert

        if not user_id:
             current_app.logger.error(f"Failed to get lastrowid for doctor user {username} after commit.")
             flash("Error: User seemed to be created but could not retrieve ID.", "danger")
             return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

        current_app.logger.info(f"Step 1: Committed doctor user insert for {username}. lastrowid = {user_id}. Redirecting to Step 2.")
        current_app.logger.warning(f"Temporary password for doctor {username} (ID: {user_id}): {temp_password}") # SECURITY RISK

        flash("Step 1 complete: Doctor user account created. Now add specific doctor details.", "info")
        return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error creating user: {db_err}", "danger")
        current_app.logger.error(f"DB Error adding doctor user (step 1) for {username}: {db_err}")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error adding doctor user (step 1) for {username}: {e}")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('Doctors_Management.add_doctor_step1_form'))

# --- Add Doctor Step 2 ---

@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['GET'])
@login_required
def add_doctor_step2_form(user_id):
    """Displays Step 2 of the add doctor form (Doctor specifics)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    current_app.logger.info(f"Doctor Step 2 Form (GET): Received request for user_id = {user_id}")
    user_info = get_user_basic_info(user_id, expected_type='doctor')

    if not user_info:
        current_app.logger.error(f"Doctor Step 2 Form (GET): Doctor user info not found or wrong type for ID {user_id}.")
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Pass current year for the graduation year max value
    current_year = datetime.datetime.now().year

    return render_template(
        'Admin_Portal/Doctors/add_doctor_step2.html',
        user=user_info,
        form_data={},
        current_year=current_year # Pass current year
    )

@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['POST'])
@login_required
def add_doctor_step2(user_id):
    """Processes Step 2: Updates the doctor record with specific details."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    specialization = request.form.get('specialization')
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state') or None
    license_expiration = request.form.get('license_expiration') or None
    npi_number = request.form.get('npi_number') or None
    medical_school = request.form.get('medical_school') or None
    graduation_year = request.form.get('graduation_year') or None
    certifications = request.form.get('certifications') or None
    biography = request.form.get('biography') or None
    clinic_address = request.form.get('clinic_address') or None
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0

    # Get current year for re-rendering
    current_year = datetime.datetime.now().year

    if not all([specialization, license_number, license_state, license_expiration]):
        flash("Missing required doctor details (Specialization, License Number, State, Expiration).", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info,
                               form_data=request.form,
                               current_year=current_year) # Pass year on error

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        if npi_number:
             cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, user_id))
             if cursor.fetchone():
                  flash("NPI number already exists for another doctor.", "danger")
                  return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                                         user=user_info,
                                         form_data=request.form,
                                         current_year=current_year) # Pass year on error

        cursor.execute("""
            UPDATE doctors SET
                specialization = %s, license_number = %s, license_state = %s,
                license_expiration = %s, accepting_new_patients = %s, npi_number = %s,
                medical_school = %s, graduation_year = %s, certifications = %s,
                biography = %s, clinic_address = %s
            WHERE user_id = %s
        """, (specialization, license_number, license_state,
              license_expiration, accepting_new_patients, npi_number,
              medical_school, graduation_year, certifications, biography,
              clinic_address, user_id))

        rows_affected = cursor.rowcount
        connection.commit()

        if rows_affected == 0:
             current_app.logger.warning(f"Step 2 (POST): Update doctor details for user {user_id} affected 0 rows.")
             flash("Warning: Doctor details could not be updated (no changes or record missing?).", "warning")
             return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))
        else:
            current_admin_id = get_current_user_id_int()
            if current_admin_id:
                try:
                    cursor.execute("""
                        INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                        VALUES (%s, 'doctor_created', 'Doctor details added by admin (Step 2)', %s)
                    """, (user_id, current_admin_id))
                    connection.commit()
                except Exception as audit_err:
                    current_app.logger.error(f"Failed to add audit log for doctor step 2 {user_id}: {audit_err}")

            current_app.logger.info(f"Step 2 (POST): Successfully updated doctor details for user {user_id}.")
            flash("Doctor account created and details added successfully. Account pending verification.", "success")

        return redirect(url_for('Doctors_Management.index'))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error saving doctor details: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating doctor details (step 2) for user ID {user_id}: {db_err}")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info, form_data=request.form, current_year=current_year) # Pass year on error
    except Exception as e:
        flash(f"Error saving doctor details: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating doctor details (step 2) for user ID {user_id}: {e}")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info, form_data=request.form, current_year=current_year) # Pass year on error
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))


# --- Edit Doctor ---

@Doctors_Management.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    """Processes editing of doctor details (plain text pass)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    redirect_target = url_for('Doctors_Management.view_doctor', doctor_id=doctor_id)
    current_year = datetime.datetime.now().year # Get current year for max graduation year

    if request.method == 'GET':
        doctor_for_render = get_doctor_details(doctor_id)
        if not doctor_for_render:
             flash("Doctor not found.", "danger")
             return redirect(url_for('Doctors_Management.index'))
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=doctor_for_render,
                               form_data=doctor_for_render, # Use current data for initial form
                               current_year=current_year)

    # --- POST Logic ---
    current_doctor_data = get_doctor_details(doctor_id)
    if not current_doctor_data:
        flash("Cannot edit doctor: Doctor not found.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Prepare data for re-rendering, including data not in form
    form_data_for_render = request.form.to_dict()
    form_data_for_render['user_id'] = doctor_id
    form_data_for_render['accepting_new_patients'] = 1 if request.form.get('accepting_new_patients') else 0
    form_data_for_render['license_expiration_formatted'] = request.form.get('license_expiration') or ''
    form_data_for_render['documents'] = current_doctor_data.get('documents', [])
    # Include fields not editable in the form but needed for display context
    form_data_for_render['username'] = current_doctor_data.get('username')
    form_data_for_render['account_status'] = current_doctor_data.get('account_status')
    form_data_for_render['created_at'] = current_doctor_data.get('created_at')
    form_data_for_render['verification_status'] = current_doctor_data.get('verification_status')


    try:
        # Extract Form Data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone') or None
        specialization = request.form.get('specialization')
        license_number = request.form.get('license_number')
        license_state = request.form.get('license_state') or None
        license_expiration = request.form.get('license_expiration') or None
        npi_number = request.form.get('npi_number') or None
        medical_school = request.form.get('medical_school') or None
        graduation_year = request.form.get('graduation_year') or None
        certifications = request.form.get('certifications') or None
        biography = request.form.get('biography') or None
        clinic_address = request.form.get('clinic_address') or None
        accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Basic Validation
        if not all([first_name, last_name, email, specialization, license_number, license_state, license_expiration]):
             flash("Missing required fields (Name, Email, Specialization, License Details).", "danger")
             return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                    doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)

        # Password Change Logic
        update_password = False
        password_error = False
        if new_password or confirm_password:
            if not new_password or not confirm_password:
                 flash("Both New Password and Confirm Password are required to change password.", "warning")
                 password_error = True
            elif new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                password_error = True
            else:
                update_password = True
        if password_error:
             form_data_for_render['new_password'] = '' # Clear passwords
             form_data_for_render['confirm_password'] = ''
             return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                    doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)

        # DB Interaction
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        # Pre-checks (email, NPI uniqueness)
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, doctor_id))
        email_exists = cursor.fetchone()
        npi_exists = None
        if npi_number:
             cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, doctor_id))
             npi_exists = cursor.fetchone()

        if email_exists:
            flash("Email address already in use by another user.", "danger")
            return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)
        if npi_exists:
             flash("NPI Number already in use by another doctor.", "danger")
             return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)

        # Perform Updates
        user_update_query = "UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s"
        user_params = [first_name, last_name, email, phone]
        if update_password:
            user_update_query += ", password = %s"; user_params.append(new_password)
        user_update_query += " WHERE user_id = %s AND user_type = 'doctor'"; user_params.append(doctor_id)
        cursor.execute(user_update_query, tuple(user_params))
        user_rows_affected = cursor.rowcount

        cursor.execute("""
            UPDATE doctors SET specialization = %s, license_number = %s,
                license_state = %s, license_expiration = %s,
                accepting_new_patients = %s, npi_number = %s,
                medical_school = %s, graduation_year = %s,
                certifications = %s, biography = %s, clinic_address = %s
            WHERE user_id = %s
        """, (specialization, license_number, license_state,
              license_expiration, accepting_new_patients, npi_number,
              medical_school, graduation_year, certifications, biography,
              clinic_address, doctor_id))
        doctor_rows_affected = cursor.rowcount

        connection.commit() # Commit updates

        # Audit log
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            current_admin_id = get_current_user_id_int()
            if current_admin_id:
                try:
                     cursor.execute("""
                         INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                         VALUES (%s, 'doctor_updated', 'Doctor profile updated by admin', %s)
                     """, (doctor_id, current_admin_id))
                     connection.commit() # Commit audit log
                except Exception as audit_err:
                     current_app.logger.error(f"Failed to add audit log for doctor edit {doctor_id}: {audit_err}")

        # Feedback
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            flash_msg = "Doctor updated successfully"
            if update_password: flash_msg += " (Password Changed)"
            flash(flash_msg, "success")
        else:
             flash("No changes detected for the doctor.", "info")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception: pass
        flash(f"Database error updating doctor: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating doctor {doctor_id}: {db_err}")
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)

    except Exception as e:
        flash(f"An error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating doctor {doctor_id}: {e}")
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year)

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)


# --- Document Management ---
# These functions assume UPLOAD_FOLDER is correctly configured in the main Flask app

@Doctors_Management.route('/admin/doctors/upload-document/<int:doctor_id>', methods=['POST'])
@login_required
def upload_doctor_document(doctor_id):
    """Handles document uploads for a specific doctor."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # Verify doctor exists before proceeding
    if not get_user_basic_info(doctor_id, expected_type='doctor'):
         flash("Doctor not found.", "danger")
         return redirect(url_for('Doctors_Management.index'))

    # --- File and Form Validation ---
    if 'document' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    file = request.files['document']
    document_type = request.form.get('document_type')

    if file.filename == '':
        flash('No file selected for upload.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    # Simple validation for allowed document types
    valid_document_types = ['license', 'certification', 'identity', 'education', 'other']
    if not document_type or document_type not in valid_document_types:
        flash('Invalid or missing document type specified.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    connection = None
    cursor = None
    saved_file_path_abs = None # Store absolute path for potential cleanup
    relative_path_for_db = None # Store relative path for DB insertion

    try:
        # --- Get Upload Path Configuration ---
        upload_folder_base = current_app.config.get('UPLOAD_FOLDER')
        if not upload_folder_base:
             # Log critical error and inform user
             current_app.logger.critical("UPLOAD_FOLDER configuration missing in Flask app!")
             raise ValueError("File upload configuration error. Please contact administrator.")

        # --- Prepare File Paths ---
        # Create a relative subdirectory path (e.g., 'doctor_docs/123')
        doctor_upload_subdir = os.path.join('doctor_docs', str(doctor_id))
        # Create the absolute path for saving the file on the server
        doctor_upload_path_abs = os.path.join(upload_folder_base, doctor_upload_subdir)
        # Ensure the target directory exists
        os.makedirs(doctor_upload_path_abs, exist_ok=True)

        # --- Create Secure and Unique Filename ---
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
        # Use secure_filename to prevent directory traversal attacks
        safe_original_filename = secure_filename(file.filename)
        unique_filename = f"{timestamp}_{safe_original_filename}"

        # --- Define Paths for Saving and Database ---
        saved_file_path_abs = os.path.join(doctor_upload_path_abs, unique_filename) # Full path to save file
        relative_path_for_db = os.path.join(doctor_upload_subdir, unique_filename) # Path to store in DB

        # --- Save the File ---
        current_app.logger.info(f"Attempting to save document to: {saved_file_path_abs}")
        file.save(saved_file_path_abs)
        file_size = os.path.getsize(saved_file_path_abs)
        current_app.logger.info(f"Successfully saved {unique_filename} ({file_size} bytes)")

        # --- Update Database ---
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed after file save.")
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO doctor_documents
            (doctor_id, document_type, file_name, file_path, file_size, upload_date)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (doctor_id, document_type, unique_filename, relative_path_for_db, file_size)) # Store relative path

        connection.commit() # Commit document record
        current_app.logger.info(f"Successfully inserted document record for {unique_filename} into DB.")

        # --- Add Audit Log ---
        current_admin_id = get_current_user_id_int()
        if current_admin_id:
            try:
                # Re-use cursor or get a new one if needed
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                    VALUES (%s, 'document_upload', %s, %s)
                """, (doctor_id, f"Admin uploaded {document_type} document: {unique_filename}", current_admin_id))
                connection.commit() # Commit audit log separately
            except Exception as audit_err:
                 current_app.logger.error(f"Failed to add audit log for doc upload {doctor_id}, file {unique_filename}: {audit_err}")
                 # Non-critical error, don't rollback main action

        flash("Document uploaded successfully.", "success")

    except ValueError as ve: # Catch specific config error
        flash(str(ve), "danger") # Show specific error message
        current_app.logger.error(f"Configuration error during doc upload for {doctor_id}: {ve}")
    except mysql.connector.Error as db_err:
        # Attempt rollback if connection exists
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err:
            current_app.logger.error(f"Rollback attempt failed after DB error: {rb_err}")
        flash(f"Database error saving document record: {db_err}", "danger")
        current_app.logger.error(f"DB error uploading doc record for {doctor_id}, file {unique_filename if 'unique_filename' in locals() else 'N/A'}: {db_err}")
        # Attempt to clean up the file if DB insertion failed but file was saved
        if saved_file_path_abs and os.path.exists(saved_file_path_abs):
             flash("Physical file was saved, but the database update failed.", "warning")
             try:
                 os.remove(saved_file_path_abs)
                 current_app.logger.info(f"Cleaned up orphaned file on DB error: {saved_file_path_abs}")
             except OSError as cleanup_err:
                 current_app.logger.error(f"Error removing orphaned file {saved_file_path_abs} on DB error: {cleanup_err}")

    except Exception as e:
        # Catch all other exceptions (e.g., file saving errors, permission errors)
        flash(f"An unexpected error occurred during upload: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error uploading doc for {doctor_id}: {e}", exc_info=True) # Log full traceback
        # Attempt to clean up the file if it was saved before the error occurred
        if saved_file_path_abs and os.path.exists(saved_file_path_abs):
             try:
                 os.remove(saved_file_path_abs)
                 current_app.logger.info(f"Cleaned up file on general error: {saved_file_path_abs}")
             except OSError as cleanup_error:
                 current_app.logger.error(f"Error cleaning up file {saved_file_path_abs} on general error: {cleanup_error}")

    finally:
    # Ensure resources are closed
        if cursor: # Check if cursor was assigned
            try:
                cursor.close()
            except Exception as close_err:
                current_app.logger.error(f"Error closing cursor during doc upload: {close_err}")
        if connection and connection.is_connected(): # Check connection exists and is connected
            try:
                connection.close()
            except Exception as conn_close_err:
                current_app.logger.error(f"Error closing connection during doc upload: {conn_close_err}")

    # Redirect back to the doctor's view page regardless of success/failure within the try block
    return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))


@Doctors_Management.route('/admin/doctors/delete-document/<int:document_id>', methods=['POST'])
@login_required
def delete_doctor_document(document_id):
    """Deletes a document record and the associated file."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    doc_info = None
    doctor_id_redirect = None # Initialize for redirection

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")

        # 1. Retrieve document details FIRST to get file path and doctor_id
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""SELECT dd.doctor_id, dd.file_path, dd.document_type, dd.file_name, u.user_type
                          FROM doctor_documents dd JOIN users u ON dd.doctor_id = u.user_id
                          WHERE dd.document_id = %s""", (document_id,))
        doc_info = cursor.fetchone()
        cursor.close(); cursor = None # Close dict cursor immediately

        if not doc_info:
            flash("Document not found.", "danger")
            return redirect(request.referrer or url_for('Doctors_Management.index')) # Use referrer as fallback

        # Check if the document belongs to a valid doctor
        if doc_info.get('user_type') != 'doctor':
             flash("Document does not belong to a doctor.", "warning")
             return redirect(request.referrer or url_for('Doctors_Management.index'))

        doctor_id_redirect = doc_info['doctor_id'] # Store for final redirect

        # 2. Delete document record from database
        cursor = connection.cursor() # Re-open standard cursor for DELETE
        cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s", (document_id,))
        deleted_rows = cursor.rowcount
        connection.commit() # Commit DB delete
        current_app.logger.info(f"Attempted DB delete for document ID {document_id}. Rows affected: {deleted_rows}")

        # 3. Proceed only if DB deletion was successful
        if deleted_rows > 0:
             # Add audit log entry
             current_admin_id = get_current_user_id_int()
             if current_admin_id:
                 try:
                     # Can reuse the standard cursor
                     cursor.execute("""
                         INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                         VALUES (%s, 'document_deleted', %s, %s)
                     """, (doc_info['doctor_id'], f"Admin deleted {doc_info.get('document_type','N/A')} doc: {doc_info.get('file_name', 'N/A')}", current_admin_id))
                     connection.commit() # Commit audit log
                 except Exception as audit_err:
                      current_app.logger.error(f"Failed to add audit log for doc delete {document_id}: {audit_err}")
                      # Continue deletion even if audit log fails

             # 4. Try deleting file from filesystem AFTER successful DB commit
             file_path_relative = doc_info.get('file_path')
             file_path_absolute = None
             upload_folder_base = current_app.config.get('UPLOAD_FOLDER')

             if not upload_folder_base:
                 current_app.logger.error("UPLOAD_FOLDER not configured, cannot delete document file.")
                 flash("Document record deleted, but could not delete file (server configuration error).", "warning")
             elif file_path_relative:
                 file_path_absolute = os.path.join(upload_folder_base, file_path_relative)
                 try:
                     if os.path.exists(file_path_absolute):
                         os.remove(file_path_absolute)
                         flash("Document deleted successfully (Record and File).", "success")
                         current_app.logger.info(f"Successfully deleted document file: {file_path_absolute}")
                     else:
                         current_app.logger.warning(f"File path record existed, but file not found on disk for deleted doc ID {document_id}: {file_path_absolute}")
                         flash(f"Document record deleted, but the physical file was not found at the expected location.", "warning")
                 except OSError as e:
                     current_app.logger.error(f"Error deleting file {file_path_absolute}: {e}")
                     flash(f"Document record deleted, but failed to delete the physical file: {e}", "warning")
             else:
                 # No file path was stored in the DB
                 flash("Document record deleted successfully (No associated file path was recorded).", "success")
                 current_app.logger.info(f"Document record {document_id} deleted, no file path in DB.")
        else:
             # DB delete affected 0 rows
             flash("Document record was already deleted or not found.", "warning")

    except mysql.connector.Error as db_err:
        # Attempt rollback if connection exists
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err:
            current_app.logger.error(f"Rollback attempt failed after DB error: {rb_err}")
        flash(f"Database error during document deletion: {db_err}", "danger")
        current_app.logger.error(f"DB error deleting doc record {document_id}: {db_err}")
    except Exception as e:
        # Catch other potential errors (like ConnectionError early on)
        flash(f"An error occurred while deleting the document: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB error deleting doc {document_id}: {e}", exc_info=True)
    finally:
    # Ensure cursor and connection are closed
        if cursor: # Check if cursor was assigned (it might error before assignment)
            try:
                cursor.close()
            except Exception as close_err:
                current_app.logger.error(f"Error closing cursor during doc delete: {close_err}")
        if connection and connection.is_connected():
            try:
                connection.close()
            except Exception as conn_close_err:
                current_app.logger.error(f"Error closing connection during doc delete: {conn_close_err}")

    # Redirect back to the doctor's view page using the stored ID
    if doctor_id_redirect:
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id_redirect))
    else:
        # Fallback redirect if doctor_id couldn't be determined (e.g., error before fetching doc_info)
        return redirect(request.referrer or url_for('Doctors_Management.index'))


# --- Delete Doctor ---

@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['GET'])
@login_required
def delete_doctor_confirmation(doctor_id):
     """Displays confirmation page before deleting a doctor."""
     if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login'))

     doctor_info = get_user_basic_info(doctor_id, expected_type='doctor')
     if not doctor_info:
          flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

     return render_template('Admin_Portal/Doctors/delete_doctor_confirmation.html', doctor=doctor_info)


@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    """Processes deletion of a doctor and associated data/files."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login'))

    connection = None
    cursor = None
    deleted_rows = 0
    documents_to_delete = []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")

        # 1. Get list of document file paths
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT document_id, file_path FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        documents_to_delete = cursor_dict.fetchall()
        cursor_dict.close()

        # 2. Delete DB records (dependents first, then doctor, then user)
        cursor = connection.cursor()
        current_app.logger.info(f"Attempting deletion for doctor ID: {doctor_id}")

        # Delete dependents explicitly (safer if no CASCADE)
        cursor.execute("DELETE FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        current_app.logger.debug(f"Deleted {cursor.rowcount} rows from doctor_documents")
        # Add other tables like reviews, appointments, availability if they don't cascade
        # ...

        cursor.execute("DELETE FROM doctors WHERE user_id = %s", (doctor_id,))
        current_app.logger.debug(f"Deleted {cursor.rowcount} rows from doctors")

        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'doctor'", (doctor_id,))
        deleted_rows = cursor.rowcount
        current_app.logger.debug(f"Deleted {deleted_rows} rows from users")

        connection.commit() # Commit all DB deletions

        # 3. Audit log (if user was deleted)
        if deleted_rows > 0:
            current_admin_id = get_current_user_id_int()
            if current_admin_id:
                 try:
                     cursor.execute("""
                        INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                        VALUES (%s, 'doctor_deleted', 'Admin deleted doctor account and associated data', %s)
                     """, (doctor_id, current_admin_id))
                     connection.commit()
                 except Exception as audit_err:
                      current_app.logger.error(f"Failed to add audit log for doctor delete {doctor_id}: {audit_err}")

            # 4. Delete files from filesystem AFTER successful DB commit
            files_deleted_count = 0
            files_error_count = 0
            upload_folder_base = current_app.config.get('UPLOAD_FOLDER')
            if upload_folder_base:
                 for doc in documents_to_delete:
                      file_path_relative = doc.get('file_path')
                      file_path_absolute = None
                      if file_path_relative:
                           file_path_absolute = os.path.join(upload_folder_base, file_path_relative)
                      try:
                           if file_path_absolute and os.path.exists(file_path_absolute):
                                os.remove(file_path_absolute); files_deleted_count += 1
                           elif file_path_absolute:
                               current_app.logger.warning(f"File path not found for deleted doctor {doctor_id}, doc {doc.get('document_id')}: {file_path_absolute}")
                      except OSError as e:
                           files_error_count += 1
                           current_app.logger.error(f"Error deleting file {file_path_absolute} for doctor {doctor_id}: {e}")

            # Provide feedback
            msg = "Doctor deleted successfully."
            if documents_to_delete:
                 if files_error_count > 0:
                      msg += f" However, {files_error_count} associated file(s) could not be deleted from storage."
                      flash(msg, "warning")
                 elif not upload_folder_base:
                      msg += " Could not delete files (UPLOAD_FOLDER not configured)."
                      flash(msg, "warning")
                 else:
                      msg += f" Associated files ({files_deleted_count}) also deleted."
                      flash(msg, "success")
            else:
                 flash(msg, "success")
        else:
            flash("Doctor not found or already deleted.", "warning")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception: pass
        flash(f"Database error deleting doctor: {db_err}", "danger")
        current_app.logger.error(f"DB Error deleting doctor {doctor_id}: {db_err}")
    except Exception as e:
        flash(f"Error deleting doctor: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error deleting doctor {doctor_id}: {e}")

    finally:
    # Ensure all potential cursors and connection are closed
        if 'cursor_dict' in locals() and cursor_dict: # Check if it exists and was assigned
            try:
                cursor_dict.close()
            except Exception as close_err:
                current_app.logger.error(f"Error closing dict_cursor during doctor delete: {close_err}")
        if cursor: # Check if main cursor was assigned
            try:
                cursor.close()
            except Exception as close_err:
                current_app.logger.error(f"Error closing main cursor during doctor delete: {close_err}")
        if connection and connection.is_connected():
            try:
                connection.close()
            except Exception as conn_close_err:
                current_app.logger.error(f"Error closing connection during doctor delete: {conn_close_err}")

    return redirect(url_for('Doctors_Management.index'))