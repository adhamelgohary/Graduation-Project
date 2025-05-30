# Doctors_Management.py
import os
import datetime
from flask import (Blueprint, render_template, request, flash, redirect, url_for,
                   current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename as werkzeug_secure_filename # Use werkzeug's for basic cleaning
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from math import ceil
import mysql.connector
import re
import uuid # For generating unique filenames

# Assuming directory_configs.py is in a 'utils' package accessible from here
# If Doctors_Management.py is in routes/Admin_Portal/ and utils is ../../utils/
# from ...utils.directory_configs import get_relative_path_for_db
# For simplicity, let's assume direct import works due to PYTHONPATH or package structure
try:
    from utils.directory_configs import get_relative_path_for_db
except ImportError:
    current_app.logger.error("Failed to import get_relative_path_for_db from utils.directory_configs in Doctors_Management")
    # Fallback or raise critical error if this util is essential
    def get_relative_path_for_db(absolute_filepath): # Dummy fallback
        return None


Doctors_Management = Blueprint('Doctors_Management', __name__, template_folder="../templates/Admin_Portal/Doctors") # More specific template folder

# --- Constants ---
PER_PAGE_DOCTORS = 10
ALLOWED_DOCTOR_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'specialization_name', 'department_name',
    'license_number', 'verification_status', 'created_at', 'account_status'
}
VALID_DOCUMENT_TYPES = ['license', 'certification', 'identity', 'education', 'other'] # Should align with DB ENUM
DEFAULT_ACCOUNT_STATUSES = ['active', 'inactive', 'suspended', 'pending']
DEFAULT_VERIFICATION_STATUSES = ['pending', 'approved', 'rejected', 'pending_info']

# --- Utility for secure filenames (can be moved to a shared utils.py) ---
def generate_secure_filesystem_name(original_filename):
    """Generates a secure and unique filename for storing on the filesystem."""
    cleaned_filename = werkzeug_secure_filename(original_filename)
    base, ext = os.path.splitext(cleaned_filename)
    # Limit base name length to prevent issues, ensure it's not empty
    base = base[:100] if base else "file" 
    return f"{uuid.uuid4().hex}_{base}{ext}"

# --- Helper Functions ---
# (get_enum_values, get_all_specializations, get_all_departments, get_doctor_details, get_user_basic_info, get_current_user_id_int, is_valid_email - remain largely the same)
# Minor adjustment in get_doctor_details for profile_photo_url consistency.

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
            if table_name == 'doctor_documents' and column_name == 'document_type': return VALID_DOCUMENT_TYPES # Fallback for doc types
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
    
    if not enum_values: 
        if table_name == 'users' and column_name == 'account_status': return DEFAULT_ACCOUNT_STATUSES
        if table_name == 'doctors' and column_name == 'verification_status': return DEFAULT_VERIFICATION_STATUSES
        if table_name == 'doctor_documents' and column_name == 'document_type': return VALID_DOCUMENT_TYPES
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

def get_all_departments():
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
                u.account_status, u.user_type, 
                u.created_at AS user_created_at, u.updated_at AS user_updated_at,
                d.license_number, d.license_state, d.license_expiration, d.npi_number,
                d.medical_school, d.graduation_year, d.certifications, d.biography,
                d.clinic_address, d.accepting_new_patients, d.verification_status,
                d.approval_date, d.specialization_id, s.name AS specialization_name,
                d.department_id, dep.name AS department_name,
                d.profile_photo_url
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id 
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """
        cursor.execute(query, (doctor_id,))
        doctor_data = cursor.fetchone()
        if not doctor_data: return None

        if not doctor_data.get('profile_photo_url'): # Ensure None if empty for template logic
            doctor_data['profile_photo_url'] = None

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

def is_valid_email(email):
    if not email: return False
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email) is not None


# --- Routes ---
@Doctors_Management.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route')) # Replace with actual login route

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by_frontend = request.args.get('sort_by', 'last_name').lower()
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

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
        else: sort_column_sql = "u.last_name" 

        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.created_at,
                   u.account_status, s.name AS specialization_name, dep.name AS department_name,
                   d.license_number, d.verification_status, d.profile_photo_url
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
        'Admin_Portal/Doctors/view_doctors.html', # Assumes view_doctors.html is in Admin_Portal/Doctors/
        doctors=doctors, page=page, total_pages=total_pages,
        total_items=total_items, search_term=search_term,
        sort_by=sort_by_frontend, sort_order=sort_order
    )

@Doctors_Management.route('/admin/doctors/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    doctor = get_doctor_details(doctor_id)
    if not doctor:
        flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
    
    doc_types_for_upload = get_enum_values('doctor_documents', 'document_type')

    max_content_length = current_app.config.get('MAX_CONTENT_LENGTH')
    if isinstance(max_content_length, (int, float)) and max_content_length > 0:
        max_upload_size_display = str(int(max_content_length // (1024 * 1024)))
    else:
        max_upload_size_display = 'Not Set' # Or a default like '2'

    # This specific config key was used in template, but we'll use get_relative_path_for_db and UPLOAD_FOLDER_DOCS
    # For displaying existing docs, the 'file_path' from DB (which is relative to static) is enough.
    # docs_relative_path_base = current_app.config.get('UPLOAD_FOLDER_DOCS_RELATIVE_PATH', 'uploads/doctor_documents')

    return render_template(
        'Admin_Portal/Doctors/doctor_details.html', # Assumes doctor_details.html is in Admin_Portal/Doctors/
        doctor=doctor,
        valid_document_types=doc_types_for_upload,
        max_upload_size_display=max_upload_size_display
        # docs_relative_path_base is no longer needed if doc.file_path is already correct for url_for
    )

# add_doctor_step1, add_doctor_step2_form, add_doctor_step2_submit, edit_doctor
# These routes are primarily for DB data, not direct file uploads from admin panel in this flow.
# Profile photo upload for doctors is handled in their own settings_management.py.
# Admin can edit the text fields, but not typically upload files for the doctor this way,
# except for "doctor_documents".

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
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        errors = []
        if not all([username, email, first_name, last_name, password, confirm_password]):
            errors.append("All fields including password are required for Step 1.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if password and len(password) < 8: 
            errors.append("Password must be at least 8 characters.")
        if not is_valid_email(email):
            errors.append("Invalid email format.")

        if errors:
            for error in errors: flash(error, "danger")
            form_data_cleared = request.form.to_dict()
            form_data_cleared['password'] = ''
            form_data_cleared['confirm_password'] = ''
            return render_template('add_doctor_step1.html', form_data=form_data_cleared)

        connection = None; cursor = None; user_id = None
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
            
            connection.autocommit = False 
            cursor = connection.cursor()

            cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
            if cursor.fetchone():
                flash("Email or Username already exists.", "danger")
                if connection.is_connected(): connection.rollback()
                form_data_cleared = request.form.to_dict()
                form_data_cleared['password'] = ''
                form_data_cleared['confirm_password'] = ''
                return render_template('add_doctor_step1.html', form_data=form_data_cleared)

            hashed_password = generate_password_hash(password) 
            now_dt = datetime.datetime.now()
            cursor.execute("""
                INSERT INTO users (username, email, password, first_name, last_name,
                                  user_type, phone, account_status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 'doctor', %s, 'pending', %s, %s)
            """, (username, email, hashed_password, first_name, last_name, phone, now_dt, now_dt))
            user_id = cursor.lastrowid
            
            connection.commit()
            current_app.logger.info(f"Step 1: Committed doctor USER insert for {username} (ID: {user_id}). Trigger handles doctors record.")
            flash("Step 1 complete: Doctor user account created. Now add professional details.", "info")
            return redirect(url_for('Doctors_Management.add_doctor_step2_form', user_id=user_id))

        except mysql.connector.Error as db_err:
            if connection and connection.is_connected(): connection.rollback()
            flash(f"Database error: {db_err}", "danger"); current_app.logger.error(f"DB Error add_doctor_step1: {db_err}")
        except Exception as e:
            if connection and connection.is_connected(): connection.rollback() 
            flash(f"Error: {str(e)}", "danger"); current_app.logger.error(f"Error add_doctor_step1: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected():
                if not connection.autocommit: connection.autocommit = True 
                connection.close()
        
        form_data_cleared = request.form.to_dict()
        form_data_cleared['password'] = ''
        form_data_cleared['confirm_password'] = ''
        return render_template('add_doctor_step1.html', form_data=form_data_cleared) 
        
    return render_template('add_doctor_step1.html', form_data={})

@Doctors_Management.route('/admin/doctors/add/step2/<int:user_id>', methods=['GET'])
@login_required
def add_doctor_step2_form(user_id): 
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    all_specializations = get_all_specializations()
    all_departments = get_all_departments() 
    current_year = datetime.datetime.now().year
    
    existing_doctor_details = get_doctor_details(user_id) or {} 
    form_data = {
        'specialization_id': existing_doctor_details.get('specialization_id'),
        'department_id': existing_doctor_details.get('department_id'),
    }
    return render_template(
        'add_doctor_step2.html',
        user=user_info,
        form_data=form_data, 
        current_year=current_year,
        specializations=all_specializations,
        departments=all_departments
    )
    
@Doctors_Management.route('/admin/doctors/add/step2/submit/<int:user_id>', methods=['POST'])
@login_required
def add_doctor_step2_submit(user_id): 
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    user_info = get_user_basic_info(user_id, expected_type='doctor')
    if not user_info:
        flash("Doctor user account not found or invalid.", "danger")
        return redirect(url_for('Doctors_Management.index'))

    all_specializations = get_all_specializations()
    all_departments = get_all_departments()
    current_year = datetime.datetime.now().year
    
    form_data_for_render = request.form.to_dict() 

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
        return render_template('add_doctor_step2.html',
                               user=user_info, form_data=form_data_for_render,
                               current_year=current_year, specializations=all_specializations, departments=all_departments)

    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB connection failed")
        connection.autocommit = False
        cursor = connection.cursor()

        if npi_number: 
            cursor.execute("SELECT user_id FROM doctors WHERE npi_number = %s AND user_id != %s", (npi_number, user_id))
            if cursor.fetchone():
                flash("NPI number already exists for another doctor.", "danger")
                if connection.is_connected(): connection.rollback()
                return render_template('add_doctor_step2.html', user=user_info, form_data=form_data_for_render, current_year=current_year, specializations=all_specializations, departments=all_departments)
        
        update_doctors_query = """
            UPDATE doctors SET
                department_id = %s, specialization_id = %s, license_number = %s, 
                license_state = %s, license_expiration = %s, accepting_new_patients = %s, 
                npi_number = %s, medical_school = %s, graduation_year = %s, 
                certifications = %s, biography = %s, clinic_address = %s,
                verification_status = 'pending_info', 
                updated_at = NOW()
            WHERE user_id = %s
        """
        update_doctors_params = (
            department_id_int, specialization_id_int, license_number, license_state,
            license_expiration, accepting_new_patients, npi_number,
            medical_school, graduation_year_int, certifications, biography,
            clinic_address, user_id
        )

        cursor.execute(update_doctors_query, update_doctors_params)
        rows_affected = cursor.rowcount

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
    return render_template('add_doctor_step2.html', user=user_info, form_data=form_data_for_render, current_year=current_year, specializations=all_specializations, departments=all_departments)


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
    all_departments = get_all_departments() 

    if request.method == 'GET':
        doctor_for_render = get_doctor_details(doctor_id) 
        if not doctor_for_render:
             flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
        doctor_for_render.pop('new_password', None)
        doctor_for_render.pop('confirm_password', None)
        return render_template('Admin_Portal/Doctors/edit_doctor.html',
                               doctor=doctor_for_render, form_data=doctor_for_render,
                               current_year=current_year, account_statuses=account_statuses_list,
                               specializations=all_specializations, departments=all_departments,
                               verification_statuses=verification_statuses_list)

    current_doctor_data = get_doctor_details(doctor_id)
    if not current_doctor_data:
        flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

    form_data_for_render = request.form.to_dict()
    form_data_for_render.update({
        'user_id': doctor_id, 'documents': current_doctor_data.get('documents', []),
        'username': current_doctor_data.get('username'),
        'user_created_at': current_doctor_data.get('user_created_at'),
        'profile_photo_url': current_doctor_data.get('profile_photo_url'), 
        'accepting_new_patients': 1 if request.form.get('accepting_new_patients') else 0,
        'license_expiration_formatted': form_data_for_render.get('license_expiration') or current_doctor_data.get('license_expiration_formatted','')
    })
    form_data_for_render_secure = form_data_for_render.copy()
    form_data_for_render_secure['new_password'] = ''
    form_data_for_render_secure['confirm_password'] = ''
    
    selected_spec_id_str = form_data_for_render.get('specialization_id')
    if selected_spec_id_str:
        try:
            selected_spec_id = int(selected_spec_id_str)
            form_data_for_render_secure['specialization_name'] = next((s['name'] for s in all_specializations if s['specialization_id'] == selected_spec_id), 'Unknown')
        except (ValueError, TypeError): pass
    
    selected_dept_id_str = form_data_for_render.get('department_id')
    if selected_dept_id_str:
        try:
            selected_dept_id = int(selected_dept_id_str)
            form_data_for_render_secure['department_name'] = next((d['name'] for d in all_departments if d['department_id'] == selected_dept_id), 'Unknown')
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
    
    # Admin edit form does not handle profile_photo_url upload directly.
    # That's done by doctor in their settings or a separate admin tool for it.
    # If admin could change it, logic for file upload and setting profile_photo_url_to_update would be here.
    profile_photo_url_to_update = None 


    errors = []
    if not all([first_name, last_name, email, account_status, verification_status, department_id_str, specialization_id_str, license_number, license_state, license_expiration]):
        errors.append("Name, Email, Statuses, Department, Specialization, and License details are required.")
    if not account_status or account_status not in account_statuses_list: errors.append("Invalid account status.")
    if not verification_status or verification_status not in verification_statuses_list: errors.append("Invalid verification status.")
    if not is_valid_email(email): errors.append("Invalid email format.")

    department_id_int = None; specialization_id_int = None; graduation_year_int = None
    try: department_id_int = int(department_id_str) if department_id_str else None
    except ValueError: errors.append("Invalid Department ID.")
    try: specialization_id_int = int(specialization_id_str) if specialization_id_str else None
    except ValueError: errors.append("Invalid Specialization ID.")
    try: graduation_year_int = int(graduation_year_str) if graduation_year_str else None
    except ValueError: errors.append("Invalid Graduation Year.")
    
    password_to_update_hashed = None
    if new_password or confirm_password:
        if not new_password: errors.append("New Password is required to change password.")
        elif not confirm_password: errors.append("Confirm Password is required to change password.")
        elif new_password != confirm_password: errors.append("New passwords do not match.")
        elif len(new_password) < 8: errors.append("New password must be at least 8 characters.")
        else: password_to_update_hashed = generate_password_hash(new_password)

    if errors:
        for error in errors: flash(error, "danger")
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render_secure, form_data=form_data_for_render_secure, current_year=current_year, account_statuses=account_statuses_list, specializations=all_specializations, departments=all_departments, verification_statuses=verification_statuses_list)

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

        doctor_update_fields = [
            "department_id = %s", "specialization_id = %s", "license_number = %s", "license_state = %s",
            "license_expiration = %s", "accepting_new_patients = %s", "npi_number = %s",
            "medical_school = %s", "graduation_year = %s", "certifications = %s",
            "biography = %s", "clinic_address = %s", "verification_status = %s",
            "updated_at = NOW()"
        ]
        doctor_params_list = [
            department_id_int, specialization_id_int, license_number, license_state,
            license_expiration, accepting_new_patients, npi_number,
            medical_school, graduation_year_int, certifications, biography,
            clinic_address, verification_status
        ]
        
        if profile_photo_url_to_update is not None: # Check if admin is allowed to set this
             doctor_update_fields.append("profile_photo_url = %s")
             doctor_params_list.append(profile_photo_url_to_update)


        doctor_params_list.append(doctor_id)
        doctor_update_sql = f"UPDATE doctors SET {', '.join(doctor_update_fields)} WHERE user_id = %s"
        
        cursor.execute(doctor_update_sql, tuple(doctor_params_list))
        doctor_rows_affected = cursor.rowcount
        
        if user_rows_affected > 0 or doctor_rows_affected > 0:
            current_admin_id = get_current_user_id_int()
            action_details = f"Doctor ID {doctor_id} updated. User rows: {user_rows_affected}, Doctor rows: {doctor_rows_affected}."
            if password_to_update_hashed: action_details += " Password changed."
            if profile_photo_url_to_update: action_details += " Profile photo URL updated by admin."
            if current_admin_id:
                try:
                    cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'doctor_updated', %s, %s, 'users_doctors', %s)",
                                   (doctor_id, action_details, current_admin_id, doctor_id))
                except Exception as audit_err: raise RuntimeError(f"Audit log failed: {audit_err}")
        
        connection.commit()
        flash_msg = "Doctor updated successfully" if user_rows_affected > 0 or doctor_rows_affected > 0 else "No changes detected."
        if password_to_update_hashed: flash_msg += " (Password Changed)"
        if profile_photo_url_to_update: flash_msg += " (Profile Photo URL updated)"
        flash(flash_msg, "success" if user_rows_affected > 0 or doctor_rows_affected > 0 else "info")

    except (mysql.connector.Error, ConnectionError, ValueError, RuntimeError) as err: 
        if connection and connection.is_connected(): connection.rollback()
        if isinstance(err, ValueError) and "conflict" not in str(err).lower(): 
            flash(str(err), "danger")
        elif not isinstance(err, ValueError): 
             flash(f"Error updating doctor: {err}", "danger")
        current_app.logger.error(f"Error editing doctor {doctor_id}: {err}", exc_info=True)
        return render_template('Admin_Portal/Doctors/edit_doctor.html', doctor=form_data_for_render_secure, form_data=form_data_for_render_secure, current_year=current_year, account_statuses=account_statuses_list, specializations=all_specializations, departments=all_departments, verification_statuses=verification_statuses_list)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()
    return redirect(redirect_target)


@Doctors_Management.route('/admin/doctors/upload-document/<int:doctor_id>', methods=['POST'])
@login_required
def upload_doctor_document(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    
    doctor_user = get_user_basic_info(doctor_id, expected_type='doctor')
    if not doctor_user:
         flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))

    if 'document' not in request.files or request.files['document'].filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    file = request.files['document']
    document_type = request.form.get('document_type')
    
    # Get valid document types from ENUM or config
    valid_doc_types_from_db = get_enum_values('doctor_documents', 'document_type')
    if not document_type or document_type not in valid_doc_types_from_db:
        flash(f'Invalid document type. Valid types: {", ".join(valid_doc_types_from_db)}', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))

    # Get allowed extensions for documents
    allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'})
    original_filename_cleaned = werkzeug_secure_filename(file.filename)
    if not original_filename_cleaned.split('.')[-1].lower() in allowed_extensions :
        flash(f'Invalid file type. Allowed: {", ".join(allowed_extensions)}', 'danger')
        return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id))


    connection = None; cursor = None; saved_doc_absolute_path = None
    try:
        # This is the base directory where all doctor documents are stored,
        # e.g., /abs/path/to/your_project/static/uploads/doctor_docs/
        upload_dir_docs_base_absolute = current_app.config.get('UPLOAD_FOLDER_DOCS')
        if not upload_dir_docs_base_absolute: 
            raise ValueError("UPLOAD_FOLDER_DOCS not configured in app.config.")

        # Create a subdirectory for this specific doctor's documents if it doesn't exist
        # e.g., /abs/path/to/your_project/static/uploads/doctor_docs/<doctor_id>/
        # This helps in organizing files and matches the old relative_path_for_db logic.
        # However, the new get_relative_path_for_db will store "uploads/doctor_docs/<doctor_id>/filename.ext"
        # if we save it into such a structure. Let's simplify and put all docs directly in UPLOAD_FOLDER_DOCS for now.
        # If doctor-specific subfolders are desired, adjust `upload_dir_for_this_doctor` and `db_storage_path`.
        
        # For simplicity, save directly into UPLOAD_FOLDER_DOCS.
        # If you want subfolders like `doctor_docs/<doctor_id>/filename.ext`
        # then:
        # doctor_specific_subdir_abs = os.path.join(upload_dir_docs_base_absolute, str(doctor_id))
        # os.makedirs(doctor_specific_subdir_abs, exist_ok=True)
        # filesystem_secure_name = generate_secure_filesystem_name(original_filename_cleaned)
        # saved_doc_absolute_path = os.path.join(doctor_specific_subdir_abs, filesystem_secure_name)
        # file.save(saved_doc_absolute_path)
        # db_storage_path = get_relative_path_for_db(saved_doc_absolute_path) # will be "uploads/doctor_docs/<doctor_id>/unique_name.ext"

        # Current simpler approach: save directly into UPLOAD_FOLDER_DOCS
        os.makedirs(upload_dir_docs_base_absolute, exist_ok=True) # Ensure base dir exists
        filesystem_secure_name = generate_secure_filesystem_name(original_filename_cleaned)
        saved_doc_absolute_path = os.path.join(upload_dir_docs_base_absolute, filesystem_secure_name)
        
        file.save(saved_doc_absolute_path)
        file_size = os.path.getsize(saved_doc_absolute_path)
        current_app.logger.info(f"Admin uploaded doc for Dr {doctor_id}: {saved_doc_absolute_path}")

        db_storage_path = get_relative_path_for_db(saved_doc_absolute_path)
        if not db_storage_path:
            raise ValueError("Could not generate DB storage path for uploaded document.")

        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB Connection failed.")
        connection.autocommit = False
        cursor = connection.cursor()
        
        # Storing original cleaned filename for display, and unique path for storage/linking
        cursor.execute("""
            INSERT INTO doctor_documents 
            (doctor_id, document_type, file_name, file_path, file_size, upload_date) 
            VALUES (%s, %s, %s, %s, %s, NOW())
            """, (doctor_id, document_type, original_filename_cleaned, db_storage_path, file_size))
        doc_id = cursor.lastrowid
        
        admin_id = get_current_user_id_int()
        if admin_id:
            cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'document_upload', %s, %s, 'doctor_documents', %s)",
                           (doctor_id, f"Admin uploaded {document_type}: {original_filename_cleaned}", admin_id, doc_id))
        connection.commit()
        flash("Document uploaded successfully.", "success")

    except (ValueError, IOError, mysql.connector.Error, ConnectionError, RuntimeError) as err:
        if connection and connection.is_connected() and not getattr(connection, 'autocommit', True): connection.rollback()
        flash(f"Error uploading document: {str(err)}", "danger")
        current_app.logger.error(f"Doc upload error by admin for Dr {doctor_id}: {err}", exc_info=True)
        if saved_doc_absolute_path and os.path.exists(saved_doc_absolute_path):
            try: os.remove(saved_doc_absolute_path); current_app.logger.info(f"Cleaned up {saved_doc_absolute_path}")
            except OSError as e_clean: current_app.logger.error(f"Cleanup failed for {saved_doc_absolute_path}: {e_clean}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not getattr(connection, 'autocommit', True): connection.autocommit = True # Reset if changed
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
        # We need doctor_id to redirect, and file_path to delete file from disk.
        cursor_dict.execute("""
            SELECT dd.doctor_id, dd.file_path, dd.file_name, u.user_type 
            FROM doctor_documents dd 
            JOIN doctors d ON dd.doctor_id = d.user_id -- ensure it's a doctor's doc
            JOIN users u ON d.user_id = u.user_id
            WHERE dd.document_id = %s
            """, (document_id,))
        doc_info = cursor_dict.fetchone()
        cursor_dict.close()

        if not doc_info: 
            flash("Document not found or does not belong to a doctor.", "danger")
            raise ValueError("Document not found or invalid.")
        
        doctor_id_redirect = doc_info['doctor_id']
        # No need to check user_type here again if query joins correctly.

        connection.autocommit = False
        cursor = connection.cursor()
        cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s", (document_id,))
        deleted_rows = cursor.rowcount

        if deleted_rows > 0:
            admin_id = get_current_user_id_int()
            if admin_id:
                cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'document_deleted', %s, %s, 'doctor_documents', %s)",
                               (doctor_id_redirect, f"Admin deleted doc: {doc_info.get('file_name', 'N/A')}", admin_id, document_id))
            connection.commit()
            
            db_file_path_relative_to_static = doc_info.get('file_path') # e.g., "uploads/doctor_docs/unique_name.pdf"
            if db_file_path_relative_to_static:
                # Reconstruct absolute path using app.static_folder
                file_to_delete_absolute = os.path.join(current_app.static_folder, db_file_path_relative_to_static)
                try:
                    if os.path.exists(file_to_delete_absolute): 
                        os.remove(file_to_delete_absolute)
                        flash("Document deleted successfully (Record and File).", "success")
                        current_app.logger.info(f"Admin deleted doc file: {file_to_delete_absolute}")
                    else:
                        flash("Document record deleted, but file not found on disk.", "warning")
                        current_app.logger.warning(f"Doc file for deletion not found on disk: {file_to_delete_absolute}")
                except OSError as e: 
                    flash(f"Record deleted, but error deleting file: {e}", "warning")
                    current_app.logger.error(f"File delete error for {file_to_delete_absolute}: {e}")
            else: 
                flash("Document record deleted. No file path was stored.", "info") # Should not happen if uploads are correct
        else: 
            flash("Document record not found or already deleted.", "warning")

    except (ValueError, mysql.connector.Error, ConnectionError, RuntimeError) as err: 
        if connection and connection.is_connected() and not getattr(connection, 'autocommit', True): connection.rollback()
        flash(f"Error deleting document: {str(err)}", "danger")
        current_app.logger.error(f"Doc delete error for ID {document_id}: {err}", exc_info=True)
    finally:
        if 'cursor_dict' in locals() and cursor_dict and not cursor_dict.closed: cursor_dict.close()
        if cursor and not cursor.closed : cursor.close()
        if connection and connection.is_connected():
            if not getattr(connection, 'autocommit', True): connection.autocommit = True
            connection.close()
            
    return redirect(url_for('Doctors_Management.view_doctor', doctor_id=doctor_id_redirect) if doctor_id_redirect else url_for('Doctors_Management.index'))


@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>/confirm', methods=['GET']) 
@login_required
def delete_doctor_confirmation(doctor_id):
     if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
     doctor_info = get_user_basic_info(doctor_id, expected_type='doctor')
     if not doctor_info:
          flash("Doctor not found.", "danger"); return redirect(url_for('Doctors_Management.index'))
     return render_template('delete_doctor_confirmation.html', doctor=doctor_info)

@Doctors_Management.route('/admin/doctors/delete/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    connection = None; cursor = None; cursor_dict = None
    doctor_username = "Unknown"; documents_to_delete_db_paths = []
    profile_photo_db_path = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("DB Connection failed.")
        
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT u.username, d.profile_photo_url FROM users u JOIN doctors d ON u.user_id = d.user_id WHERE u.user_id = %s AND u.user_type = 'doctor'", (doctor_id,))
        user_doc_res = cursor_dict.fetchone()

        if user_doc_res: 
            doctor_username = user_doc_res['username']
            profile_photo_db_path = user_doc_res.get('profile_photo_url') # Path relative to static
        else: 
            flash("Doctor user not found for deletion.", "danger"); raise ValueError("User not found")

        # Get all document paths for this doctor
        cursor_dict.execute("SELECT file_path FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        doc_paths_result = cursor_dict.fetchall()
        documents_to_delete_db_paths = [row['file_path'] for row in doc_paths_result if row['file_path']]
        cursor_dict.close(); cursor_dict = None # Close dict cursor early

        connection.autocommit = False
        cursor = connection.cursor() # Default cursor for operations

        # Note: doctor_documents are deleted via CASCADE when users record is deleted,
        # but we fetched them first to delete files.
        # If CASCADE is not on doctor_documents, uncomment:
        # cursor.execute("DELETE FROM doctor_documents WHERE doctor_id = %s", (doctor_id,))
        # doc_del_count = cursor.rowcount
        
        admin_id = get_current_user_id_int()
        if admin_id:
            action_details = f"Admin initiated deletion of doctor account {doctor_username} (ID: {doctor_id})."
            if profile_photo_db_path: action_details += f" Profile photo '{profile_photo_db_path}' to be deleted."
            if documents_to_delete_db_paths: action_details += f" {len(documents_to_delete_db_paths)} documents to be deleted."
            
            cursor.execute("INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id) VALUES (%s, 'doctor_deletion_initiated', %s, %s, 'users', %s)",
                           (doctor_id, action_details, admin_id, doctor_id))
        
        # Deleting from users will cascade to doctors table due to FK ON DELETE CASCADE
        # and also to doctor_documents if its FK to doctors.user_id has ON DELETE CASCADE
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'doctor'", (doctor_id,))
        deleted_user_rows = cursor.rowcount

        if deleted_user_rows == 0: 
            connection.rollback() 
            flash(f"Doctor user (ID: {doctor_id}) not found or not a doctor. No user deleted.", "warning")
            return redirect(url_for('Doctors_Management.index'))

        connection.commit() # Commit DB changes first
        
        # Now, delete files from filesystem
        static_folder_abs = current_app.static_folder

        # Delete associated doctor documents
        if documents_to_delete_db_paths:
            current_app.logger.info(f"Attempting to delete {len(documents_to_delete_db_paths)} documents for doctor {doctor_id}.")
            for doc_relative_path in documents_to_delete_db_paths:
                doc_absolute_path = os.path.join(static_folder_abs, doc_relative_path)
                try:
                    if os.path.exists(doc_absolute_path): 
                        os.remove(doc_absolute_path)
                        current_app.logger.info(f"Deleted document file: {doc_absolute_path}")
                except OSError as e: 
                    current_app.logger.error(f"Error deleting document file {doc_absolute_path}: {e}")
        
        # Delete associated profile photo
        if profile_photo_db_path:
            profile_photo_absolute_path = os.path.join(static_folder_abs, profile_photo_db_path)
            try:
                if os.path.exists(profile_photo_absolute_path): 
                    os.remove(profile_photo_absolute_path)
                    current_app.logger.info(f"Deleted profile photo file: {profile_photo_absolute_path}")
            except OSError as e: 
                current_app.logger.error(f"Error deleting profile photo file {profile_photo_absolute_path}: {e}")

        flash(f"Doctor '{doctor_username}' and associated data deleted successfully.", "success")

    except (ValueError, mysql.connector.Error, ConnectionError, RuntimeError) as err:
        if connection and connection.is_connected() and not getattr(connection, 'autocommit', True): connection.rollback()
        flash(f"Error deleting doctor: {str(err)}", "danger")
        current_app.logger.error(f"Error deleting doctor {doctor_id} ('{doctor_username}'): {err}", exc_info=True)
    finally:
        if 'cursor_dict' in locals() and cursor_dict and not cursor_dict.closed : cursor_dict.close()
        if cursor and not cursor.closed : cursor.close()
        if connection and connection.is_connected():
            if not getattr(connection, 'autocommit', True): connection.autocommit = True
            connection.close()
    return redirect(url_for('Doctors_Management.index'))