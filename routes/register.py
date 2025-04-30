# /auth/register.py
import os
import re
import uuid
from datetime import datetime, date
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
import mysql.connector
from db import get_db_connection # Assuming db.py exists

register_bp = Blueprint('register', __name__, template_folder="../templates")

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

def allowed_file(filename):
    """Checks if the file extension is allowed based on app config."""
    allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS')
    if not allowed_extensions:
        current_app.logger.error("ALLOWED_DOC_EXTENSIONS not found in app config!")
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def is_valid_email(email):
    return re.match(EMAIL_REGEX, email) is not None

def get_specializations():
    """Fetches active specializations (ID and Name) for the dropdown."""
    specializations = []
    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT specialization_id, name FROM specializations ORDER BY name ASC")
            specializations = cursor.fetchall()
        else:
             current_app.logger.error('get_specializations: Failed to get/connect to DB.')
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching specializations: {err}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations


@register_bp.route('/register', methods=['GET', 'POST'])
def register_route():
    # Consistent 4-space indentation starts here
    available_specializations = get_specializations()
    if not available_specializations and request.method == 'GET':
        flash('Could not load specializations list. Please try again later or contact support.', 'warning')

    allowed_doc_extensions_str = ", ".join(current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf'}))

    if request.method == 'POST':
        # --- Retrieve Form Fields ---
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
        specialization_id_str = request.form.get('specialization_id') or None
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

        # --- Initial Validation ---
        errors = []
        if not all([username, email, first_name, last_name, user_type]):
            errors.append('Please fill in all required common fields (*).')
        if not is_valid_email(email):
             errors.append('Please enter a valid email address.')

        specialization_id = None

        if user_type == 'patient':
            if not password or not confirm_password: errors.append('Password and confirmation are required.')
            elif password != confirm_password: errors.append('Passwords do not match.')
            elif len(password) < 8 : errors.append('Password must be at least 8 characters.')
            if not date_of_birth: errors.append('Date of Birth is required for patients.')
            else:
                try:
                    dob_obj = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
                    if dob_obj >= date.today(): errors.append('Date of Birth must be in the past.')
                except ValueError: errors.append('Invalid Date of Birth format (YYYY-MM-DD).')
            if not gender or gender == 'unknown': errors.append('Gender is required for patients.')

        elif user_type == 'doctor':
            if not specialization_id_str:
                errors.append('Specialization is required.')
            else:
                 try:
                     specialization_id = int(specialization_id_str)
                     if not any(spec['specialization_id'] == specialization_id for spec in available_specializations):
                         errors.append('Invalid specialization selected.')
                 except ValueError:
                     errors.append('Invalid specialization ID format.')
            if not license_number: errors.append('License Number is required.')
            if not license_state: errors.append('License State is required.')
            if not license_expiration: errors.append('License Expiration Date is required.')
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
        else:
            errors.append('Invalid user type selected.')

        if errors:
            for error in errors: flash(error, 'danger')
            return render_template('Register.html',
                                   form_data=request.form,
                                   specializations=available_specializations)

        # --- Variables for outer scope ---
        connection = None
        cursor = None
        saved_file_absolute_paths = []

        # === OUTER TRY BLOCK === (Ensure this indentation level is correct relative to the `if request.method == 'POST':`)
        try: # <--- THIS IS THE TARGET OF LINTER ERROR on Line 101
            connection = get_db_connection() # <--- Line 102
            if not connection or not connection.is_connected(): # <--- Line 103
                raise ConnectionError("Database connection failed.")

            connection.autocommit = False # Set autocommit off for manual transaction control
            cursor = connection.cursor(dictionary=True) # Use dict cursor for checks

            # --- Check Existence ---
            cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s LIMIT 1", (email, username))
            existing_user = cursor.fetchone()
            cursor.execute("SELECT id FROM pending_registrations WHERE email = %s OR username = %s LIMIT 1", (email, username))
            pending_user = cursor.fetchone()

            if existing_user or pending_user:
                flash('Email or Username already exists or is pending approval.', 'warning')
                # Important: Close connection before returning template if obtained
                if cursor: cursor.close()
                if connection and connection.is_connected(): connection.close()
                return render_template('Register.html', form_data=request.form, specializations=available_specializations)

            # Switch to standard cursor before potential INSERT/UPDATE
            cursor.close()
            cursor = connection.cursor()

            needs_approval = user_type == 'doctor'

            if needs_approval:
                # --- Process Doctor Registration ---
                upload_folder_docs_abs = current_app.config.get('UPLOAD_FOLDER_DOCS')
                if not upload_folder_docs_abs or not os.path.isdir(upload_folder_docs_abs):
                    raise ValueError("Server configuration error: Upload directory missing.")

                # Save files BEFORE starting DB transaction
                for db_column_name, file_data in uploaded_files_data.items():
                    file = file_data['file_obj']
                    original_secure = secure_filename(file.filename)
                    base, ext = os.path.splitext(original_secure)
                    unique_filename = f"{uuid.uuid4().hex}_{base[:50]}{ext}"
                    save_path_abs = os.path.join(upload_folder_docs_abs, unique_filename)
                    try: relative_path_for_db = os.path.relpath(save_path_abs, current_app.static_folder).replace("\\", "/")
                    except ValueError: relative_path_for_db = os.path.join('uploads', 'doctor_docs', unique_filename).replace("\\", "/"); current_app.logger.warning(f"Fallback doc path: {relative_path_for_db}")

                    try:
                        os.makedirs(os.path.dirname(save_path_abs), exist_ok=True)
                        file.save(save_path_abs)
                        uploaded_files_data[db_column_name]['saved_relative_path'] = relative_path_for_db
                        saved_file_absolute_paths.append(save_path_abs)
                        current_app.logger.info(f"Saved pending doc: {save_path_abs}")
                    except Exception as save_err:
                        raise IOError(f"Failed to save {db_column_name}: {save_err}") # Re-raise to trigger cleanup

                # Start DB Transaction for Pending Insert
                connection.start_transaction()
                current_app.logger.debug(f"Transaction started for pending registration {username}")

                insert_columns = ["email", "first_name", "last_name", "username", "phone", "country", "user_type_requested", "specialization_id", "license_number", "license_state", "license_expiration", "date_submitted", "status"]
                pending_data_list = [email, first_name, last_name, username, phone, country, 'doctor', specialization_id, license_number, license_state, license_expiration, datetime.now(), 'pending']
                for db_col, file_info in uploaded_files_data.items():
                    if file_info['saved_relative_path']:
                        insert_columns.append(f"`{db_col}`")
                        pending_data_list.append(file_info['saved_relative_path'])
                insert_values_placeholders = ["%s"] * len(insert_columns)
                query_pending = f"""INSERT INTO pending_registrations ({", ".join(f'`{col}`' for col in insert_columns)}) VALUES ({", ".join(insert_values_placeholders)})"""

                cursor.execute(query_pending, tuple(pending_data_list))
                pending_reg_id = cursor.lastrowid
                if not pending_reg_id:
                    raise Exception("Failed to get lastrowid for pending reg.")

                connection.commit() # Commit Doctor transaction
                current_app.logger.info(f"Transaction committed for pending doctor {username}.")
                flash('Registration submitted for approval.', 'info')
                return redirect(url_for('login.login_route')) # Success

            else: # Patient Registration
                # Start DB Transaction for Patient Insert
                connection.start_transaction()
                current_app.logger.debug(f"Transaction started for patient registration {username}")

                # 1. Insert user
                hashed_password = generate_password_hash(password)
                now = datetime.now()
                query_user = """ INSERT INTO users (username, email, password, first_name, last_name, user_type, phone, country, account_status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s) """
                cursor.execute(query_user, (username, email, hashed_password, first_name, last_name, user_type, phone, country, now, now))
                user_id = cursor.lastrowid
                if not user_id:
                    raise Exception("Failed to create user record for patient.")
                current_app.logger.info(f"Created patient user {username} (ID: {user_id})")

                # 2. Get Insurance Provider ID (Switch cursor type temporarily)
                insurance_provider_id = None
                if insurance_provider_name:
                    cursor.close(); cursor = connection.cursor(dictionary=True)
                    cursor.execute("SELECT id FROM insurance_providers WHERE provider_name = %s AND is_active = TRUE", (insurance_provider_name,))
                    provider_result = cursor.fetchone()
                    insurance_provider_id = provider_result['id'] if provider_result else None
                    if not insurance_provider_id: current_app.logger.warning(f"Insurance provider '{insurance_provider_name}' not found/inactive for user {user_id}.")
                    cursor.close(); cursor = connection.cursor() # Switch back

                # 3. Insert patient
                query_patient = """INSERT INTO patients (user_id, date_of_birth, gender, insurance_provider_id, insurance_policy_number, insurance_group_number) VALUES (%s, %s, %s, %s, %s, %s)"""
                cursor.execute(query_patient, (user_id, date_of_birth, gender, insurance_provider_id, insurance_policy_number, insurance_group_number))

                connection.commit() # Commit Patient transaction
                current_app.logger.info(f"Transaction committed for patient {username}.")
                flash('Registration successful! You can now log in.', 'success')
                return redirect(url_for('login.login_route')) # Success

        # === OUTER EXCEPT BLOCK ===
        except (mysql.connector.Error, ConnectionError, ValueError, IOError, Exception) as err:
            error_msg = str(err)
            current_app.logger.error(f"Registration Error for user {username} ({email}): {error_msg}", exc_info=True)

            # Attempt Rollback if connection exists and might be in transaction
            if connection and connection.is_connected():
                try:
                    current_app.logger.warning("Attempting rollback in outer except block due to error...")
                    connection.rollback()
                    current_app.logger.info("Rollback executed in outer except block.")
                except mysql.connector.Error as rb_err:
                    current_app.logger.error(f"Error during rollback in outer except block: {rb_err}")

            # --- File Cleanup ---
            if saved_file_absolute_paths:
                current_app.logger.warning(f"Attempting file cleanup after error for {username}: {len(saved_file_absolute_paths)} file(s).")
                for cleanup_path in saved_file_absolute_paths:
                    try:
                        if os.path.exists(cleanup_path):
                            os.remove(cleanup_path)
                            current_app.logger.info(f"Cleaned up file: {cleanup_path}")
                    except OSError as clean_err:
                        current_app.logger.error(f"Error cleaning up file {cleanup_path}: {clean_err}")

            flash(f'An error occurred during registration: {error_msg}. Please check your input and try again.', 'danger')
            # Return render_template on error to show form with data
            return render_template('Register.html',
                                   form_data=request.form,
                                   specializations=available_specializations)

        # === OUTER FINALLY BLOCK ===
        finally:
            # Ensure cursor and connection are always closed
            if cursor:
                try: cursor.close()
                except Exception as cur_err: current_app.logger.error(f"Error closing cursor in finally: {cur_err}")
            if connection and connection.is_connected():
                 try:
                     connection.close()
                     current_app.logger.debug("Connection closed in finally block.")
                 except Exception as conn_err: current_app.logger.error(f"Error closing connection in finally: {conn_err}")

    # --- GET Request ---
    # This part is outside the `if request.method == 'POST':` block
    return render_template('Register.html',
                           form_data={},
                           specializations=available_specializations)