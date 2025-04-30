# Doctors_Management.py
# Relies on DB connection having autocommit=True by default, but uses explicit
# commits and rollbacks in critical sections for guaranteed data integrity.
# WARNING: Uses plain text passwords - highly insecure for production.
# Uses a two-step creation process - USER record created in step 1, trigger
# creates initial DOCTOR record, step 2 UPDATES the doctor record.
# UPDATED: To align with new schema (specialization_id, joins, trigger reliance).

import os
import datetime # Ensure datetime is imported
from flask import (Blueprint, render_template, request, flash, redirect, url_for,
                   current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
# Removed: from werkzeug.security import generate_password_hash - NO LONGER HASHING
from db import get_db_connection
from math import ceil
import mysql.connector # For error handling
import re # Added for get_enum_values

Doctors_Management = Blueprint('Doctors_Management', __name__)

# --- Constants ---
PER_PAGE_DOCTORS = 10
# UPDATED: Sort columns to reflect joins and new schema
ALLOWED_DOCTOR_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'specialization_name', 'license_number', # Use specialization_name
    'verification_status', 'created_at', 'account_status'
}
# Ensure UPLOAD_FOLDER is configured in Flask app config
VALID_DOCUMENT_TYPES = ['license', 'certification', 'identity', 'education', 'other']
# Default/fallback account statuses matching the new schema
DEFAULT_ACCOUNT_STATUSES = ['active', 'inactive', 'suspended', 'pending']


# --- Helper Functions ---

# --- COPIED/ADAPTED from Admins_Management.py ---
def get_enum_values(table_name, column_name):
    """Fetches possible ENUM values for a given table and column."""
    connection = None
    cursor = None
    enum_values = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for ENUM fetch")
        cursor = connection.cursor()
        db_name = connection.database
        if not db_name:
            db_name = current_app.config.get('MYSQL_DB')
        if not db_name:
            current_app.logger.warning("Could not determine database name to fetch ENUMs.")
            # Return defaults based on common columns if name unknown
            if table_name == 'users' and column_name == 'account_status': return DEFAULT_ACCOUNT_STATUSES
            if table_name == 'doctors' and column_name == 'verification_status': return ['pending', 'approved', 'rejected', 'pending_info']
            if table_name == 'doctor_documents' and column_name == 'document_type': return VALID_DOCUMENT_TYPES
            return []

        cursor.execute("""
            SELECT COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
        """, (db_name, table_name, column_name))
        result = cursor.fetchone()

        if result and result[0]:
            enum_def = result[0]
            if enum_def.lower().startswith("enum("):
                content = enum_def[5:-1]
                enum_values = [val.strip().strip("'").strip('"') for val in content.split(',')]
            else:
                 current_app.logger.warning(f"Could not parse ENUM string for {table_name}.{column_name}: {result[0]}")
        else:
            current_app.logger.warning(f"Could not find ENUM definition for {table_name}.{column_name}")

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching ENUM values for {table_name}.{column_name}: {db_err}")
        enum_values = [] # Ensure empty list on error
    except Exception as e:
        current_app.logger.error(f"General error fetching ENUM values for {table_name}.{column_name}: {e}")
        enum_values = []
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Use defaults if fetching failed and defaults are known
    if not enum_values:
        if table_name == 'users' and column_name == 'account_status':
            current_app.logger.warning("ENUM fetch failed for account_status, using defaults.")
            return DEFAULT_ACCOUNT_STATUSES
        if table_name == 'doctors' and column_name == 'verification_status':
             current_app.logger.warning("ENUM fetch failed for verification_status, using defaults.")
             return ['pending', 'approved', 'rejected', 'pending_info']
        if table_name == 'doctor_documents' and column_name == 'document_type':
             current_app.logger.warning("ENUM fetch failed for document_type, using defaults.")
             return VALID_DOCUMENT_TYPES

    return enum_values
# --- END COPIED HELPER ---

def get_all_specializations():
    """Fetches all specializations (id, name) for dropdowns."""
    connection = None
    cursor = None
    specializations = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for specializations fetch")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT specialization_id, name FROM specializations ORDER BY name")
        specializations = cursor.fetchall()
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching specializations: {db_err}")
    except Exception as e:
        current_app.logger.error(f"General error fetching specializations: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations

# --- UPDATED Helper Function ---
def get_doctor_details(doctor_id):
    """
    Fetches combined user, doctor, specialization, and department details,
    including documents AND account_status. ALIGNED WITH NEW SCHEMA.
    """
    connection = None
    cursor = None
    doctor_data = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in get_doctor_details for {doctor_id}")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)

        # UPDATED Query: Join users, doctors, specializations, and departments
        query = """
            SELECT
                u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone,
                u.account_status, u.user_type, u.profile_picture,
                u.created_at AS user_created_at, u.updated_at AS user_updated_at, -- Alias timestamps
                d.license_number, d.license_state, d.license_expiration, d.npi_number,
                d.medical_school, d.graduation_year, d.certifications, d.biography,
                d.clinic_address, d.accepting_new_patients, d.verification_status,
                d.rejection_reason, d.approval_date, d.info_requested, d.info_requested_date,
                d.specialization_id, -- Keep the ID
                s.name AS specialization_name, -- Get the name
                s.department_id AS specialization_department_id, -- Get dept ID from specialization
                dep.name AS department_name -- Get dept name via specialization's dept ID
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON s.department_id = dep.department_id -- Join department via specialization
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """
        cursor.execute(query, (doctor_id,))
        doctor_data = cursor.fetchone()

        if not doctor_data:
            current_app.logger.warning(f"Doctor not found for ID {doctor_id} in get_doctor_details")
            return None

        # Get documents (query remains the same conceptually)
        cursor.execute("""SELECT document_id, document_type, file_name, file_path, upload_date, file_size
                          FROM doctor_documents WHERE doctor_id = %s ORDER BY upload_date DESC""", (doctor_id,))
        doctor_data['documents'] = cursor.fetchall()

        # Format dates if needed for display
        if doctor_data.get('license_expiration') and isinstance(doctor_data['license_expiration'], (datetime.date, datetime.datetime)):
             doctor_data['license_expiration_formatted'] = doctor_data['license_expiration'].strftime('%Y-%m-%d')
        else:
            doctor_data['license_expiration_formatted'] = ''

        return doctor_data
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error fetching doctor details for {doctor_id}: {db_err}")
        return None
    except Exception as e:
        current_app.logger.error(f"Error fetching doctor details for {doctor_id}: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

# ... (keep get_user_basic_info and get_current_user_id_int) ...
def get_user_basic_info(user_id, expected_type='doctor'):
    """
    Fetches basic user info (username, names) for display, checking type.
    Read-only operation, no explicit transaction needed.
    """
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
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error fetching basic info for user ID {user_id}: {db_err}")
        user_info = None
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

# --- UPDATED Route ---
@Doctors_Management.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    """Displays a paginated list of doctors with search and sort. ALIGNED WITH NEW SCHEMA."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Corrected redirect

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by = request.args.get('sort_by', 'last_name').lower()
    # UPDATED: Use specialization_name for sorting
    if sort_by == 'specialization': sort_by = 'specialization_name'
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

        # --- UPDATED Query Building ---
        base_query = """
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            WHERE u.user_type = 'doctor'
        """
        params = []
        search_clause = ""
        if search_term:
            # UPDATED: Search specialization name (s.name)
            search_clause = """ AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s
                                OR s.name LIKE %s OR d.license_number LIKE %s
                                OR d.verification_status LIKE %s OR u.account_status LIKE %s) """
            like_term = f"%{search_term}%"; params.extend([like_term] * 7) # Count remains 7

        # Count total
        count_query = f"SELECT COUNT(u.user_id) as total {base_query} {search_clause}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_DOCTORS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_DOCTORS

        # Determine sort column prefix (handle specialization_name)
        if sort_by in ['first_name', 'last_name', 'email', 'created_at', 'account_status']:
            sort_column = f"u.{sort_by}"
        elif sort_by in ['license_number', 'verification_status']:
            sort_column = f"d.{sort_by}"
        elif sort_by == 'specialization_name':
            sort_column = "s.name" # Sort by the actual name column
        else: # Default fallback (shouldn't happen with validation)
            sort_column = "u.last_name"

        # Construct final data query (No password field selected)
        # UPDATED: Select specialization name, adjust joins
        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.created_at,
                   u.account_status, s.name AS specialization_name, d.license_number, d.verification_status
            {base_query} {search_clause}
            ORDER BY {sort_column} {sort_order}
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE_DOCTORS, offset]
        cursor.execute(data_query, tuple(final_params)); doctors = cursor.fetchall()

    except mysql.connector.Error as db_err:
        flash(f"Database error fetching doctors: {db_err}", "danger")
        current_app.logger.error(f"DB Error fetching doctor list: {db_err}")
    except Exception as e:
        flash(f"Error fetching doctors: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching doctor list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Pass the original sort_by ('specialization') to template if used, for active class highlighting
    template_sort_by = 'specialization' if sort_by == 'specialization_name' else sort_by

    return render_template(
        'Admin_Portal/Doctors/view_doctors.html',
        doctors=doctors, page=page, total_pages=total_pages, per_page=PER_PAGE_DOCTORS,
        total_items=total_items, search_term=search_term,
        sort_by=template_sort_by, # Pass potentially mapped name back
        sort_order=sort_order
    )


# --- View Doctor (Uses updated get_doctor_details) ---
@Doctors_Management.route('/admin/doctors/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_doctor(doctor_id):
    """Displays details for a single doctor. Read-only. Uses updated get_doctor_details."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    doctor = get_doctor_details(doctor_id)
    if not doctor:
        flash("Doctor not found.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Template 'doctor_details.html' needs to be updated to use
    # doctor.specialization_name and potentially doctor.department_name
    return render_template('Admin_Portal/Doctors/doctor_details.html', doctor=doctor)


# --- Add Doctor Step 1 (Only Creates User Record) ---

@Doctors_Management.route('/admin/doctors/add/step1', methods=['GET'])
@login_required
def add_doctor_step1_form():
    """Displays Step 1 of the add doctor form (User details)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route
    return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data={})


@Doctors_Management.route('/admin/doctors/add/step1', methods=['POST'])
@login_required
def add_doctor_step1():
    """
    Processes Step 1: Creates ONLY the user record (plain text pass).
    The DB trigger handles creating the associated doctors record.
    Uses an explicit transaction. ALIGNED WITH NEW SCHEMA/TRIGGER.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    username = request.form.get('username')
    email = request.form.get('email')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None
    # WARNING: Storing plain text password - highly insecure
    temp_password = os.urandom(10).hex() # Generate a temporary password

    form_data_for_render = request.form.copy() # Keep form data for re-rendering on error

    if not all([username, email, first_name, last_name]):
        flash("Missing required fields (Username, Email, First Name, Last Name).", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

    connection = None
    cursor = None
    user_id = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        # Check for existing user *before* inserting
        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email or Username already exists.", "danger")
            # No rollback needed as no changes were made yet
            return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

        # Insert the new user (Trigger will handle doctors record)
        # Default status is 'pending' to align with typical doctor onboarding
        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name,
                              user_type, phone, account_status)
            VALUES (%s, %s, %s, %s, %s, 'doctor', %s, 'pending')
        """, (username, email, temp_password, first_name, last_name, phone)) # Store plain text password

        user_id = cursor.lastrowid

        # Explicitly commit the transaction
        connection.commit()
        current_app.logger.info(f"Step 1: Committed doctor USER insert for {username}. lastrowid = {user_id}. Trigger should create doctor record.")

        if not user_id:
             # This case should be rare if commit succeeded, but handle defensively
             current_app.logger.error(f"Failed to get lastrowid for doctor user {username} after commit.")
             flash("Error: User seemed to be created but could not retrieve ID.", "danger")
             return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

        current_app.logger.warning(f"Temporary password for doctor {username} (ID: {user_id}): {temp_password}") # SECURITY RISK LOGGING

        flash("Step 1 complete: Doctor user account created (Status: Pending). Now add specific doctor details.", "info")
        return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error adding doctor user (step 1) for {username}: {db_err}")
        try:
            if connection and connection.is_connected():
                connection.rollback() # Rollback on DB error
                current_app.logger.info(f"Rolled back transaction for user {username} due to DB error.")
        except Exception as rb_err:
            current_app.logger.error(f"Error during rollback attempt for {username}: {rb_err}")
        flash(f"Database error creating user: {db_err}", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

    except Exception as e:
        current_app.logger.error(f"Non-DB Error adding doctor user (step 1) for {username}: {e}")
        # No rollback needed if error occurred before DB operations or after commit
        flash(f"Error creating user: {str(e)}", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=form_data_for_render)

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Fallback redirect (should ideally not be reached if logic is correct)
    return redirect(url_for('Doctors_Management.add_doctor_step1_form'))


# --- Add Doctor Step 2 (Updates Doctor Record) ---

@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['GET'])
@login_required
def add_doctor_step2_form(user_id):
    """
    Displays Step 2 of the add doctor form (Doctor specifics).
    Fetches specializations for dropdown. ALIGNED WITH NEW SCHEMA.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        current_app.logger.error(f"Doctor Step 2 Form (GET): Doctor user info not found or wrong type for ID {user_id}.")
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Fetch specializations for the dropdown
    specializations_list = get_all_specializations()
    if not specializations_list:
        flash("Could not load specializations. Please try again or contact support.", "warning")
        # Decide if we should block or allow proceeding without specialization selection
        # For now, we'll proceed but the dropdown will be empty.

    current_year = datetime.datetime.now().year
    # Template 'add_doctor_step2.html' needs updating for specialization_id select
    return render_template(
        'Admin_Portal/Doctors/add_doctor_step2.html',
        user=user_info,
        form_data={},
        current_year=current_year,
        specializations=specializations_list # Pass list to template
    )


@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['POST'])
@login_required
def add_doctor_step2(user_id):
    """
    Processes Step 2: UPDATES the doctor record created by trigger and adds audit log.
    Uses an explicit transaction. ALIGNED WITH NEW SCHEMA/TRIGGER.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    user_info = get_user_basic_info(user_id, expected_type='doctor') # Re-fetch for context
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Fetch specializations again for error re-rendering
    specializations_list = get_all_specializations()

    # Extract form data
    specialization_id_str = request.form.get('specialization_id') # Get ID from select
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state') or None
    license_expiration = request.form.get('license_expiration') or None
    npi_number = request.form.get('npi_number') or None
    medical_school = request.form.get('medical_school') or None
    graduation_year = request.form.get('graduation_year') or None # Keep as potentially null/string
    certifications = request.form.get('certifications') or None
    biography = request.form.get('biography') or None
    clinic_address = request.form.get('clinic_address') or None
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
    # department_id = request.form.get('department_id') or None # Add if needed

    current_year = datetime.datetime.now().year # For re-rendering form on error

    # Basic validation - CRITICAL: Validate specialization_id
    if not all([specialization_id_str, license_number, license_state, license_expiration]):
        flash("Missing required doctor details (Specialization, License Number, State, Expiration).", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info,
                               form_data=request.form,
                               current_year=current_year,
                               specializations=specializations_list) # Pass list back

    # Convert specialization_id to integer
    try:
        specialization_id = int(specialization_id_str)
    except (ValueError, TypeError):
         flash("Invalid Specialization selected.", "danger")
         return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                                user=user_info,
                                form_data=request.form,
                                current_year=current_year,
                                specializations=specializations_list)

    # Convert graduation year safely
    try:
        graduation_year_int = int(graduation_year) if graduation_year else None
    except (ValueError, TypeError):
        flash("Invalid Graduation Year.", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info,
                               form_data=request.form,
                               current_year=current_year,
                               specializations=specializations_list)


    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        # Check NPI uniqueness (if provided) before updating
        if npi_number:
             cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, user_id))
             if cursor.fetchone():
                  flash("NPI number already exists for another doctor.", "danger")
                  return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                                         user=user_info,
                                         form_data=request.form,
                                         current_year=current_year,
                                         specializations=specializations_list)

        # UPDATED: Update the doctors table (record created by trigger)
        # Set verification_status to 'pending_info' or keep 'pending'
        cursor.execute("""
            UPDATE doctors SET
                specialization_id = %s, license_number = %s, license_state = %s,
                license_expiration = %s, accepting_new_patients = %s, npi_number = %s,
                medical_school = %s, graduation_year = %s, certifications = %s,
                biography = %s, clinic_address = %s,
                verification_status = 'pending_info' -- Or keep 'pending'
                -- department_id = %s -- Add if needed
            WHERE user_id = %s
        """, (specialization_id, license_number, license_state,
              license_expiration, accepting_new_patients, npi_number,
              medical_school, graduation_year_int, certifications, biography,
              clinic_address, # department_id, # Add if needed
              user_id))

        rows_affected = cursor.rowcount

        # Add audit log entry within the same transaction
        current_admin_id = get_current_user_id_int()
        action_details = f"Doctor details added/updated by admin (Step 2). Rows affected: {rows_affected}."
        if current_admin_id:
            try:
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                    VALUES (%s, 'doctor_details_added', %s, %s, 'doctors', %s)
                """, (user_id, action_details, current_admin_id, user_id))
            except Exception as audit_err:
                raise RuntimeError(f"Failed to add audit log, rolling back: {audit_err}")
        else:
             current_app.logger.warning(f"Could not create audit log for step 2 doctor {user_id} - admin ID unknown.")


        # Commit both the update and the audit log together
        connection.commit()
        current_app.logger.info(f"Step 2 (POST): Committed doctor details update and audit log for user {user_id}.")

        if rows_affected > 0:
            flash("Doctor details added successfully. Account verification status updated.", "success")
        else:
             # This might happen if the trigger failed or data hasn't changed
             flash("Doctor details submitted, but no changes were detected or the record was missing.", "warning")
             current_app.logger.warning(f"Step 2 (POST): Update doctor details for user {user_id} affected 0 rows.")

        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=user_id)) # Go to details page

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error updating doctor details (step 2) for user ID {user_id}: {db_err}")
        try:
            if connection and connection.is_connected():
                connection.rollback()
                current_app.logger.info(f"Rolled back transaction for doctor details {user_id} due to DB error.")
        except Exception as rb_err:
            current_app.logger.error(f"Error during rollback attempt for doctor {user_id}: {rb_err}")
        # Check for FK violation on specialization_id
        if db_err.errno == 1452: # Foreign key constraint fails
             flash("Invalid Specialization selected. Please choose from the list.", "danger")
        else:
             flash(f"Database error saving doctor details: {db_err}", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info, form_data=request.form,
                               current_year=current_year, specializations=specializations_list)

    except Exception as e:
        current_app.logger.error(f"Non-DB Error updating doctor details (step 2) for user ID {user_id}: {e}")
        # Rollback if error occurred during DB operations before commit
        if 'cursor' in locals() and cursor is not None: # Check if cursor was created
            try:
                 if connection and connection.is_connected():
                    connection.rollback()
                    current_app.logger.info(f"Rolled back transaction for doctor details {user_id} due to non-DB error during transaction.")
            except Exception as rb_err:
                 current_app.logger.error(f"Error during rollback attempt for doctor {user_id} (non-DB error): {rb_err}")
        flash(f"Error saving doctor details: {str(e)}", "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info, form_data=request.form,
                               current_year=current_year, specializations=specializations_list)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Fallback redirect
    return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))


# --- Edit Doctor ---

@Doctors_Management.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    """
    Processes editing of doctor user and details (plain text pass).
    Handles account_status update. Uses specialization_id dropdown.
    Uses an explicit transaction for updates. ALIGNED WITH NEW SCHEMA.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    connection = None
    cursor = None
    redirect_target = url_for('Doctors_Management.view_doctor', doctor_id=doctor_id)
    current_year = datetime.datetime.now().year

    # Fetch lists needed for forms (GET and POST error render)
    account_statuses_list = get_enum_values('users', 'account_status') or DEFAULT_ACCOUNT_STATUSES
    specializations_list = get_all_specializations()
    verification_statuses_list = get_enum_values('doctors', 'verification_status') or ['pending', 'approved', 'rejected', 'pending_info']


    if request.method == 'GET':
        doctor_for_render = get_doctor_details(doctor_id)
        if not doctor_for_render:
             flash("Doctor not found.", "danger")
             return redirect(url_for('Doctors_Management.index'))

        # Template 'edit_doctor.html' needs updating for specialization_id select
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=doctor_for_render,
                               form_data=doctor_for_render, # Pre-fill form
                               current_year=current_year,
                               account_statuses=account_statuses_list,
                               specializations=specializations_list, # Pass list
                               verification_statuses=verification_statuses_list)

    # --- POST Logic ---
    current_doctor_data = get_doctor_details(doctor_id) # Get current state for comparison
    if not current_doctor_data:
        flash("Cannot edit doctor: Doctor not found.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    # Prepare data for re-rendering on error - Start with form, update with non-form data
    form_data_for_render = request.form.to_dict()
    # Add essential non-form data needed for template rendering
    form_data_for_render['user_id'] = doctor_id
    form_data_for_render['documents'] = current_doctor_data.get('documents', [])
    form_data_for_render['username'] = current_doctor_data.get('username')
    form_data_for_render['user_created_at'] = current_doctor_data.get('user_created_at')
    form_data_for_render['profile_picture'] = current_doctor_data.get('profile_picture')
    # Ensure boolean/checkbox value is correct for render
    form_data_for_render['accepting_new_patients'] = 1 if request.form.get('accepting_new_patients') else 0
    # Keep formatted date if available, otherwise use form value
    form_data_for_render['license_expiration_formatted'] = form_data_for_render.get('license_expiration') or current_doctor_data.get('license_expiration_formatted','')
    # Add specialization name based on selected ID for display consistency on error
    selected_spec_id_str = form_data_for_render.get('specialization_id')
    form_data_for_render['specialization_name'] = 'Unknown' # Default
    if selected_spec_id_str:
        try:
            selected_spec_id = int(selected_spec_id_str)
            for spec in specializations_list:
                if spec['specialization_id'] == selected_spec_id:
                    form_data_for_render['specialization_name'] = spec['name']
                    break
        except (ValueError, TypeError):
            pass # Keep default 'Unknown' if ID is invalid


    try:
        # Extract Form Data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone') or None
        account_status = request.form.get('account_status') # Get selected user account status
        verification_status = request.form.get('verification_status') # Get selected doctor verification status

        specialization_id_str = request.form.get('specialization_id') # Get ID
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
        if not all([first_name, last_name, email, account_status, verification_status, specialization_id_str, license_number, license_state, license_expiration]):
             flash("Missing required fields (Name, Email, Account Status, Verification Status, Specialization, License Details).", "danger")
             return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                    doctor=form_data_for_render, form_data=form_data_for_render,
                                    current_year=current_year, account_statuses=account_statuses_list,
                                    specializations=specializations_list, verification_statuses=verification_statuses_list)

        # --- Add Status Validation ---
        if not account_status or account_status not in account_statuses_list:
             flash(f"Invalid account status selected.", "danger")
             return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                    doctor=form_data_for_render, form_data=form_data_for_render,
                                    current_year=current_year, account_statuses=account_statuses_list,
                                    specializations=specializations_list, verification_statuses=verification_statuses_list)
        if not verification_status or verification_status not in verification_statuses_list:
             flash(f"Invalid verification status selected.", "danger")
             return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                    doctor=form_data_for_render, form_data=form_data_for_render,
                                    current_year=current_year, account_statuses=account_statuses_list,
                                    specializations=specializations_list, verification_statuses=verification_statuses_list)

        # Convert specialization_id and graduation_year safely
        try:
            specialization_id = int(specialization_id_str)
        except (ValueError, TypeError):
            flash("Invalid Specialization selected.", "danger")
            return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                   doctor=form_data_for_render, form_data=form_data_for_render,
                                   current_year=current_year, account_statuses=account_statuses_list,
                                   specializations=specializations_list, verification_statuses=verification_statuses_list)
        try:
            graduation_year_int = int(graduation_year) if graduation_year else None
        except (ValueError, TypeError):
            flash("Invalid Graduation Year.", "danger")
            return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                   doctor=form_data_for_render, form_data=form_data_for_render,
                                   current_year=current_year, account_statuses=account_statuses_list,
                                   specializations=specializations_list, verification_statuses=verification_statuses_list)


        # Password Change Logic (Plain Text)
        update_password = False
        password_to_update = None
        password_error = False # Flag for password specific errors
        if new_password or confirm_password:
            if not new_password or not confirm_password:
                 flash("Both New Password and Confirm Password are required to change password.", "warning")
                 password_error = True
            elif new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                password_error = True
            else:
                update_password = True
                password_to_update = new_password
                current_app.logger.warning(f"Admin is changing password for doctor ID {doctor_id} (Plain Text).")

            if password_error:
                 form_data_for_render['new_password'] = '' # Clear passwords on error render
                 form_data_for_render['confirm_password'] = ''
                 return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                        doctor=form_data_for_render, form_data=form_data_for_render,
                                        current_year=current_year, account_statuses=account_statuses_list,
                                        specializations=specializations_list, verification_statuses=verification_statuses_list)

        # DB Interaction within a transaction
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        # Pre-checks (email, NPI uniqueness) before updates
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, doctor_id))
        if cursor.fetchone():
            flash("Email address already in use by another user.", "danger")
            cursor.close(); connection.close()
            return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                   doctor=form_data_for_render, form_data=form_data_for_render,
                                   current_year=current_year, account_statuses=account_statuses_list,
                                   specializations=specializations_list, verification_statuses=verification_statuses_list)

        if npi_number:
             cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, doctor_id))
             if cursor.fetchone():
                 flash("NPI Number already in use by another doctor.", "danger")
                 cursor.close(); connection.close()
                 return render_template('Admin_Portal/Doctors/edit_doctor.html',
                                        doctor=form_data_for_render, form_data=form_data_for_render,
                                        current_year=current_year, account_statuses=account_statuses_list,
                                        specializations=specializations_list, verification_statuses=verification_statuses_list)

        # Perform Updates
        # Update Users Table
        user_update_fields = ["first_name = %s", "last_name = %s", "email = %s", "phone = %s"]
        user_params = [first_name, last_name, email, phone]
        # Add password update if requested
        if update_password:
            user_update_fields.append("password = %s") # Still using plain text password column
            user_params.append(password_to_update)
        # Add account status update if changed
        if account_status != current_doctor_data.get('account_status'):
            user_update_fields.append("account_status = %s")
            user_params.append(account_status)

        user_rows_affected = 0
        if len(user_update_fields) > 0 : # Only run update if there are fields to update
            user_params.append(doctor_id) # For WHERE clause
            user_update_query = f"UPDATE users SET {', '.join(user_update_fields)} WHERE user_id = %s AND user_type = 'doctor'"
            cursor.execute(user_update_query, tuple(user_params))
            user_rows_affected = cursor.rowcount

        # Update Doctors Table
        # UPDATED: Use specialization_id instead of specialization name
        # Add verification_status
        doctor_update_fields = [
            "specialization_id = %s", "license_number = %s", "license_state = %s",
            "license_expiration = %s", "accepting_new_patients = %s", "npi_number = %s",
            "medical_school = %s", "graduation_year = %s", "certifications = %s",
            "biography = %s", "clinic_address = %s", "verification_status = %s"
            # "department_id = %s" # Add if needed
        ]
        doctor_params = [
            specialization_id, license_number, license_state,
            license_expiration, accepting_new_patients, npi_number,
            medical_school, graduation_year_int, certifications, biography,
            clinic_address, verification_status
            # department_id # Add if needed
        ]
        doctor_params.append(doctor_id) # For WHERE clause

        doctor_update_query = f"UPDATE doctors SET {', '.join(doctor_update_fields)} WHERE user_id = %s"
        cursor.execute(doctor_update_query, tuple(doctor_params))
        doctor_rows_affected = cursor.rowcount

        # Add Audit Log if changes were made
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            current_admin_id = get_current_user_id_int()
            action_details = f"Doctor profile updated by admin. User rows: {user_rows_affected}, Doctor rows: {doctor_rows_affected}."
            if update_password: action_details += " Password changed."
            if account_status != current_doctor_data.get('account_status'): action_details += f" Account status set to {account_status}."
            if verification_status != current_doctor_data.get('verification_status'): action_details += f" Verification status set to {verification_status}."
            if specialization_id != current_doctor_data.get('specialization_id'): action_details += f" Specialization ID changed to {specialization_id}."

            if current_admin_id:
                try:
                     cursor.execute("""
                         INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                         VALUES (%s, 'doctor_updated', %s, %s, 'users/doctors', %s)
                     """, (doctor_id, action_details, current_admin_id, doctor_id))
                except Exception as audit_err:
                     raise RuntimeError(f"Failed to add audit log, rolling back: {audit_err}")
            else:
                 current_app.logger.warning(f"Could not log audit for doctor edit {doctor_id} - admin ID not found.")

        # Commit all changes
        connection.commit()
        current_app.logger.info(f"Committed updates for doctor {doctor_id}. User rows: {user_rows_affected}, Doctor rows: {doctor_rows_affected}")

        # Provide feedback
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            flash_msg = "Doctor updated successfully"
            if update_password: flash_msg += " (Password Changed - Plain Text)"
            if account_status != current_doctor_data.get('account_status'):
                 flash_msg += f" (Account Status set to: {account_status.replace('_',' ').title()})"
            if verification_status != current_doctor_data.get('verification_status'):
                 flash_msg += f" (Verification Status set to: {verification_status.replace('_',' ').title()})"
            flash(flash_msg, "success")
        else:
             flash("No changes detected for the doctor.", "info")

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error updating doctor {doctor_id}: {db_err}")
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt (DB error): {rb_err}")
        # Check for FK violation on specialization_id
        if db_err.errno == 1452: # Foreign key constraint fails
             flash("Invalid Specialization selected. Please choose from the list.", "danger")
        else:
             flash(f"Database error updating doctor: {db_err}", "danger")
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=form_data_for_render, form_data=form_data_for_render,
                               current_year=current_year, account_statuses=account_statuses_list,
                               specializations=specializations_list, verification_statuses=verification_statuses_list)

    except Exception as e:
        current_app.logger.error(f"Non-DB Error updating doctor {doctor_id}: {e}")
        if 'cursor' in locals() and cursor is not None:
            try:
                if connection and connection.is_connected(): connection.rollback()
            except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt (non-DB error): {rb_err}")
        flash(f"An error occurred: {str(e)}", "danger")
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=form_data_for_render, form_data=form_data_for_render,
                               current_year=current_year, account_statuses=account_statuses_list,
                               specializations=specializations_list, verification_statuses=verification_statuses_list)

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)


# --- Document Management (Largely Unchanged - Schema OK) ---

@Doctors_Management.route('/admin/doctors/upload-document/<int:doctor_id>', methods=['POST'])
@login_required
def upload_doctor_document(doctor_id):
    """
    Handles document uploads for a specific doctor.
    Saves file first, then uses an explicit transaction for DB insert + audit log.
    Attempts file cleanup on DB error. Schema for doctor_documents is compatible.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    # Verify doctor exists before proceeding (uses get_user_basic_info - OK)
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

    # Fetch valid types dynamically or use constant
    valid_doc_types = get_enum_values('doctor_documents', 'document_type') or VALID_DOCUMENT_TYPES
    if not document_type or document_type not in valid_doc_types:
        flash(f'Invalid or missing document type. Allowed types: {", ".join(valid_doc_types)}.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    connection = None
    cursor = None
    saved_file_path_abs = None # Store absolute path for saving and potential cleanup
    relative_path_for_db = None # Store relative path for DB insertion
    unique_filename = None # Store filename for logging

    try:
        # --- Get Upload Path Configuration ---
        upload_folder_base = current_app.config.get('UPLOAD_FOLDER')
        if not upload_folder_base:
             current_app.logger.critical("UPLOAD_FOLDER configuration missing in Flask app!")
             raise ValueError("File upload configuration error. Please contact administrator.")

        # --- Prepare File Paths ---
        doctor_upload_subdir = os.path.join('doctor_docs', str(doctor_id))
        doctor_upload_path_abs = os.path.join(upload_folder_base, doctor_upload_subdir)
        os.makedirs(doctor_upload_path_abs, exist_ok=True)

        # --- Create Secure and Unique Filename ---
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
        safe_original_filename = secure_filename(file.filename)
        # Limit filename length if necessary for DB schema (VARCHAR(255))
        base, ext = os.path.splitext(safe_original_filename)
        max_base_len = 255 - len(timestamp) - 1 - len(ext) # -1 for underscore
        if len(base) > max_base_len:
            base = base[:max_base_len]
        safe_original_filename = f"{base}{ext}"
        unique_filename = f"{timestamp}_{safe_original_filename}" # Store for logging/DB

        saved_file_path_abs = os.path.join(doctor_upload_path_abs, unique_filename)
        relative_path_for_db = os.path.join(doctor_upload_subdir, unique_filename).replace("\\", "/") # Use forward slashes for DB/web

        # --- Save the File (Outside DB Transaction) ---
        current_app.logger.info(f"Attempting to save document to: {saved_file_path_abs}")
        file.save(saved_file_path_abs)
        file_size = os.path.getsize(saved_file_path_abs)
        current_app.logger.info(f"Successfully saved {unique_filename} ({file_size} bytes) for doctor {doctor_id}")

        # --- Update Database (Within Transaction) ---
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed after file save.")
        cursor = connection.cursor()

        # Insert document record (Schema matches)
        # Use DEFAULT for upload_date if column definition uses DEFAULT CURRENT_TIMESTAMP
        cursor.execute("""
            INSERT INTO doctor_documents
            (doctor_id, document_type, file_name, file_path, file_size, upload_date)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (doctor_id, document_type, unique_filename, relative_path_for_db, file_size))
        document_id_inserted = cursor.lastrowid

        # Add Audit Log entry
        current_admin_id = get_current_user_id_int()
        if current_admin_id:
            try:
                action_details = f"Admin uploaded {document_type} document: {unique_filename}"
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                    VALUES (%s, 'document_upload', %s, %s, 'doctor_documents', %s)
                """, (doctor_id, action_details, current_admin_id, document_id_inserted))
            except Exception as audit_err:
                # Decide: Rollback or proceed without audit? Decision: Rollback.
                raise RuntimeError(f"Failed to add audit log for doc upload, rolling back: {audit_err}")
        else:
            current_app.logger.warning(f"Could not log audit for doc upload {unique_filename} - admin ID not found.")

        # Commit DB changes (document record + audit log)
        connection.commit()
        current_app.logger.info(f"Committed document record (ID: {document_id_inserted}) and audit log for {unique_filename} into DB.")
        flash("Document uploaded successfully.", "success")

    except ValueError as ve: # Catch specific config error
        flash(str(ve), "danger")
        current_app.logger.error(f"Configuration error during doc upload for {doctor_id}: {ve}")
        # No cleanup needed as file save likely didn't happen

    except (mysql.connector.Error, ConnectionError, RuntimeError) as db_err: # Catch DB errors, connection issues, or audit failure runtime error
        current_app.logger.error(f"DB Transaction error during doc upload for {doctor_id}, file {unique_filename}: {db_err}")
        try:
            if connection and connection.is_connected():
                connection.rollback()
                current_app.logger.info(f"Rolled back DB transaction for doc {unique_filename}.")
        except Exception as rb_err:
            current_app.logger.error(f"Rollback attempt failed after DB error for {unique_filename}: {rb_err}")
        flash(f"Database error saving document record: {db_err}", "danger")

        # Attempt to clean up the orphaned file if DB insertion failed but file was saved
        if saved_file_path_abs and os.path.exists(saved_file_path_abs):
             current_app.logger.warning(f"Attempting to clean up orphaned file due to DB error: {saved_file_path_abs}")
             try:
                 os.remove(saved_file_path_abs)
                 current_app.logger.info(f"Cleaned up orphaned file: {saved_file_path_abs}")
                 flash("Physical file was saved, but the database update failed. The file has been removed.", "warning")
             except OSError as cleanup_err:
                 current_app.logger.error(f"Error removing orphaned file {saved_file_path_abs} on DB error: {cleanup_err}")
                 flash("Physical file was saved, but the database update failed and the file could NOT be automatically removed.", "danger")

    except Exception as e: # Catch other errors (e.g., file saving errors, permission issues)
        current_app.logger.error(f"Unexpected error uploading doc for {doctor_id}, file {unique_filename}: {e}", exc_info=True)
        flash(f"An unexpected error occurred during upload: {str(e)}", "danger")
        # Attempt cleanup if file was saved before the error
        if saved_file_path_abs and os.path.exists(saved_file_path_abs):
             current_app.logger.warning(f"Attempting to clean up file due to unexpected error: {saved_file_path_abs}")
             try:
                 os.remove(saved_file_path_abs)
                 current_app.logger.info(f"Cleaned up file on general error: {saved_file_path_abs}")
             except OSError as cleanup_error:
                 current_app.logger.error(f"Error cleaning up file {saved_file_path_abs} on general error: {cleanup_error}")

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Redirect back to the doctor's view page
    return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))


@Doctors_Management.route('/admin/doctors/delete-document/<int:document_id>', methods=['POST'])
@login_required
def delete_doctor_document(document_id):
    """
    Deletes a document record and the associated file.
    Uses explicit transaction for DB delete + audit log. Deletes file *after* successful commit.
    Schema for doctor_documents is compatible.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your login route

    connection = None
    cursor = None
    doc_info = None
    doctor_id_redirect = None # Initialize for redirection logic

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")

        # 1. Retrieve document details FIRST to get file path and doctor_id for redirection/cleanup
        cursor_dict = connection.cursor(dictionary=True)
        # Query joins users to verify user_type - OK
        cursor_dict.execute("""SELECT dd.doctor_id, dd.file_path, dd.document_type, dd.file_name, u.user_type
                          FROM doctor_documents dd JOIN users u ON dd.doctor_id = u.user_id
                          WHERE dd.document_id = %s""", (document_id,))
        doc_info = cursor_dict.fetchone()
        cursor_dict.close(); cursor_dict = None # Close dict cursor immediately

        if not doc_info:
            flash("Document not found.", "danger")
            # Cannot determine doctor_id, redirect to referrer or index
            return redirect(request.referrer or url_for('Doctors_Management.index'))

        doctor_id_redirect = doc_info['doctor_id'] # Store for final redirect

        # Check if the document belongs to a valid doctor (extra safety) - OK
        if doc_info.get('user_type') != 'doctor':
             flash("Document does not belong to a doctor.", "warning")
             return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id_redirect))


        # 2. Perform DB Deletion and Audit Log within a Transaction
        cursor = connection.cursor() # Use standard cursor for DML

        # Delete document record (Schema matches) - OK
        cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s", (document_id,))
        deleted_rows = cursor.rowcount

        if deleted_rows > 0:
             # Add audit log entry
             current_admin_id = get_current_user_id_int()
             if current_admin_id:
                 try:
                     action_details = f"Admin deleted {doc_info.get('document_type','N/A')} doc: {doc_info.get('file_name', 'N/A')}"
                     cursor.execute("""
                         INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                         VALUES (%s, 'document_deleted', %s, %s, 'doctor_documents', %s)
                     """, (doc_info['doctor_id'], action_details, current_admin_id, document_id))
                 except Exception as audit_err:
                     # Decide: Rollback or proceed without audit? Decision: Rollback
                     raise RuntimeError(f"Failed to add audit log for doc delete, rolling back: {audit_err}")
             else:
                 current_app.logger.warning(f"Could not log audit for doc delete {document_id} - admin ID not found.")

             # Commit DB delete and audit log together
             connection.commit()
             current_app.logger.info(f"Committed DB delete and audit log for document ID {document_id}.")

             # 3. Try deleting file from filesystem *AFTER* successful DB commit
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
                         # File path existed in DB, but file not found on disk
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
             # DB delete affected 0 rows (already deleted or never existed)
             flash("Document record was not found or already deleted.", "warning")
             # No need to commit or delete files if nothing was deleted from DB

    except (mysql.connector.Error, ConnectionError, RuntimeError) as db_err: # Catch DB errors, connection issues, or audit failure
        current_app.logger.error(f"DB Transaction error during document deletion {document_id}: {db_err}")
        try:
            if connection and connection.is_connected():
                connection.rollback()
                current_app.logger.info(f"Rolled back transaction for doc delete {document_id} due to DB error.")
        except Exception as rb_err:
            current_app.logger.error(f"Rollback attempt failed after DB error for doc {document_id}: {rb_err}")
        flash(f"Database error during document deletion: {db_err}", "danger")

    except Exception as e:
        # Catch other potential errors
        flash(f"An error occurred while deleting the document: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB error deleting doc {document_id}: {e}", exc_info=True)
        # Rollback might be needed if error happened mid-transaction
        if 'cursor' in locals() and cursor is not None: # Check if cursor was created
             try:
                 if connection and connection.is_connected():
                     connection.rollback()
                     current_app.logger.info(f"Rolled back transaction for doc delete {document_id} due to non-DB error.")
             except Exception as rb_err:
                 current_app.logger.error(f"Rollback attempt failed after non-DB error for doc {document_id}: {rb_err}")

    finally:
        # Ensure cursor (if used) and connection are closed
        if 'cursor_dict' in locals() and cursor_dict: # Check if it exists and wasn't closed yet
            try: cursor_dict.close()
            except Exception: pass
        if cursor: # Check if standard cursor was assigned
            try: cursor.close()
            except Exception as close_err: current_app.logger.error(f"Error closing std cursor: {close_err}")
        if connection and connection.is_connected():
            try: connection.close()
            except Exception as conn_close_err: current_app.logger.error(f"Error closing conn: {conn_close_err}")

    # Redirect back to the doctor's view page using the stored ID or fallback
    if doctor_id_redirect:
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id_redirect))
    else:
        # Fallback if doctor_id couldn't be determined (e.g., doc not found initially)
        return redirect(request.referrer or url_for('Doctors_Management.index'))


# --- Delete Doctor ---

@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['GET'])
@login_required
def delete_doctor_confirmation(doctor_id):
     """Displays confirmation page before deleting a doctor."""
     if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login')) # Use your login route

     doctor_info = get_user_basic_info(doctor_id, expected_type='doctor') # Uses basic info - OK
     if not doctor_info:
          flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

     return render_template('Admin_Portal/Doctors/delete_doctor_confirmation.html', doctor=doctor_info)


@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    """
    Processes deletion of a doctor and associated data/files.
    Relies on CASCADE DELETE for doctors table when user is deleted,
    but explicitly deletes documents first for file cleanup.
    Uses an explicit transaction for DB deletes + audit log.
    Deletes files *after* successful commit. ALIGNED WITH SCHEMA (CASCADE).
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login')) # Use your login route

    connection = None
    cursor = None
    cursor_dict = None # For fetching documents
    deleted_user_rows = 0
    documents_to_delete = []
    doctor_username = None # For logging

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")

        # Fetch username for logging before potential deletion
        cursor_simple = connection.cursor()
        cursor_simple.execute("SELECT username FROM users WHERE user_id = %s", (doctor_id,))
        result = cursor_simple.fetchone()
        if result: doctor_username = result[0]
        cursor_simple.close()

        # 1. Get list of document file paths *before* deleting records
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT document_id, file_path FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        documents_to_delete = cursor_dict.fetchall()
        cursor_dict.close(); cursor_dict = None # Close immediately

        # 2. Delete DB records within transaction
        # Explicitly delete documents first to ensure paths are captured before cascade potentially hits.
        # Audit log happens *before* final user deletion.
        cursor = connection.cursor()
        current_app.logger.info(f"Attempting deletion transaction for doctor ID: {doctor_id} (Username: {doctor_username})")

        # Delete documents explicitly
        cursor.execute("DELETE FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        doc_del_count = cursor.rowcount
        current_app.logger.debug(f"Deleted {doc_del_count} rows from doctor_documents for doctor {doctor_id}")

        # Add Audit Log BEFORE deleting the user (as user_id might be needed)
        current_admin_id = get_current_user_id_int()
        if current_admin_id:
            try:
                action_details = f"Admin initiated deletion of doctor account (ID: {doctor_id}, Username: {doctor_username}) and associated data (documents: {doc_del_count})."
                cursor.execute("""
                    INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                    VALUES (%s, 'doctor_deleted', %s, %s, 'users', %s)
                """, (doctor_id, action_details, current_admin_id, doctor_id))
            except Exception as audit_err:
                 # Decide: Rollback or proceed? Decision: Rollback
                 raise RuntimeError(f"Failed to add audit log for doctor delete, rolling back: {audit_err}")
        else:
            current_app.logger.warning(f"Could not log audit for doctor delete {doctor_id} - admin ID not found.")

        # Delete from users table (LAST). CASCADE should handle 'doctors' table.
        # Add user_type check for safety.
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'doctor'", (doctor_id,))
        deleted_user_rows = cursor.rowcount
        current_app.logger.debug(f"Deleted {deleted_user_rows} rows from users for doctor {doctor_id}. Cascade should handle doctors table.")

        # Commit all DB deletions and the audit log together
        connection.commit()
        current_app.logger.info(f"Committed deletion transaction for doctor ID: {doctor_id}. User rows deleted: {deleted_user_rows}")

        # 3. Delete files from filesystem *AFTER* successful DB commit
        if deleted_user_rows > 0: # Only delete files if user was actually deleted
            files_deleted_count = 0
            files_error_count = 0
            upload_folder_base = current_app.config.get('UPLOAD_FOLDER')

            if not upload_folder_base:
                current_app.logger.error(f"UPLOAD_FOLDER not configured, cannot delete files for deleted doctor {doctor_id}.")
                flash("Doctor record deleted, but could not delete associated files (server configuration error).", "warning")
            elif documents_to_delete:
                 current_app.logger.info(f"Attempting to delete {len(documents_to_delete)} files for doctor {doctor_id}.")
                 for doc in documents_to_delete:
                      file_path_relative = doc.get('file_path')
                      if not file_path_relative: continue # Skip if no path recorded

                      file_path_absolute = os.path.join(upload_folder_base, file_path_relative)
                      try:
                           if os.path.exists(file_path_absolute):
                                os.remove(file_path_absolute); files_deleted_count += 1
                                current_app.logger.debug(f"Deleted file: {file_path_absolute}")
                           else:
                               current_app.logger.warning(f"File path not found for deleted doctor {doctor_id}, doc {doc.get('document_id')}: {file_path_absolute}")
                      except OSError as e:
                           files_error_count += 1
                           current_app.logger.error(f"Error deleting file {file_path_absolute} for doctor {doctor_id}: {e}")

                 # Provide detailed feedback about file deletion
                 msg = f"Doctor '{doctor_username}' deleted successfully."
                 if files_error_count > 0:
                      msg += f" However, {files_error_count} associated file(s) could not be deleted from storage."
                      flash(msg, "warning")
                 elif files_deleted_count > 0:
                      msg += f" Associated files ({files_deleted_count}/{len(documents_to_delete)}) also deleted."
                      flash(msg, "success")
                 else: # User deleted, but no documents found/deleted
                      msg += " No associated documents found to delete."
                      flash(msg, "success")

            else:
                 # User deleted, but no documents were associated
                 flash(f"Doctor '{doctor_username}' deleted successfully. No associated documents found to delete.", "success")

        elif doc_del_count > 0:
             # Only documents deleted, user wasn't (maybe wrong type or already gone?)
             flash("Associated doctor documents deleted, but the main user account was not found or not a doctor.", "warning")
             current_app.logger.warning(f"Deleted {doc_del_count} documents for user {doctor_id}, but user record was not deleted (0 rows affected).")
        else:
            # Nothing was deleted from the DB
            flash(f"Doctor (ID: {doctor_id}) not found or already deleted.", "warning")

    except (mysql.connector.Error, ConnectionError, RuntimeError) as db_err: # Catch DB errors, connection issues, audit failure
        current_app.logger.error(f"DB Transaction error deleting doctor {doctor_id}: {db_err}")
        try:
            if connection and connection.is_connected():
                connection.rollback()
                current_app.logger.info(f"Rolled back transaction for doctor delete {doctor_id} due to DB error.")
        except Exception as rb_err:
            current_app.logger.error(f"Rollback attempt failed after DB error for doctor {doctor_id}: {rb_err}")
        flash(f"Database error deleting doctor: {db_err}", "danger")

    except Exception as e:
        current_app.logger.error(f"Non-DB Error deleting doctor {doctor_id}: {e}", exc_info=True)
        # Rollback if error happened mid-transaction
        if 'cursor' in locals() and cursor is not None:
             try:
                 if connection and connection.is_connected():
                     connection.rollback()
                     current_app.logger.info(f"Rolled back transaction for doctor delete {doctor_id} due to non-DB error.")
             except Exception as rb_err:
                 current_app.logger.error(f"Rollback attempt failed after non-DB error for doctor {doctor_id}: {rb_err}")
        flash(f"Error deleting doctor: {str(e)}", "danger")

    finally:
        # Ensure all potential cursors and connection are closed
        if 'cursor_dict' in locals() and cursor_dict: # Check if it exists and wasn't closed yet
            try: cursor_dict.close()
            except Exception: pass
        if cursor:
            try: cursor.close()
            except Exception as close_err: current_app.logger.error(f"Error closing main cursor: {close_err}")
        if connection and connection.is_connected():
            try: connection.close()
            except Exception as conn_close_err: current_app.logger.error(f"Error closing connection: {conn_close_err}")

    return redirect(url_for('Doctors_Management.index'))

# Note: Ensure templates (view_doctors.html, doctor_details.html, add_doctor_step2.html, edit_doctor.html)
# are updated to reflect the use of specialization_name for display and specialization_id for form submissions.