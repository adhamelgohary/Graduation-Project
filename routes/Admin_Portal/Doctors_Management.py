# Doctors_Management.py
import os
import datetime
from flask import (Blueprint, render_template, request, flash, redirect, url_for,
                   current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash # Import for hashing
from db import get_db_connection
from math import ceil
import mysql.connector
import re

Doctors_Management = Blueprint('Doctors_Management', __name__, template_folder="../templates")

# --- Constants ---
PER_PAGE_DOCTORS = 10
ALLOWED_DOCTOR_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'specialization_name', 'department_name', # Added department
    'license_number', 'verification_status', 'created_at', 'account_status'
}
VALID_DOCUMENT_TYPES = ['license', 'certification', 'identity', 'education', 'other']
DEFAULT_ACCOUNT_STATUSES = ['active', 'inactive', 'suspended', 'pending']
DEFAULT_VERIFICATION_STATUSES = ['pending', 'approved', 'rejected', 'pending_info']


# --- Helper Functions ---
def get_enum_values(table_name, column_name):
    connection = None; cursor = None; enum_values = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed for ENUM fetch")
        cursor = connection.cursor()
        db_name = connection.database or current_app.config.get('MYSQL_DB')
        if not db_name:
            current_app.logger.warning("Could not determine database name to fetch ENUMs.")
            if table_name == 'users' and column_name == 'account_status': return DEFAULT_ACCOUNT_STATUSES
            if table_name == 'doctors' and column_name == 'verification_status': return DEFAULT_VERIFICATION_STATUSES
            return []

        cursor.execute("SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
                       (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0] and result[0].lower().startswith("enum("):
            enum_values = [val.strip().strip("'\"") for val in result[0][5:-1].split(',')]
    except mysql.connector.Error as db_err: current_app.logger.error(f"DB error fetching ENUMs for {table_name}.{column_name}: {db_err}")
    except Exception as e: current_app.logger.error(f"General error fetching ENUMs for {table_name}.{column_name}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    
    if not enum_values: # Fallback to constants if DB fetch fails
        if table_name == 'users' and column_name == 'account_status': return DEFAULT_ACCOUNT_STATUSES
        if table_name == 'doctors' and column_name == 'verification_status': return DEFAULT_VERIFICATION_STATUSES
    return enum_values

def get_all_specializations():
    connection = None; cursor = None; specializations = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed for specializations fetch")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT specialization_id, name, department_id FROM specializations ORDER BY name")
        specializations = cursor.fetchall()
    except Exception as e: current_app.logger.error(f"Error fetching all specializations: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations

def get_all_departments(): # New helper
    connection = None; cursor = None; departments = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed for departments fetch")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT department_id, name FROM departments ORDER BY name")
        departments = cursor.fetchall()
    except Exception as e: current_app.logger.error(f"Error fetching all departments: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return departments


def get_doctor_details(doctor_id):
    connection = None; cursor = None; doctor_data = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone,
                u.account_status, u.user_type, u.profile_picture,
                u.created_at AS user_created_at, u.updated_at AS user_updated_at,
                d.license_number, d.license_state, d.license_expiration, d.npi_number,
                d.medical_school, d.graduation_year, d.certifications, d.biography,
                d.clinic_address, d.accepting_new_patients, d.verification_status,
                d.approval_date, d.specialization_id, s.name AS specialization_name,
                d.department_id, dep.name AS department_name 
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id 
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """ # d.department_id is directly from doctors table now
        cursor.execute(query, (doctor_id,))
        doctor_data = cursor.fetchone()
        if not doctor_data: return None

        cursor.execute("SELECT document_id, document_type, file_name, file_path, upload_date, file_size FROM doctor_documents WHERE doctor_id = %s ORDER BY upload_date DESC", (doctor_id,))
        doctor_data['documents'] = cursor.fetchall()
        if doctor_data.get('license_expiration'):
            doctor_data['license_expiration_formatted'] = doctor_data['license_expiration'].strftime('%Y-%m-%d')
        else:
            doctor_data['license_expiration_formatted'] = ''
        return doctor_data
    except Exception as e:
        current_app.logger.error(f"Error fetching doctor details for {doctor_id}: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

def get_user_basic_info(user_id, expected_type='doctor'):
    connection = None; cursor = None; user_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, first_name, last_name, user_type FROM users WHERE user_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if user_info and user_info.get('user_type') != expected_type: return None
    except Exception as e: current_app.logger.error(f"Error fetching basic info for user ID {user_id}: {e}"); user_info = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user_info

def get_current_user_id_int():
    user_id_str = getattr(current_user, 'id', None)
    try: return int(user_id_str) if user_id_str else None
    except (ValueError, TypeError): return None

# --- Routes ---
@Doctors_Management.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by_frontend = request.args.get('sort_by', 'last_name').lower()
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

    # Map frontend sort term to DB column if necessary
    sort_by_db = sort_by_frontend
    if sort_by_frontend == 'specialization': sort_by_db = 'specialization_name'
    elif sort_by_frontend == 'department': sort_by_db = 'department_name'
    
    if sort_by_db not in ALLOWED_DOCTOR_SORT_COLUMNS: sort_by_db = 'last_name'


    connection = None; cursor = None; doctors = []; total_items = 0; total_pages = 0
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)

        base_query_from = """
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id 
            WHERE u.user_type = 'doctor'
        """
        params = []
        search_conditions = []
        if search_term:
            like_term = f"%{search_term}%"
            search_fields = [
                "u.first_name LIKE %s", "u.last_name LIKE %s", "u.email LIKE %s", "u.username LIKE %s",
                "s.name LIKE %s", "dep.name LIKE %s", "d.license_number LIKE %s",
                "d.verification_status LIKE %s", "u.account_status LIKE %s"
            ]
            search_conditions.append(f"({' OR '.join(search_fields)})")
            params.extend([like_term] * len(search_fields))
        
        where_clause = " AND " + " AND ".join(search_conditions) if search_conditions else ""
        
        count_query = f"SELECT COUNT(u.user_id) as total {base_query_from} {where_clause}"
        cursor.execute(count_query, tuple(params))
        total_items = cursor.fetchone()['total']
        total_pages = ceil(total_items / PER_PAGE_DOCTORS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_DOCTORS

        sort_column_sql = ""
        if sort_by_db in ['first_name', 'last_name', 'email', 'created_at', 'account_status']: sort_column_sql = f"u.{sort_by_db}"
        elif sort_by_db in ['license_number', 'verification_status']: sort_column_sql = f"d.{sort_by_db}"
        elif sort_by_db == 'specialization_name': sort_column_sql = "s.name"
        elif sort_by_db == 'department_name': sort_column_sql = "dep.name"
        else: sort_column_sql = "u.last_name" # Default

        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.created_at,
                   u.account_status, s.name AS specialization_name, dep.name AS department_name,
                   d.license_number, d.verification_status
            {base_query_from} {where_clause}
            ORDER BY {sort_column_sql} {sort_order}
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE_DOCTORS, offset]
        cursor.execute(data_query, tuple(final_params))
        doctors = cursor.fetchall()
    except Exception as e:
        flash(f"Error fetching doctors: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching doctor list: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Doctors/view_doctors.html',
        doctors=doctors, page=page, total_pages=total_pages,
        total_items=total_items, search_term=search_term,
        sort_by=sort_by_frontend, sort_order=sort_order # Pass original frontend sort_by
    )

@Doctors_Management.route('/admin/doctors/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    doctor = get_doctor_details(doctor_id)
    if not doctor:
        flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
    
    # Fetch valid document types for the upload form on view page
    doc_types_for_upload = get_enum_values('doctor_documents', 'document_type') or VALID_DOCUMENT_TYPES

    return render_template('Admin_Portal/Doctors/doctor_details.html', doctor=doctor, valid_document_types=doc_types_for_upload)

@Doctors_Management.route('/admin/doctors/add/step1', methods=['GET', 'POST'])
@login_required
def add_doctor_step1():
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    if request.method == 'POST':
        username = request.form.get('username','').strip()
        email = request.form.get('email','').strip().lower()
        first_name = request.form.get('first_name','').strip()
        last_name = request.form.get('last_name','').strip()
        phone = request.form.get('phone','').strip() or None
        # Admin sets password during this step
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        errors = []
        if not all([username, email, first_name, last_name, password, confirm_password]):
            errors.append("All fields including password are required for Step 1.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if password and len(password) < 8: # Check length only if password is provided
            errors.append("Password must be at least 8 characters.")
        if not is_valid_email(email):
            errors.append("Invalid email format.")

        if errors:
            for error in errors: flash(error, "danger")
            return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=request.form)

        connection = None; cursor = None; user_id = None
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
            
            connection.autocommit = False # Explicit transaction
            cursor = connection.cursor()

            cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
            if cursor.fetchone():
                flash("Email or Username already exists.", "danger")
                if connection.is_connected(): connection.rollback()
                return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=request.form)

            hashed_password = generate_password_hash(password) # Hash the password
            now_dt = datetime.datetime.now()

            cursor.execute("""
                INSERT INTO users (username, email, password, first_name, last_name,
                                  user_type, phone, account_status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'doctor', %s, 'pending', %s, %s)
            """, (username, email, hashed_password, first_name, last_name, phone, now_dt, now_dt))
            user_id = cursor.lastrowid
            
            # The trigger `after_users_insert_professional` should have created the doctors record.
            # No explicit insert into `doctors` table needed here.

            connection.commit()
            current_app.logger.info(f"Step 1: Committed doctor USER insert for {username} (ID: {user_id}). Password hashed. Trigger handles doctors record.")
            flash("Step 1 complete: Doctor user account created (Status: Pending). Now add professional details.", "info")
            return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))

        except mysql.connector.Error as db_err:
            if connection and connection.is_connected(): connection.rollback()
            flash(f"Database error: {db_err}", "danger"); current_app.logger.error(f"DB Error add_doctor_step1: {db_err}")
        except Exception as e:
            if connection and connection.is_connected(): connection.rollback() # Rollback for other errors during transaction too
            flash(f"Error: {str(e)}", "danger"); current_app.logger.error(f"Error add_doctor_step1: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected():
                if not connection.autocommit: connection.autocommit = True # Reset
                connection.close()
        return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data=request.form) # Re-render on error after try-except
        
    return render_template('Admin_Portal/Doctors/add_doctor_step1.html', form_data={})


@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['GET', 'POST'])
@login_required
def add_doctor_step2_form(user_id): # Renamed for clarity, as it handles both GET and initial form display
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    all_specializations = get_all_specializations()
    all_departments = get_all_departments() # Fetch departments
    current_year = datetime.datetime.now().year

    if request.method == 'GET':
        # Pre-fill form_data with existing doctor details if any (though fresh record might be empty)
        # This is more relevant if it were an edit page for step 2. For add, usually empty.
        existing_doctor_details = get_doctor_details(user_id) or {} # Fetch to see if trigger populated anything useful
        form_data = {
            'specialization_id': existing_doctor_details.get('specialization_id'),
            'department_id': existing_doctor_details.get('department_id'), # from doctors table if trigger sets it
            # ... other fields from existing_doctor_details if you want to prefill ...
        }
        return render_template(
            'Admin_Portal/Doctors/add_doctor_step2.html',
            user=user_info,
            form_data=form_data, # Pass potentially pre-filled or empty
            current_year=current_year,
            specializations=all_specializations,
            departments=all_departments
        )
    
    # POST logic is now in a separate route: add_doctor_step2_submit
    # This route ('add_doctor_step2_form') is now only for GET
    return redirect(url_for('Doctors_Management.index')) # Should not reach here for POST


@Doctors_Management.route('/admin/doctors/add/step2/submit/<int:user_id>', methods=['POST'])
@login_required
def add_doctor_step2_submit(user_id): # New route for POST submission
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    all_specializations = get_all_specializations()
    all_departments = get_all_departments()
    current_year = datetime.datetime.now().year
    
    form_data_for_render = request.form.to_dict() # For re-rendering on error

    department_id_str = request.form.get('department_id')
    specialization_id_str = request.form.get('specialization_id')
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state') or None
    license_expiration = request.form.get('license_expiration') or None
    npi_number = request.form.get('npi_number') or None
    medical_school = request.form.get('medical_school') or None
    graduation_year_str = request.form.get('graduation_year') or None
    certifications = request.form.get('certifications') or None
    biography = request.form.get('biography') or None
    clinic_address = request.form.get('clinic_address') or None
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
    
    errors = []
    if not all([department_id_str, specialization_id_str, license_number, license_state, license_expiration]):
        errors.append("Department, Specialization, License Number, State, and Expiration are required.")

    department_id_int = None
    if department_id_str:
        try: department_id_int = int(department_id_str)
        except ValueError: errors.append("Invalid Department ID format.")
    
    specialization_id_int = None
    if specialization_id_str:
        try: specialization_id_int = int(specialization_id_str)
        except ValueError: errors.append("Invalid Specialization ID format.")

    graduation_year_int = None
    if graduation_year_str:
        try: graduation_year_int = int(graduation_year_str)
        except ValueError: errors.append("Invalid Graduation Year format.")
    
    if errors:
        for error in errors: flash(error, "danger")
        return render_template('Admin_Portal/Doctors/add_doctor_step2.html',
                               user=user_info, form_data=form_data_for_render,
                               current_year=current_year, specializations=all_specializations, departments=all_departments)

    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        connection.autocommit = False
        cursor = connection.cursor()

        if npi_number: # Check NPI uniqueness
            cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, user_id))
            if cursor.fetchone():
                flash("NPI number already exists for another doctor.", "danger")
                if connection.is_connected(): connection.rollback()
                return render_template('Admin_Portal/Doctors/add_doctor_step2.html', user=user_info, form_data=form_data_for_render, current_year=current_year, specializations=all_specializations, departments=all_departments)

        # The trigger created the initial doctors record. Now we UPDATE it.
        # Default verification_status to 'pending' or 'pending_info'
        # The trigger sets default license info as 'PENDING_VERIFICATION', 'XX'
        cursor.execute("""
            UPDATE doctors SET
                department_id = %s, specialization_id = %s, license_number = %s, 
                license_state = %s, license_expiration = %s, accepting_new_patients = %s, 
                npi_number = %s, medical_school = %s, graduation_year = %s, 
                certifications = %s, biography = %s, clinic_address = %s,
                verification_status = 'pending_info', -- Or 'pending' based on your workflow
                updated_at = NOW()
            WHERE user_id = %s
        """, (department_id_int, specialization_id_int, license_number, license_state,
              license_expiration, accepting_new_patients, npi_number,
              medical_school, graduation_year_int, certifications, biography,
              clinic_address, user_id))
        rows_affected = cursor.rowcount

        # Also update users.account_status to 'active' if it was 'pending'
        # This makes the account usable after step 2, but doctor verification is separate
        cursor.execute("UPDATE users SET account_status = 'active', updated_at = NOW() WHERE user_id = %s AND account_status = 'pending'", (user_id,))
        user_status_updated = cursor.rowcount > 0


        current_admin_id = get_current_user_id_int()
        action_details = f"Doctor details added/updated by admin (Step 2). Rows: {rows_affected}."
        if user_status_updated: action_details += " User account activated."
        if current_admin_id:
            try:
                cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'doctor_details_added', %s, %s, 'doctors', %s)",
                               (user_id, action_details, current_admin_id, user_id))
            except Exception as audit_err: raise RuntimeError(f"Failed to add audit log: {audit_err}")
        
        connection.commit()
        flash_msg = "Doctor professional details saved successfully."
        if user_status_updated: flash_msg += " User account is now active."
        flash(flash_msg, "success")
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=user_id))

    except mysql.connector.Error as db_err:
        if connection and connection.is_connected(): connection.rollback()
        if db_err.errno == 1452: flash("Invalid Department or Specialization selected.", "danger")
        else: flash(f"Database error: {db_err}", "danger")
        current_app.logger.error(f"DB Error add_doctor_step2_submit for user {user_id}: {db_err}", exc_info=True)
    except Exception as e:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"Error: {str(e)}", "danger")
        current_app.logger.error(f"Error add_doctor_step2_submit for user {user_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
    return render_template('Admin_Portal/Doctors/add_doctor_step2.html', user=user_info, form_data=form_data_for_render, current_year=current_year, specializations=all_specializations, departments=all_departments)


@Doctors_Management.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    connection = None; cursor = None
    redirect_target = url_for('Doctors_Management.view_doctor', doctor_id=doctor_id)
    current_year = datetime.datetime.now().year

    account_statuses_list = get_enum_values('users', 'account_status')
    verification_statuses_list = get_enum_values('doctors', 'verification_status')
    all_specializations = get_all_specializations()
    all_departments = get_all_departments() # Fetch departments

    if request.method == 'GET':
        doctor_for_render = get_doctor_details(doctor_id)
        if not doctor_for_render:
             flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=doctor_for_render, form_data=doctor_for_render,
                               current_year=current_year, account_statuses=account_statuses_list,
                               specializations=all_specializations, departments=all_departments,
                               verification_statuses=verification_statuses_list)

    # --- POST Logic ---
    current_doctor_data = get_doctor_details(doctor_id)
    if not current_doctor_data:
        flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

    form_data_for_render = request.form.to_dict()
    # Augment form_data_for_render with necessary non-form data for template re-render
    form_data_for_render.update({
        'user_id': doctor_id, 'documents': current_doctor_data.get('documents', []),
        'username': current_doctor_data.get('username'),
        'user_created_at': current_doctor_data.get('user_created_at'),
        'profile_picture': current_doctor_data.get('profile_picture'),
        'accepting_new_patients': 1 if request.form.get('accepting_new_patients') else 0,
        'license_expiration_formatted': form_data_for_render.get('license_expiration') or current_doctor_data.get('license_expiration_formatted','')
    })
    
    selected_spec_id_str = form_data_for_render.get('specialization_id')
    if selected_spec_id_str:
        try:
            selected_spec_id = int(selected_spec_id_str)
            form_data_for_render['specialization_name'] = next((s['name'] for s in all_specializations if s['specialization_id'] == selected_spec_id), 'Unknown')
        except (ValueError, TypeError): pass
    
    selected_dept_id_str = form_data_for_render.get('department_id')
    if selected_dept_id_str:
        try:
            selected_dept_id = int(selected_dept_id_str)
            form_data_for_render['department_name'] = next((d['name'] for d in all_departments if d['department_id'] == selected_dept_id), 'Unknown')
        except (ValueError, TypeError): pass


    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone') or None
    account_status = request.form.get('account_status')
    verification_status = request.form.get('verification_status')
    department_id_str = request.form.get('department_id')
    specialization_id_str = request.form.get('specialization_id')
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state') or None
    license_expiration = request.form.get('license_expiration') or None
    npi_number = request.form.get('npi_number') or None
    medical_school = request.form.get('medical_school') or None
    graduation_year_str = request.form.get('graduation_year') or None
    certifications = request.form.get('certifications') or None
    biography = request.form.get('biography') or None
    clinic_address = request.form.get('clinic_address') or None
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    errors = []
    if not all([first_name, last_name, email, account_status, verification_status, department_id_str, specialization_id_str, license_number, license_state, license_expiration]):
        errors.append("Name, Email, Statuses, Department, Specialization, and License details are required.")
    if not account_status or account_status not in account_statuses_list: errors.append("Invalid account status.")
    if not verification_status or verification_status not in verification_statuses_list: errors.append("Invalid verification status.")

    department_id_int = None; specialization_id_int = None; graduation_year_int = None
    try: department_id_int = int(department_id_str) if department_id_str else None
    except ValueError: errors.append("Invalid Department ID.")
    try: specialization_id_int = int(specialization_id_str) if specialization_id_str else None
    except ValueError: errors.append("Invalid Specialization ID.")
    try: graduation_year_int = int(graduation_year_str) if graduation_year_str else None
    except ValueError: errors.append("Invalid Graduation Year.")
    
    password_to_update_hashed = None
    if new_password or confirm_password:
        if not new_password or not confirm_password: errors.append("Both New Password and Confirm Password are required to change.")
        elif new_password != confirm_password: errors.append("New passwords do not match.")
        elif len(new_password) < 8: errors.append("New password must be at least 8 characters.")
        else: password_to_update_hashed = generate_password_hash(new_password)

    if errors:
        for error in errors: flash(error, "danger")
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year, account_statuses=account_statuses_list, specializations=all_specializations, departments=all_departments, verification_statuses=verification_statuses_list)

    try:
        connection = get_db_connection(); 
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        connection.autocommit = False
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, doctor_id))
        if cursor.fetchone(): flash("Email already in use.", "danger"); raise ValueError("Email conflict")
        if npi_number:
            cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, doctor_id))
            if cursor.fetchone(): flash("NPI already in use.", "danger"); raise ValueError("NPI conflict")

        user_update_parts = ["first_name = %s", "last_name = %s", "email = %s", "phone = %s", "account_status = %s", "updated_at = NOW()"]
        user_params = [first_name, last_name, email, phone, account_status]
        if password_to_update_hashed:
            user_update_parts.append("password = %s")
            user_params.append(password_to_update_hashed)
        user_params.append(doctor_id)
        cursor.execute(f"UPDATE users SET {', '.join(user_update_parts)} WHERE user_id = %s AND user_type = 'doctor'", tuple(user_params))
        user_rows_affected = cursor.rowcount

        doctor_update_sql = """
            UPDATE doctors SET
                department_id = %s, specialization_id = %s, license_number = %s, license_state = %s,
                license_expiration = %s, accepting_new_patients = %s, npi_number = %s,
                medical_school = %s, graduation_year = %s, certifications = %s,
                biography = %s, clinic_address = %s, verification_status = %s,
                updated_at = NOW() 
            WHERE user_id = %s
        """ # Added department_id, updated_at
        doctor_params_tuple = (
            department_id_int, specialization_id_int, license_number, license_state,
            license_expiration, accepting_new_patients, npi_number,
            medical_school, graduation_year_int, certifications, biography,
            clinic_address, verification_status, doctor_id
        )
        cursor.execute(doctor_update_sql, doctor_params_tuple)
        doctor_rows_affected = cursor.rowcount
        
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            current_admin_id = get_current_user_id_int()
            action_details = f"Doctor ID {doctor_id} updated. User rows: {user_rows_affected}, Doctor rows: {doctor_rows_affected}."
            if password_to_update_hashed: action_details += " Password changed."
            if current_admin_id:
                try:
                    cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'doctor_updated', %s, %s, 'users_doctors', %s)",
                                   (doctor_id, action_details, current_admin_id, doctor_id))
                except Exception as audit_err: raise RuntimeError(f"Audit log failed: {audit_err}")
        
        connection.commit()
        flash_msg = "Doctor updated successfully" if user_rows_affected > 0 or doctor_rows_affected > 0 else "No changes detected."
        if password_to_update_hashed: flash_msg += " (Password Changed)"
        flash(flash_msg, "success" if user_rows_affected > 0 or doctor_rows_affected > 0 else "info")

    except (mysql.connector.Error, ConnectionError, ValueError, RuntimeError) as err: # Added ValueError, RuntimeError
        if connection and connection.is_connected(): connection.rollback()
        if isinstance(err, ValueError) and "conflict" not in str(err).lower(): # Don't re-flash if already flashed
            flash(str(err), "danger")
        elif not isinstance(err, ValueError): # Don't flash generic "ValueError"
             flash(f"Error updating doctor: {err}", "danger")
        current_app.logger.error(f"Error editing doctor {doctor_id}: {err}", exc_info=True)
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render, form_data=form_data_for_render, current_year=current_year, account_statuses=account_statuses_list, specializations=all_specializations, departments=all_departments, verification_statuses=verification_statuses_list)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
    return redirect(redirect_target)


# Document Management Routes (upload_doctor_document, delete_doctor_document)
# These should be largely okay but ensure UPLOAD_FOLDER logic is robust.
# I'll include them for completeness, assuming schema for doctor_documents is compatible.

@Doctors_Management.route('/admin/doctors/upload-document/<int:doctor_id>', methods=['POST'])
@login_required
def upload_doctor_document(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    if not get_user_basic_info(doctor_id, expected_type='doctor'):
         flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

    if 'document' not in request.files or request.files['document'].filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    file = request.files['document']
    document_type = request.form.get('document_type')
    valid_doc_types = get_enum_values('doctor_documents', 'document_type') or VALID_DOCUMENT_TYPES
    if not document_type or document_type not in valid_doc_types:
        flash(f'Invalid document type.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    connection = None; cursor = None; saved_file_path_abs = None; unique_filename = None
    try:
        upload_folder_base = current_app.config.get('UPLOAD_FOLDER_DOCS') # Use specific config for doctor docs
        if not upload_folder_base: raise ValueError("UPLOAD_FOLDER_DOCS not configured.")

        doctor_upload_subdir = str(doctor_id) # Store directly under doctor_id folder within UPLOAD_FOLDER_DOCS
        doctor_upload_path_abs = os.path.join(upload_folder_base, doctor_upload_subdir)
        os.makedirs(doctor_upload_path_abs, exist_ok=True)

        original_secure_filename = secure_filename(file.filename)
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
        base, ext = os.path.splitext(original_secure_filename)
        unique_filename = f"{timestamp}_{base[:100]}{ext}" # Limit base length
        saved_file_path_abs = os.path.join(doctor_upload_path_abs, unique_filename)
        # Relative path for DB should be relative to a base from which files are served,
        # e.g., if UPLOAD_FOLDER_DOCS is 'app/static/uploads/doctor_docs', then store 'doctor_id/filename.ext'
        # or if served by a dedicated route, store path relative to UPLOAD_FOLDER_DOCS root.
        # For simplicity, if UPLOAD_FOLDER_DOCS is web accessible (e.g. under static/uploads), store from that point.
        # Assuming UPLOAD_FOLDER_DOCS is '.../static/doctor_uploads', path_for_db = 'doctor_id/filename.ext'
        # This needs careful consideration based on how files are served.
        # For now, let's assume file_path will be relative to a configured base that Flask can serve.
        # A common pattern is to store path from a configured 'media root' or 'static/uploads'
        # For this example, relative_path_for_db is 'doctor_id/unique_filename' assuming UPLOAD_FOLDER_DOCS is the root for these.
        relative_path_for_db = os.path.join(str(doctor_id), unique_filename).replace("\\", "/")


        file.save(saved_file_path_abs)
        file_size = os.path.getsize(saved_file_path_abs)

        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB Connection failed.")
        connection.autocommit = False
        cursor = connection.cursor()
        cursor.execute("INSERT INTO doctor_documents (doctor_id, document_type, file_name, file_path, file_size, upload_date) VALUES (%s, %s, %s, %s, %s, NOW())",
                       (doctor_id, document_type, unique_filename, relative_path_for_db, file_size))
        doc_id = cursor.lastrowid
        
        admin_id = get_current_user_id_int()
        if admin_id:
            cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'document_upload', %s, %s, 'doctor_documents', %s)",
                           (doctor_id, f"Uploaded {document_type}: {unique_filename}", admin_id, doc_id))
        connection.commit()
        flash("Document uploaded successfully.", "success")
    except (ValueError, IOError, mysql.connector.Error, ConnectionError, RuntimeError) as err:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"Error uploading document: {err}", "danger")
        current_app.logger.error(f"Doc upload error for Dr {doctor_id}: {err}", exc_info=True)
        if saved_file_path_abs and os.path.exists(saved_file_path_abs):
            try: os.remove(saved_file_path_abs); current_app.logger.info(f"Cleaned up {saved_file_path_abs}")
            except OSError as e_clean: current_app.logger.error(f"Cleanup failed for {saved_file_path_abs}: {e_clean}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
    return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))


@Doctors_Management.route('/admin/doctors/delete-document/<int:document_id>', methods=['POST'])
@login_required
def delete_doctor_document(document_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    
    connection = None; cursor = None; doc_info = None; doctor_id_redirect = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB Connection failed.")
        
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT dd.doctor_id, dd.file_path, dd.file_name, u.user_type FROM doctor_documents dd JOIN users u ON dd.doctor_id = u.user_id WHERE dd.document_id = %s", (document_id,))
        doc_info = cursor_dict.fetchone()
        cursor_dict.close()

        if not doc_info: flash("Document not found.", "danger"); raise ValueError("Doc not found")
        doctor_id_redirect = doc_info['doctor_id']
        if doc_info.get('user_type') != 'doctor': flash("Doc not of doctor.", "warning"); raise ValueError("Doc owner mismatch")

        connection.autocommit = False
        cursor = connection.cursor()
        cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s", (document_id,))
        deleted_rows = cursor.rowcount

        if deleted_rows > 0:
            admin_id = get_current_user_id_int()
            if admin_id:
                cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'document_deleted', %s, %s, 'doctor_documents', %s)",
                               (doctor_id_redirect, f"Deleted doc: {doc_info.get('file_name', 'N/A')}", admin_id, document_id))
            connection.commit()
            
            file_path_relative = doc_info.get('file_path')
            upload_folder_base = current_app.config.get('UPLOAD_FOLDER_DOCS') # Use specific config
            if upload_folder_base and file_path_relative:
                file_path_absolute = os.path.join(upload_folder_base, file_path_relative)
                try:
                    if os.path.exists(file_path_absolute): os.remove(file_path_absolute)
                    flash("Document deleted successfully (Record and File).", "success")
                except OSError as e: flash(f"Record deleted, but error deleting file: {e}", "warning"); current_app.logger.error(f"File delete error for {file_path_absolute}: {e}")
            else: flash("Document record deleted.", "success" if not file_path_relative else "warning") # Warning if path was expected but missing from config
        else: flash("Document record not found or already deleted.", "warning")

    except (ValueError, mysql.connector.Error, ConnectionError, RuntimeError) as err: # Catch specific and general errors
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"Error deleting document: {err}", "danger")
        current_app.logger.error(f"Doc delete error for ID {document_id}: {err}", exc_info=True)
    finally:
        if 'cursor_dict' in locals() and cursor_dict and not cursor_dict.closed: cursor_dict.close()
        if cursor and not cursor.closed : cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
            
    return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id_redirect) if doctor_id_redirect else url_for('Doctors_Management.index'))


# Delete Doctor Routes (confirmation and actual delete)
# These remain largely the same but ensure UPLOAD_FOLDER_DOCS is used for file paths

@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>/confirm', methods=['GET']) # Changed route slightly for clarity
@login_required
def delete_doctor_confirmation(doctor_id):
     if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
     doctor_info = get_user_basic_info(doctor_id, expected_type='doctor')
     if not doctor_info:
          flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
     return render_template('Admin_Portal/Doctors/delete_doctor_confirmation.html', doctor=doctor_info)

@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    connection = None; cursor = None; cursor_dict = None
    doctor_username = "Unknown"; documents_to_delete = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB Connection failed.")
        
        # Fetch info needed for logging and file deletion before actual deletion
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT username FROM users WHERE user_id = %s AND user_type = 'doctor'", (doctor_id,))
        user_res = cursor_dict.fetchone()
        if user_res: doctor_username = user_res['username']
        else: flash("Doctor user not found for deletion.", "danger"); raise ValueError("User not found")

        cursor_dict.execute("SELECT file_path FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        documents_to_delete = cursor_dict.fetchall()
        cursor_dict.close(); cursor_dict = None

        connection.autocommit = False
        cursor = connection.cursor()

        # Explicitly delete documents from DB first (CASCADE will also do it, but good for logging count)
        cursor.execute("DELETE FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        doc_del_count = cursor.rowcount
        
        admin_id = get_current_user_id_int()
        if admin_id:
            action_details = f"Admin deleted doctor account {doctor_username} (ID: {doctor_id}), {doc_del_count} documents."
            cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'doctor_deleted', %s, %s, 'users', %s)",
                           (doctor_id, action_details, admin_id, doctor_id))
        
        # Delete from users table (CASCADE should handle doctors table)
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'doctor'", (doctor_id,))
        deleted_user_rows = cursor.rowcount

        if deleted_user_rows == 0: # User was not a doctor or already deleted
            connection.rollback() # Rollback audit log and doc delete if user delete failed
            flash(f"Doctor user (ID: {doctor_id}) not found or not a doctor. No user deleted.", "warning")
            return redirect(url_for('Doctors_Management.index'))

        connection.commit()
        
        # Delete files from filesystem AFTER successful DB commit
        upload_folder_base = current_app.config.get('UPLOAD_FOLDER_DOCS') # Use specific config
        if upload_folder_base and documents_to_delete:
            for doc in documents_to_delete:
                file_path_relative = doc.get('file_path')
                if file_path_relative:
                    file_path_absolute = os.path.join(upload_folder_base, file_path_relative)
                    try:
                        if os.path.exists(file_path_absolute): os.remove(file_path_absolute)
                    except OSError as e: current_app.logger.error(f"Error deleting file {file_path_absolute}: {e}")
        
        flash(f"Doctor '{doctor_username}' and associated data deleted successfully.", "success")

    except (ValueError, mysql.connector.Error, ConnectionError, RuntimeError) as err:
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"Error deleting doctor: {err}", "danger")
        current_app.logger.error(f"Error deleting doctor {doctor_id} ('{doctor_username}'): {err}", exc_info=True)
    finally:
        if 'cursor_dict' in locals() and cursor_dict and not cursor_dict.closed : cursor_dict.close()
        if cursor and not cursor.closed : cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
    return redirect(url_for('Doctors_Management.index'))