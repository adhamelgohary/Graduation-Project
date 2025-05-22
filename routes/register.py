# /auth/register.py
import os
import re
import uuid
from datetime import datetime, date
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app, jsonify)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from db import get_db_connection

register_bp = Blueprint('register', __name__, template_folder="../templates")

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS')
    if not allowed_extensions:
        current_app.logger.error("ALLOWED_DOC_EXTENSIONS not found in app config!")
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def is_valid_email(email):
    return re.match(EMAIL_REGEX, email) is not None

def get_departments():
    departments_list = []
    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT department_id, name FROM departments ORDER BY name ASC")
            departments_list = cursor.fetchall()
        else: current_app.logger.error('get_departments: Failed to get/connect to DB.')
    except mysql.connector.Error as err: current_app.logger.error(f"Error fetching departments: {err}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return departments_list

def get_specializations(department_id=None):
    specializations_list = []
    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            query = "SELECT specialization_id, name, department_id FROM specializations"
            params = []
            if department_id:
                query += " WHERE department_id = %s"
                params.append(department_id)
            query += " ORDER BY name ASC"
            cursor.execute(query, tuple(params))
            specializations_list = cursor.fetchall()
        else: current_app.logger.error('get_specializations: Failed to get/connect to DB.')
    except mysql.connector.Error as err: current_app.logger.error(f"Error fetching specializations: {err} (Dept ID: {department_id})")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations_list

@register_bp.route('/get_specializations_for_department/<int:department_id>', methods=['GET'])
def get_specializations_for_department_route(department_id):
    if not department_id: return jsonify({'error': 'Department ID is required'}), 400
    specializations = get_specializations(department_id=department_id)
    specializations_for_frontend = [{'specialization_id': s['specialization_id'], 'name': s['name']} for s in specializations]
    return jsonify(specializations_for_frontend)

@register_bp.route('/register', methods=['GET', 'POST'])
def register_route():
    all_departments = get_departments()
    specializations_for_selected_dept = []

    if request.method == 'GET' and not all_departments:
        flash('Could not load departments list. Please try again later or contact support.', 'warning')
    
    if request.method == 'POST':
        form_department_id_str = request.form.get('department_id')
        if form_department_id_str:
            try:
                form_department_id_int = int(form_department_id_str)
                specializations_for_selected_dept = get_specializations(department_id=form_department_id_int)
            except ValueError: current_app.logger.warning(f"Invalid department_id POST data: {form_department_id_str}")

        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        user_type = request.form.get('user_type')
        phone = request.form.get('phone', '').strip() or None
        country = request.form.get('country', 'United States').strip()
        date_of_birth = request.form.get('date_of_birth') or None
        gender = request.form.get('gender') or 'unknown'
        insurance_provider_name = request.form.get('insurance_provider', '').strip() or None
        insurance_policy_number = request.form.get('insurance_policy_number', '').strip() or None
        insurance_group_number = request.form.get('insurance_group_number', '').strip() or None
        department_id_str = request.form.get('department_id')
        specialization_id_str = request.form.get('specialization_id')
        license_number = request.form.get('license_number', '').strip() or None
        license_state = request.form.get('license_state', '').strip() or None
        license_expiration = request.form.get('license_expiration') or None
        doctor_files_map = {
            'id_document': 'id_document_path',
            'license_document': 'license_document_path',
            'specialization_document': 'specialization_document_path',
            'other_document': 'other_document_path'
        }
        uploaded_files_data = {}
        errors = []
        allowed_doc_extensions_str = ", ".join(current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf'}))

        if not all([username, email, first_name, last_name, user_type]):
            errors.append('Please fill in all required common fields (*).')
        if not is_valid_email(email):
            errors.append('Please enter a valid email address.')

        if user_type: 
            if not password or not confirm_password:
                errors.append(f'Password and confirmation are required for {user_type}s.')
            elif password != confirm_password:
                errors.append('Passwords do not match.')
            elif len(password) < 8:
                errors.append('Password must be at least 8 characters.')
        
        department_id_int = None
        specialization_id_int = None

        if user_type == 'patient':
            if not date_of_birth: errors.append('Date of Birth is required for patients.')
            else:
                try:
                    dob_obj = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
                    if dob_obj >= date.today(): errors.append('Date of Birth must be in the past.')
                except ValueError: errors.append('Invalid Date of Birth format (YYYY-MM-DD).')
            if not gender or gender == 'unknown': errors.append('Gender is required for patients.')
        
        elif user_type == 'doctor':
            if not department_id_str: errors.append('Department is required for professionals.')
            else:
                try:
                    department_id_int = int(department_id_str)
                    if not any(dept['department_id'] == department_id_int for dept in all_departments):
                        errors.append('Invalid department selected.')
                except ValueError: errors.append('Invalid department ID format.')
            
            if not specialization_id_str: errors.append('Specialization is required for professionals.')
            elif department_id_int:
                current_dept_specializations = get_specializations(department_id=department_id_int)
                try:
                    specialization_id_int = int(specialization_id_str)
                    if not any(spec['specialization_id'] == specialization_id_int and spec['department_id'] == department_id_int for spec in current_dept_specializations):
                        errors.append('Invalid specialization selected for the chosen department.')
                except ValueError: errors.append('Invalid specialization ID format.')
            
            if not license_number: errors.append('License Number is required for professionals.')
            if not license_state: errors.append('License State is required for professionals.')
            if not license_expiration: errors.append('License Expiration Date is required for professionals.')
            else:
                try:
                    exp_date = datetime.strptime(license_expiration, '%Y-%m-%d').date()
                    if exp_date < date.today(): errors.append('License Expiration Date cannot be in the past.')
                except ValueError: errors.append('Invalid License Expiration Date format (YYYY-MM-DD).')
            
            for form_field_name, db_column_name in doctor_files_map.items():
                file = request.files.get(form_field_name)
                if file and file.filename:
                    if allowed_file(file.filename):
                        uploaded_files_data[db_column_name] = {'file_obj': file, 'saved_relative_path': None}
                    else:
                        errors.append(f'Invalid file type for {form_field_name.replace("_", " ").title()}. Allowed: {allowed_doc_extensions_str}.')
        
        elif not user_type: errors.append('Please select an account type (Patient or Doctor).')
        else: errors.append('Invalid user type selected.')

        if errors:
            for error in errors: flash(error, 'danger')
            return render_template('Register.html',
                                   form_data=request.form,
                                   departments=all_departments,
                                   specializations_for_selected_dept=specializations_for_selected_dept)

        connection = None; cursor = None; saved_file_absolute_paths = []
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed.")
            connection.autocommit = False 
            cursor = connection.cursor(dictionary=True)

            cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s LIMIT 1", (email, username))
            existing_user = cursor.fetchone()
            cursor.execute("SELECT id FROM pending_registrations WHERE (email = %s OR username = %s) AND status != 'rejected' LIMIT 1", (email, username))
            pending_user = cursor.fetchone()

            if existing_user or pending_user:
                flash_message = 'An account with this Email or Username already exists.'
                if pending_user: flash_message += ' Your previous registration is pending approval or requires attention.'
                flash(flash_message, 'warning')
                if cursor: cursor.close()
                if connection and connection.is_connected(): connection.close()
                return render_template('Register.html', form_data=request.form, departments=all_departments, specializations_for_selected_dept=specializations_for_selected_dept)

            cursor.close()
            cursor = connection.cursor()

            if user_type == 'doctor':
                # ... (Doctor registration logic - remains the same) ...
                upload_folder_docs_abs = current_app.config.get('UPLOAD_FOLDER_DOCS')
                if not upload_folder_docs_abs or not os.path.isdir(upload_folder_docs_abs):
                    current_app.logger.error(f"UPLOAD_FOLDER_DOCS '{upload_folder_docs_abs}' invalid.")
                    raise ValueError("Server configuration error: Upload directory missing.")

                for db_column_name, file_data in uploaded_files_data.items():
                    file = file_data['file_obj']
                    original_secure = secure_filename(file.filename)
                    base, ext = os.path.splitext(original_secure)
                    unique_filename = f"{uuid.uuid4().hex}_{base[:50]}{ext}"
                    save_path_abs = os.path.join(upload_folder_docs_abs, unique_filename)
                    try: relative_path_for_db = os.path.relpath(save_path_abs, current_app.static_folder).replace("\\", "/")
                    except ValueError: relative_path_for_db = os.path.join('uploads', 'doctor_docs', unique_filename).replace("\\", "/"); current_app.logger.warning(f"Doc path fallback: {relative_path_for_db}")
                    try:
                        os.makedirs(os.path.dirname(save_path_abs), exist_ok=True)
                        file.save(save_path_abs)
                        uploaded_files_data[db_column_name]['saved_relative_path'] = relative_path_for_db
                        saved_file_absolute_paths.append(save_path_abs)
                    except Exception as save_err: raise IOError(f"Failed to save {db_column_name}: {save_err}")

                hashed_password_for_doctor = generate_password_hash(password) 
                base_insert_columns = [
                    "email", "first_name", "last_name", "username", "password", 
                    "phone", "country", "user_type_requested", 
                    "department_id", "specialization_id", 
                    "license_number", "license_state", "license_expiration", "date_submitted", "status"
                ]
                pending_data_values = [
                    email, first_name, last_name, username, hashed_password_for_doctor, 
                    phone, country, 'doctor', 
                    department_id_int, specialization_id_int, 
                    license_number, license_state, license_expiration, datetime.now(), 'pending'
                ]
                dynamic_file_columns = []
                for db_col, file_info in uploaded_files_data.items():
                    if file_info['saved_relative_path']:
                        dynamic_file_columns.append(db_col)
                        pending_data_values.append(file_info['saved_relative_path'])
                all_insert_columns = base_insert_columns + dynamic_file_columns
                insert_values_placeholders = ["%s"] * len(all_insert_columns)
                query_pending = f"""INSERT INTO pending_registrations ({", ".join(all_insert_columns)}) VALUES ({", ".join(insert_values_placeholders)})"""
                cursor.execute(query_pending, tuple(pending_data_values))
                pending_reg_id = cursor.lastrowid
                if not pending_reg_id: raise Exception("Failed to get lastrowid for pending reg.")
                connection.commit()
                flash('Registration submitted for approval.', 'info')
                return redirect(url_for('login.login_route'))

            elif user_type == 'patient':
                # 1. Insert into users table
                hashed_password_for_patient = generate_password_hash(password)
                now_dt = datetime.now()
                query_user = """INSERT INTO users (username, email, password, first_name, last_name, user_type, phone, country, account_status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)"""
                cursor.execute(query_user, (username, email, hashed_password_for_patient, first_name, last_name, user_type, phone, country, now_dt, now_dt))
                user_id = cursor.lastrowid
                if not user_id:
                    raise Exception("Failed to create user record for patient.")
                current_app.logger.info(f"Patient user record created with ID: {user_id}. Trigger will create patients table entry.")

                # 2. The trigger `after_users_insert_professional` is expected to create the initial `patients` record.
                #    Now, UPDATE that record with specific details from the form.
                
                insurance_provider_id = None
                if insurance_provider_name:
                    # Temporarily switch to dict cursor for this SELECT if not already
                    was_dict_cursor = isinstance(cursor, mysql.connector.cursor.MySQLCursorDict)
                    if not was_dict_cursor:
                        cursor.close()
                        cursor = connection.cursor(dictionary=True)
                    
                    cursor.execute("SELECT id FROM insurance_providers WHERE provider_name = %s AND is_active = TRUE", (insurance_provider_name,))
                    provider_result = cursor.fetchone()
                    insurance_provider_id = provider_result['id'] if provider_result else None
                    
                    if not was_dict_cursor: # Switch back if we changed it
                        cursor.close()
                        cursor = connection.cursor()
                    if not insurance_provider_id:
                         current_app.logger.warning(f"Insurance provider '{insurance_provider_name}' not found for user {user_id}")


                # Formulate the UPDATE query for the patients table
                update_patient_query = """
                    UPDATE patients
                    SET date_of_birth = %s,
                        gender = %s,
                        insurance_provider_id = %s,
                        insurance_policy_number = %s,
                        insurance_group_number = %s
                    WHERE user_id = %s 
                """
                # Ensure all values are provided, even if None for optional fields
                patient_update_params = (
                    date_of_birth,
                    gender,
                    insurance_provider_id, # Can be None
                    insurance_policy_number, # Can be None
                    insurance_group_number, # Can be None
                    user_id
                )
                cursor.execute(update_patient_query, patient_update_params)

                if cursor.rowcount == 0:
                    # This means the trigger might have failed or there's a logic issue
                    # where the patients record wasn't created by the trigger.
                    current_app.logger.error(f"CRITICAL: Patients record for user_id {user_id} was NOT found or NOT updated. Trigger might have failed.")
                    # Depending on desired behavior, you might want to raise an exception here
                    # or attempt an INSERT as a fallback (though that risks the original duplicate error if trigger *sometimes* works)
                    # For now, log and proceed to commit, but this indicates a problem.
                    flash("User account created, but there was an issue updating patient-specific details. Please contact support if information is missing.", "warning")
                else:
                    current_app.logger.info(f"Patients record for user_id {user_id} updated successfully.")

                connection.commit()
                flash('Registration successful! You can now log in.', 'success')
                return redirect(url_for('login.login_route'))
            else:
                raise ValueError("Invalid user_type after initial validation.")

        except (mysql.connector.Error, ConnectionError, ValueError, IOError, Exception) as err:
            error_msg_str = str(err)
            current_app.logger.error(f"Registration Error for user {username} ({email}): {error_msg_str}", exc_info=True)
            if connection and connection.is_connected():
                try: connection.rollback(); current_app.logger.info("Rollback executed.")
                except mysql.connector.Error as rb_err: current_app.logger.error(f"Error during rollback: {rb_err}")
            if saved_file_absolute_paths:
                for cleanup_path in saved_file_absolute_paths:
                    try:
                        if os.path.exists(cleanup_path): os.remove(cleanup_path); current_app.logger.info(f"Cleaned up: {cleanup_path}")
                    except OSError as clean_err: current_app.logger.error(f"Error cleaning file {cleanup_path}: {clean_err}")
            flash(f'An error occurred: {error_msg_str}. Please try again.', 'danger')
            return render_template('Register.html', form_data=request.form, departments=all_departments, specializations_for_selected_dept=specializations_for_selected_dept)
        finally:
            if cursor:
                try: cursor.close()
                except Exception as e_cur: current_app.logger.error(f"Error closing cursor in finally: {e_cur}")
            if connection and connection.is_connected():
                try:
                    if connection.autocommit is False: connection.autocommit = True
                    connection.close()
                except Exception as e_conn: current_app.logger.error(f"Error closing/resetting connection: {e_conn}")

    return render_template('Register.html', form_data={}, departments=all_departments, specializations_for_selected_dept=[])