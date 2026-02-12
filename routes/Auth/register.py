# /auth/register.py
import os
import re
# import uuid # No longer needed for filenames here
from datetime import datetime, date
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   current_app, jsonify)
from werkzeug.security import generate_password_hash
# from werkzeug.utils import secure_filename # No longer needed here directly for file saving
import mysql.connector
from db import get_db_connection

register_bp = Blueprint('register', __name__, template_folder="../templates")

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

# removed allowed_file function as it's no longer used here

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
    specializations_for_selected_dept = [] # Initialize

    if request.method == 'GET' and not all_departments:
        flash('Could not load departments list. Please try again later or contact support.', 'warning')
    
    if request.method == 'POST':
        # Pre-fetch specializations if department_id is in form_data for re-rendering on error
        form_department_id_str = request.form.get('department_id')
        if form_department_id_str:
            try:
                form_department_id_int = int(form_department_id_str)
                specializations_for_selected_dept = get_specializations(department_id=form_department_id_int)
            except ValueError: 
                current_app.logger.warning(f"Invalid department_id in POST data for re-render: {form_department_id_str}")


        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        user_type = request.form.get('user_type')
        phone = request.form.get('phone', '').strip() or None
        country = request.form.get('country', 'United States').strip()
        
        # Patient specific
        date_of_birth = request.form.get('date_of_birth') or None
        gender = request.form.get('gender') or 'unknown' # Default if not provided or empty
        insurance_provider_name = request.form.get('insurance_provider', '').strip() or None
        insurance_policy_number = request.form.get('insurance_policy_number', '').strip() or None
        insurance_group_number = request.form.get('insurance_group_number', '').strip() or None
        
        # Doctor specific (department_id_str already fetched for specializations)
        specialization_id_str = request.form.get('specialization_id')
        license_number = request.form.get('license_number', '').strip() or None
        license_state = request.form.get('license_state', '').strip() or None
        license_expiration = request.form.get('license_expiration') or None
        
        errors = []

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
            if not gender or gender == 'unknown' or gender == "": errors.append('Gender is required for patients.')
        
        elif user_type == 'doctor':
            if not form_department_id_str: errors.append('Department is required for professionals.')
            else: # form_department_id_str is already defined
                try:
                    department_id_int = int(form_department_id_str)
                    if not any(dept['department_id'] == department_id_int for dept in all_departments):
                        errors.append('Invalid department selected.')
                except ValueError: errors.append('Invalid department ID format.')
            
            if not specialization_id_str: errors.append('Specialization is required for professionals.')
            elif department_id_int: # Only validate specialization if department is valid
                # specializations_for_selected_dept already fetched
                try:
                    specialization_id_int = int(specialization_id_str)
                    if not any(spec['specialization_id'] == specialization_id_int and spec['department_id'] == department_id_int for spec in specializations_for_selected_dept):
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
            
            # Document upload logic removed from here
        
        elif not user_type: errors.append('Please select an account type (Patient or Doctor).')
        else: errors.append('Invalid user type selected.') # Should not happen if HTML select is used

        if errors:
            for error in errors: flash(error, 'danger')
            return render_template('Register.html',
                                   form_data=request.form,
                                   departments=all_departments,
                                   specializations_for_selected_dept=specializations_for_selected_dept)

        connection = None; cursor = None
        try:
            connection = get_db_connection()
            if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed.")
            connection.autocommit = False 
            cursor = connection.cursor(dictionary=True) # Use dict cursor for fetching

            # Check existing users
            cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s LIMIT 1", (email, username))
            existing_user = cursor.fetchone()
            # Check pending registrations
            cursor.execute("SELECT id FROM pending_registrations WHERE (email = %s OR username = %s) AND status != 'rejected' LIMIT 1", (email, username))
            pending_user = cursor.fetchone()

            if existing_user or pending_user:
                flash_message = 'An account with this Email or Username already exists.'
                if pending_user: flash_message += ' Your previous registration is pending approval or requires attention.'
                flash(flash_message, 'warning')
                # No need to close cursor/connection here if we are returning, finally block will handle it.
                return render_template('Register.html', form_data=request.form, departments=all_departments, specializations_for_selected_dept=specializations_for_selected_dept)

            # Close dict cursor and get a standard cursor for inserts if needed, or just continue using dict cursor
            # For simplicity, continue using dict cursor if no issues, or switch if preferred for inserts.
            # cursor.close(); cursor = connection.cursor() 

            if user_type == 'doctor':
                hashed_password_for_doctor = generate_password_hash(password) 
                pending_data_columns = [
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
                
                # Document paths are no longer included here
                # dynamic_file_columns and their values are removed

                insert_values_placeholders = ["%s"] * len(pending_data_columns)
                query_pending = f"""INSERT INTO pending_registrations ({", ".join(pending_data_columns)}) VALUES ({", ".join(insert_values_placeholders)})"""
                
                # Switch to standard cursor for insert if preferred or if dict_cursor causes issues
                # if isinstance(cursor, mysql.connector.cursor.MySQLCursorDict):
                #     cursor.close()
                #     cursor = connection.cursor()
                
                cursor.execute(query_pending, tuple(pending_data_values))
                pending_reg_id = cursor.lastrowid
                if not pending_reg_id: raise Exception("Failed to get lastrowid for pending doctor registration.")
                
                connection.commit()
                flash('Doctor registration submitted for approval. You will be notified once reviewed.', 'info')
                return redirect(url_for('login.login_route'))

            elif user_type == 'patient':
                hashed_password_for_patient = generate_password_hash(password)
                now_dt = datetime.now()
                
                # Standard cursor is fine for INSERT
                # if isinstance(cursor, mysql.connector.cursor.MySQLCursorDict):
                #    cursor.close()
                #    cursor = connection.cursor()

                query_user = """INSERT INTO users (username, email, password, first_name, last_name, user_type, phone, country, account_status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)"""
                cursor.execute(query_user, (username, email, hashed_password_for_patient, first_name, last_name, user_type, phone, country, now_dt, now_dt))
                user_id = cursor.lastrowid
                if not user_id:
                    raise Exception("Failed to create user record for patient.")
                current_app.logger.info(f"Patient user record created with ID: {user_id}. Trigger should create patients table entry.")
                
                insurance_provider_id = None
                if insurance_provider_name:
                    # Need dict cursor to fetch provider_id by name easily
                    # This assumes the cursor might not be a dict cursor from the previous checks
                    # A more consistent approach would be to use dict cursor throughout or switch explicitly
                    temp_cursor = connection.cursor(dictionary=True) # Use a temporary dict cursor
                    temp_cursor.execute("SELECT id FROM insurance_providers WHERE provider_name = %s AND is_active = TRUE", (insurance_provider_name,))
                    provider_result = temp_cursor.fetchone()
                    insurance_provider_id = provider_result['id'] if provider_result else None
                    temp_cursor.close()
                    if not insurance_provider_id:
                         current_app.logger.warning(f"Insurance provider '{insurance_provider_name}' not found for user {user_id}")

                update_patient_query = """
                    UPDATE patients
                    SET date_of_birth = %s, gender = %s,
                        insurance_provider_id = %s, insurance_policy_number = %s, insurance_group_number = %s,
                        updated_at = NOW() 
                    WHERE user_id = %s 
                """
                patient_update_params = (
                    date_of_birth, gender, insurance_provider_id, 
                    insurance_policy_number, insurance_group_number, user_id
                )
                cursor.execute(update_patient_query, patient_update_params)

                if cursor.rowcount == 0:
                    current_app.logger.error(f"CRITICAL: Patients record for user_id {user_id} was NOT found or NOT updated. Trigger might have failed or record doesn't exist.")
                    flash("User account created, but there was an issue updating patient-specific details. Please contact support if information is missing.", "warning")
                else:
                    current_app.logger.info(f"Patients record for user_id {user_id} updated successfully.")

                connection.commit()
                flash('Registration successful! You can now log in.', 'success')
                return redirect(url_for('login.login_route'))
            else:
                # This case should ideally not be reached if user_type is validated upfront
                raise ValueError("Invalid user_type encountered during processing.")

        except (mysql.connector.Error, ConnectionError, ValueError, IOError, Exception) as err:
            error_msg_str = str(err)
            current_app.logger.error(f"Registration Error for user {username} ({email}): {error_msg_str}", exc_info=True)
            if connection and connection.is_connected() and not getattr(connection, 'autocommit', True): # Check if in transaction
                try: connection.rollback(); current_app.logger.info("Rollback executed due to error.")
                except mysql.connector.Error as rb_err: current_app.logger.error(f"Error during rollback: {rb_err}")
            
            # File cleanup logic removed as files are no longer handled here
            
            flash(f'An error occurred: {error_msg_str}. Please try again.', 'danger')
            return render_template('Register.html', form_data=request.form, departments=all_departments, specializations_for_selected_dept=specializations_for_selected_dept)
        finally:
            if cursor:
                try: cursor.close()
                except Exception as e_cur: current_app.logger.error(f"Error closing cursor in finally: {e_cur}")
            if connection and connection.is_connected():
                try:
                    if not getattr(connection, 'autocommit', True): connection.autocommit = True # Ensure autocommit is reset
                    connection.close()
                except Exception as e_conn: current_app.logger.error(f"Error closing/resetting connection: {e_conn}")

    # For GET request or if POST had no errors but didn't redirect (should not happen)
    return render_template('Register.html', form_data={}, departments=all_departments, specializations_for_selected_dept=[])