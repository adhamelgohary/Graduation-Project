# patient_management.py

import os
import datetime # Keep for date formatting
from flask import (Blueprint, render_template, request, session, flash,
                   redirect, url_for, current_app)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from db import get_db_connection
from math import ceil
import mysql.connector # Import the base connector
from mysql.connector import Error as MySQLError # Import the specific Error class

patient_management = Blueprint('patient_management', __name__)

# --- Constants ---
PER_PAGE_PATIENTS = 15
ALLOWED_PATIENT_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'date_of_birth', 'gender',
    'insurance_provider_name', 'created_at'
}

# --- Helper Function (Get Patient Base Info) ---
def get_patient_base_info(patient_id):
    connection = None; cursor = None; patient = None # Initialize connection and cursor
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): # Check connection
            current_app.logger.error("get_patient_base_info: Database connection failed.")
            flash("Database connection error.", "danger")
            return None
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone, u.created_at
            FROM users u
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """, (patient_id,))
        patient = cursor.fetchone()
    except MySQLError as db_err: # Catch specific MySQL errors
        current_app.logger.error(f"MySQL error in get_patient_base_info for ID {patient_id}: {db_err}")
        flash("Database error fetching patient info.", "danger")
    except Exception as e:
        current_app.logger.error(f"Generic error in get_patient_base_info for ID {patient_id}: {e}")
        flash("An error occurred fetching patient info.", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return patient

# --- Helper to get ENUM values ---
# patient_management.py

# ... (other imports and code) ...

# --- Helper to get ENUM values ---
def get_enum_values(cursor, table_name, column_name):
    # This function now expects an active cursor to be passed in
    try:
        db_name_query = "SELECT DATABASE()" # Keep this for clarity if you want
        cursor.execute(db_name_query)
        db_name_result = cursor.fetchone()

        # --- CORRECTED KEY ACCESS ---
        # The key in the dictionary result for "SELECT DATABASE()" is "DATABASE()"
        current_db_name = None
        if db_name_result and 'DATABASE()' in db_name_result:
            current_db_name = db_name_result['DATABASE()']
        
        if not current_db_name:
             current_app.logger.error("Could not determine current database name for ENUM fetch. 'SELECT DATABASE()' returned None or no 'DATABASE()' key.")
             return []
        # --- END CORRECTION ---

        cursor.execute("""
            SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s 
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
        """, (current_db_name, table_name, column_name))
        result = cursor.fetchone() # This will also be a dictionary

        if result and result.get('COLUMN_TYPE'): # Use .get() for safer dictionary access
            type_str = result['COLUMN_TYPE']
            if type_str.lower().startswith("enum("):
                raw_values = type_str[5:-1] # Strip 'enum(' and ')'
                values = [val.strip("'") for val in raw_values.split(',')]
                return values
        current_app.logger.warning(f"ENUM values not found or not an ENUM type for {table_name}.{column_name} in DB {current_db_name}.")
        return []
    except MySQLError as db_err: # Use MySQLError if defined
        current_app.logger.error(f"MySQL error fetching ENUM for {table_name}.{column_name}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"Generic error fetching ENUM for {table_name}.{column_name}: {e}")
    return []

# ... (rest of Patient_Management.py) ...
# --- Helper to get Current User ID ---
def get_current_user_id():
    # Ensure current_user.id (or user_id) is an integer
    user_id_val = getattr(current_user, 'id', getattr(current_user, 'user_id', None))
    if user_id_val is not None:
        try:
            return int(user_id_val)
        except ValueError:
            current_app.logger.error(f"Could not convert current_user.id '{user_id_val}' to int.")
    return None


# --- Routes ---

@patient_management.route('/admin/patients', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route')) # Use your actual login route

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by = request.args.get('sort_by', 'last_name').lower()
    if sort_by not in ALLOWED_PATIENT_SORT_COLUMNS: sort_by = 'last_name'
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

    connection = None; cursor = None; patients = [] # Initialize connection, cursor, patients
    total_items = 0; total_pages = 0

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error("Index: Database connection failed.")
            flash("Database connection error.", "danger")
            return render_template('Admin_Portal/Patients/manage_patients.html', patients=[], page=1, total_pages=0, total_items=0, search_term=search_term, sort_by=sort_by, sort_order=sort_order)

        cursor = connection.cursor(dictionary=True)
        
        base_query = """
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
            WHERE u.user_type = 'patient'
        """
        params = []
        if search_term:
            base_query += """ AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s
                                OR u.phone LIKE %s OR ip.provider_name LIKE %s OR u.user_id LIKE %s) """ # Added user_id search
            like_term = f"%{search_term}%"
            params.extend([like_term] * 6) # Adjusted for 6 search fields

        count_query = f"SELECT COUNT(u.user_id) as total {base_query}"
        cursor.execute(count_query, tuple(params))
        result = cursor.fetchone(); total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_PATIENTS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_PATIENTS

        sort_column_mapping = {
            'first_name': 'u.first_name', 'last_name': 'u.last_name', 'email': 'u.email',
            'date_of_birth': 'p.date_of_birth', 'gender': 'p.gender',
            'insurance_provider_name': 'ip.provider_name', 'created_at': 'u.created_at'
        }
        sort_expression = sort_column_mapping.get(sort_by, 'u.last_name')

        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.created_at,
                   p.date_of_birth, p.gender, ip.provider_name AS insurance_provider_name,
                   u.account_status
            {base_query} ORDER BY {sort_expression} {sort_order}, u.last_name ASC, u.first_name ASC
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE_PATIENTS, offset]
        cursor.execute(data_query, tuple(final_params)); patients = cursor.fetchall()

    except MySQLError as db_err: # Catch specific MySQL errors
        flash(f"Database error fetching patients: {db_err.msg}", "danger")
        current_app.logger.error(f"MySQL error fetching patients list: {db_err}")
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Generic error fetching patients list: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Patients/manage_patients.html', patients=patients, page=page,
        total_pages=total_pages, per_page=PER_PAGE_PATIENTS, total_items=total_items,
        search_term=search_term, sort_by=sort_by, sort_order=sort_order
    )

@patient_management.route('/admin/patients/add', methods=['GET'])
@login_required
def add_patient_form():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))

    connection = None; cursor = None # Initialize
    insurance_providers, gender_options, blood_types, marital_statuses = [], [], [], []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error("add_patient_form: Database connection failed.")
            flash("Database connection error.", "danger")
            # Render with empty lists if DB fails early
            return render_template('Admin_Portal/Patients/add_patient.html', insurance_providers=[], gender_options=[], blood_types=[], marital_statuses=[])

        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
        insurance_providers = cursor.fetchall()
        gender_options = get_enum_values(cursor, 'patients', 'gender') # Pass active cursor
        blood_types = get_enum_values(cursor, 'patients', 'blood_type') # Pass active cursor
        marital_statuses = get_enum_values(cursor, 'patients', 'marital_status') # Pass active cursor
    except MySQLError as db_err:
        flash(f"Database error loading form data: {db_err.msg}", "danger")
        current_app.logger.error(f"MySQL error loading patient add form data: {db_err}")
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Generic error loading patient add form data: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/add_patient.html',
                           insurance_providers=insurance_providers,
                           gender_options=gender_options,
                           blood_types=blood_types,
                           marital_statuses=marital_statuses,
                           form_data=request.form if request.method == 'POST' else {} ) # Pass form_data for re-population

@patient_management.route('/admin/patients/add', methods=['POST'])
@login_required
def add_patient():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))
    
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password') 
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None
    date_of_birth = request.form.get('date_of_birth') or None
    gender = request.form.get('gender') 
    
    blood_type = request.form.get('blood_type')
    if not blood_type or blood_type == '': blood_type = None 

    height_cm_str = request.form.get('height_cm')
    weight_kg_str = request.form.get('weight_kg')
    insurance_provider_id_str = request.form.get('insurance_provider_id')
    insurance_policy_number = request.form.get('insurance_policy_number') or None
    insurance_group_number = request.form.get('insurance_group_number') or None
    insurance_expiration = request.form.get('insurance_expiration') or None
    
    marital_status = request.form.get('marital_status')
    if not marital_status or marital_status == '': marital_status = None
    
    occupation = request.form.get('occupation') or None

    errors = []
    if not all([username, email, password, first_name, last_name, date_of_birth, gender]):
        errors.append("Missing required fields (Username, Email, Password, Name, DOB, Gender).")
    if not gender: 
        errors.append("Gender is required.")
    if password and len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    # Add email format validation if not done elsewhere
    # from werkzeug.routing import EmailConverter # if using this for validation
    # if not EmailConverter(email).is_valid(): errors.append("Invalid email format.")


    height_cm, weight_kg, insurance_provider_id_int = None, None, None
    try:
        if height_cm_str: height_cm = float(height_cm_str)
        if weight_kg_str: weight_kg = float(weight_kg_str)
        if insurance_provider_id_str and insurance_provider_id_str != '':
             insurance_provider_id_int = int(insurance_provider_id_str)
    except ValueError:
        errors.append("Invalid number format for height, weight, or insurance ID.")

    if errors:
        for error in errors:
            flash(error, "danger")
        # Re-render form with errors and existing data
        # Need to fetch these again as they are not passed between POST and GET
        connection_form = None; cursor_form = None;
        insurance_providers_form, gender_options_form, blood_types_form, marital_statuses_form = [], [], [], []
        try:
            connection_form = get_db_connection()
            if connection_form and connection_form.is_connected():
                cursor_form = connection_form.cursor(dictionary=True)
                cursor_form.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
                insurance_providers_form = cursor_form.fetchall()
                gender_options_form = get_enum_values(cursor_form, 'patients', 'gender')
                blood_types_form = get_enum_values(cursor_form, 'patients', 'blood_type')
                marital_statuses_form = get_enum_values(cursor_form, 'patients', 'marital_status')
        except Exception as e_form: current_app.logger.error(f"Error reloading form data for add_patient error: {e_form}")
        finally:
            if cursor_form: cursor_form.close()
            if connection_form and connection_form.is_connected(): connection_form.close()

        return render_template('Admin_Portal/Patients/add_patient.html',
                               form_data=request.form,
                               insurance_providers=insurance_providers_form,
                               gender_options=gender_options_form,
                               blood_types=blood_types_form,
                               marital_statuses=marital_statuses_form)


    password_hash = generate_password_hash(password)
    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('patient_management.add_patient_form'))

    connection = None; cursor = None; new_user_id = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise MySQLError("Database connection failed.") # Raise specific error
            
        connection.autocommit = False 
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        if cursor.fetchone():
            flash("Email or Username already exists.", "danger")
            if connection.in_transaction: connection.rollback()
            return redirect(url_for('patient_management.add_patient_form'))

        current_time = datetime.datetime.now()
        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name, user_type, phone, account_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'patient', %s, 'active', %s, %s)
        """, (username, email, password_hash, first_name, last_name, phone, current_time, current_time))
        new_user_id = cursor.lastrowid
        
        if not new_user_id:
            raise Exception("Failed to create user record (user_id not returned).")
        current_app.logger.info(f"Admin created new user ID: {new_user_id} for patient {username}.")

        # Assuming a trigger creates a basic row in 'patients', we UPDATE it.
        # If no trigger, this should be an INSERT.
        update_patient_query = """
            UPDATE patients
            SET date_of_birth = %s, gender = %s, blood_type = %s, height_cm = %s, weight_kg = %s,
                insurance_provider_id = %s, insurance_policy_number = %s, insurance_group_number = %s,
                insurance_expiration = %s, marital_status = %s, occupation = %s,
                updated_at = %s 
            WHERE user_id = %s
        """
        patient_update_params = (
            date_of_birth, gender, blood_type, height_cm, weight_kg,
            insurance_provider_id_int, insurance_policy_number, insurance_group_number,
            insurance_expiration, marital_status, occupation,
            current_time, # updated_at for patients table
            new_user_id
        )
        cursor.execute(update_patient_query, patient_update_params)

        if cursor.rowcount == 0:
            current_app.logger.warning(f"Patient record for user_id {new_user_id} was NOT updated by admin add. Trigger might not exist or failed. Attempting INSERT.")
            # Fallback: If trigger didn't create the row, or if you don't have a trigger.
            # Make sure to include all necessary fields for an INSERT.
            # This assumes 'created_at' for patients table is also set by default or explicitly.
            insert_patient_query = """
                INSERT INTO patients (user_id, date_of_birth, gender, blood_type, height_cm, weight_kg,
                                   insurance_provider_id, insurance_policy_number, insurance_group_number,
                                   insurance_expiration, marital_status, occupation, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            patient_insert_params = (
                new_user_id, date_of_birth, gender, blood_type, height_cm, weight_kg,
                insurance_provider_id_int, insurance_policy_number, insurance_group_number,
                insurance_expiration, marital_status, occupation,
                current_time, # created_at
                current_time  # updated_at
            )
            cursor.execute(insert_patient_query, patient_insert_params)
            if cursor.rowcount == 0: # If fallback INSERT also fails
                 raise Exception(f"Failed to create or update patient record for user_id {new_user_id} after user creation.")


        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, 'patient_created', 'New patient account created by admin', %s, 'users', %s)
        """, (new_user_id, current_admin_id, new_user_id))

        connection.commit()
        flash(f"Patient '{first_name} {last_name}' added successfully with User ID: {new_user_id}", "success")
        return redirect(url_for('patient_management.view_patient', patient_id=new_user_id))

    except MySQLError as db_err:
        current_app.logger.error(f"MySQL Database error adding patient {username}: {db_err}")
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
            current_app.logger.info("Transaction rolled back due to MySQL error.")
        flash(f"Database error adding patient: {db_err.msg}", "danger")
    except Exception as e:
        current_app.logger.error(f"General error adding patient {username}: {e}", exc_info=True)
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
            current_app.logger.info("Transaction rolled back due to general error.")
        flash(f"An unexpected error occurred: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.autocommit = True 
            connection.close()
    
    # If an error occurred, redirect back to the add form
    # Need to re-fetch form dropdown data again
    connection_form_err = None; cursor_form_err = None;
    insurance_providers_form_err, gender_options_form_err, blood_types_form_err, marital_statuses_form_err = [], [], [], []
    try:
        connection_form_err = get_db_connection()
        if connection_form_err and connection_form_err.is_connected():
            cursor_form_err = connection_form_err.cursor(dictionary=True)
            cursor_form_err.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
            insurance_providers_form_err = cursor_form_err.fetchall()
            gender_options_form_err = get_enum_values(cursor_form_err, 'patients', 'gender')
            blood_types_form_err = get_enum_values(cursor_form_err, 'patients', 'blood_type')
            marital_statuses_form_err = get_enum_values(cursor_form_err, 'patients', 'marital_status')
    except Exception as e_form_err: current_app.logger.error(f"Error reloading form data for add_patient final redirect: {e_form_err}")
    finally:
        if cursor_form_err: cursor_form_err.close()
        if connection_form_err and connection_form_err.is_connected(): connection_form_err.close()
    return render_template('Admin_Portal/Patients/add_patient.html',
                            form_data=request.form,
                            insurance_providers=insurance_providers_form_err,
                            gender_options=gender_options_form_err,
                            blood_types=blood_types_form_err,
                            marital_statuses=marital_statuses_form_err)


@patient_management.route('/admin/patients/view/<int:patient_id>', methods=['GET'])
@login_required
def view_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route')) 

    connection = None; cursor = None # Initialize
    patient, allergies, diagnoses, processed_upcoming_appointments = None, [], [], []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"View Patient {patient_id}: Database connection failed.")
            flash("Database connection error.", "danger")
            return redirect(url_for('patient_management.index'))
            
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.*, p.*, ip.provider_name AS insurance_provider_name
            FROM users u JOIN patients p ON u.user_id = p.user_id
            LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """, (patient_id,))
        patient = cursor.fetchone()

        if not patient:
            flash("Patient not found", "danger")
            return redirect(url_for('patient_management.index'))

        cursor.execute("""
             SELECT a.allergy_name, a.allergy_type, pa.severity, pa.reaction_description, pa.diagnosed_date, pa.notes
             FROM patient_allergies pa JOIN allergies a ON pa.allergy_id = a.allergy_id
             WHERE pa.patient_id = %s ORDER BY a.allergy_name
         """, (patient_id,)); allergies = cursor.fetchall()

        cursor.execute("""
             SELECT d.*, CONCAT(doc_user.first_name, ' ', doc_user.last_name) as doctor_name
             FROM diagnoses d LEFT JOIN users doc_user ON d.doctor_id = doc_user.user_id
             WHERE d.patient_id = %s ORDER BY d.diagnosis_date DESC
         """, (patient_id,)); diagnoses = cursor.fetchall()

        cursor.execute("""
             SELECT app.*, CONCAT(doc_user.first_name, ' ', doc_user.last_name) as doctor_name,
                    appt.type_name as appointment_type_name 
             FROM appointments app 
             JOIN users doc_user ON app.doctor_id = doc_user.user_id
             LEFT JOIN appointment_types appt ON app.appointment_type_id = appt.type_id
             WHERE app.patient_id = %s AND app.appointment_date >= CURDATE()
             ORDER BY app.appointment_date ASC, app.start_time ASC
         """, (patient_id,))
        raw_upcoming_appointments = cursor.fetchall()

        for raw_appt_data in raw_upcoming_appointments:
            appt_item = dict(raw_appt_data) 
            if 'start_time' in appt_item and isinstance(appt_item['start_time'], datetime.timedelta):
                appt_item['start_time'] = (datetime.datetime.min + appt_item['start_time']).time()
            if 'end_time' in appt_item and isinstance(appt_item['end_time'], datetime.timedelta):
                appt_item['end_time'] = (datetime.datetime.min + appt_item['end_time']).time()
            processed_upcoming_appointments.append(appt_item)

    except MySQLError as db_err:
        flash(f"Database error fetching patient details: {db_err.msg}", "danger")
        current_app.logger.error(f"MySQL error fetching details for patient {patient_id}: {db_err}", exc_info=True)
        return redirect(url_for('patient_management.index'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Generic error fetching details for patient {patient_id}: {e}", exc_info=True)
        return redirect(url_for('patient_management.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/view_patient.html',
                           patient=patient, allergies=allergies, diagnoses=diagnoses,
                           upcoming_appointments=processed_upcoming_appointments)

@patient_management.route('/admin/patients/edit/<int:patient_id>', methods=['GET'])
@login_required
def edit_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))

    connection = None; cursor = None # Initialize
    patient, insurance_providers, gender_options, blood_types, marital_statuses = None, [], [], [], []

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"Edit Patient Form {patient_id}: Database connection failed.")
            flash("Database connection error.", "danger")
            return redirect(url_for('patient_management.index'))
            
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.*, p.* FROM users u JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """, (patient_id,))
        patient = cursor.fetchone()

        if not patient:
            flash("Patient not found", "danger")
            return redirect(url_for('patient_management.index'))

        cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
        insurance_providers = cursor.fetchall()
        gender_options = get_enum_values(cursor, 'patients', 'gender')
        blood_types = get_enum_values(cursor, 'patients', 'blood_type')
        marital_statuses = get_enum_values(cursor, 'patients', 'marital_status')

        # Formatting for date inputs in the form
        if patient.get('date_of_birth') and isinstance(patient.get('date_of_birth'), datetime.date):
            patient['dob_formatted'] = patient['date_of_birth'].strftime('%Y-%m-%d')
        else: patient['dob_formatted'] = ''
        
        if patient.get('insurance_expiration') and isinstance(patient.get('insurance_expiration'), datetime.date):
            patient['insurance_exp_formatted'] = patient['insurance_expiration'].strftime('%Y-%m-%d')
        else: patient['insurance_exp_formatted'] = ''


    except MySQLError as db_err:
        flash(f"Database error loading edit form: {db_err.msg}", "danger")
        current_app.logger.error(f"MySQL error loading edit form for patient {patient_id}: {db_err}")
        return redirect(url_for('patient_management.index'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Generic error loading edit form for patient {patient_id}: {e}")
        return redirect(url_for('patient_management.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/edit_patient.html',
                           patient=patient, insurance_providers=insurance_providers,
                           gender_options=gender_options, 
                           blood_types=blood_types,
                           marital_statuses=marital_statuses)

@patient_management.route('/admin/patients/edit/<int:patient_id>', methods=['POST'])
@login_required
def edit_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))

    # It's good practice to re-fetch form data for re-rendering on error
    # However, for POST, we process and then redirect. Flashing errors is key.

    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone') or None
    date_of_birth = request.form.get('date_of_birth') or None
    gender = request.form.get('gender')
    
    blood_type = request.form.get('blood_type')
    if not blood_type or blood_type == '': blood_type = None
    
    height_cm_str = request.form.get('height_cm')
    weight_kg_str = request.form.get('weight_kg')
    insurance_provider_id_str = request.form.get('insurance_provider_id')
    insurance_policy_number = request.form.get('insurance_policy_number') or None
    insurance_group_number = request.form.get('insurance_group_number') or None
    insurance_expiration = request.form.get('insurance_expiration') or None
    
    marital_status = request.form.get('marital_status')
    if not marital_status or marital_status == '': marital_status = None
    
    occupation = request.form.get('occupation') or None
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    errors = []
    if not all([first_name, last_name, email, date_of_birth, gender]):
        errors.append("Missing required fields (First Name, Last Name, Email, DOB, Gender).")
    if not gender:
        errors.append("Gender is required.")
    
    height_cm, weight_kg, insurance_provider_id_int = None, None, None
    try:
        if height_cm_str: height_cm = float(height_cm_str)
        if weight_kg_str: weight_kg = float(weight_kg_str)
        if insurance_provider_id_str and insurance_provider_id_str != '':
             insurance_provider_id_int = int(insurance_provider_id_str)
    except ValueError:
        errors.append("Invalid number format for height, weight, or insurance ID.")

    update_password = False; new_password_hash = None
    if new_password or confirm_password: # Only process if either is filled
        if not new_password :
            errors.append("New Password is required if Confirm Password is provided.")
        if not confirm_password :
            errors.append("Confirm Password is required if New Password is provided.")
        if new_password and confirm_password and new_password != confirm_password:
            errors.append("New passwords do not match.")
        if new_password and len(new_password) < 8 :
            errors.append("New password must be at least 8 characters long.")
        if not errors and new_password: # Only hash if no preceding password errors
            new_password_hash = generate_password_hash(new_password); update_password = True
    
    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for('patient_management.edit_patient_form', patient_id=patient_id))


    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('patient_management.edit_patient_form', patient_id=patient_id))

    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise MySQLError("Database connection failed.")
            
        connection.autocommit = False
        cursor = connection.cursor()

        # Check if new email conflicts with another user
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, patient_id))
        if cursor.fetchone():
            flash("Email address already in use by another user.", "danger")
            if connection.in_transaction: connection.rollback()
            return redirect(url_for('patient_management.edit_patient_form', patient_id=patient_id))

        current_time_for_update = datetime.datetime.now()
        user_update_query = "UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s, updated_at = %s"
        user_params = [first_name, last_name, email, phone, current_time_for_update]
        if update_password:
            user_update_query += ", password = %s"; user_params.append(new_password_hash)
        user_update_query += " WHERE user_id = %s"; user_params.append(patient_id)
        cursor.execute(user_update_query, tuple(user_params))

        cursor.execute("""
            UPDATE patients SET date_of_birth=%s, gender=%s, blood_type=%s, height_cm=%s, weight_kg=%s,
                insurance_provider_id=%s, insurance_policy_number=%s, insurance_group_number=%s,
                insurance_expiration=%s, marital_status=%s, occupation=%s, updated_at=%s
            WHERE user_id = %s
        """, (date_of_birth, gender, blood_type, height_cm, weight_kg, insurance_provider_id_int,
             insurance_policy_number, insurance_group_number, insurance_expiration,
             marital_status, occupation, current_time_for_update, patient_id))
        
        if cursor.rowcount == 0:
            current_app.logger.warning(f"No rows updated in patients table for user_id {patient_id}. Record might not exist or data was identical.")
            # This isn't necessarily a critical error if users table updated, but worth noting.

        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, 'patient_updated', 'Patient profile updated by admin', %s, 'users', %s)
        """, (patient_id, current_admin_id, patient_id))

        connection.commit()
        flash_msg = "Patient updated successfully"
        if update_password: flash_msg += " (Password Changed)"
        flash(flash_msg, "success")
        return redirect(url_for('patient_management.view_patient', patient_id=patient_id))

    except MySQLError as db_err:
        current_app.logger.error(f"MySQL error editing patient {patient_id}: {db_err}")
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
        flash(f"Database error updating patient: {db_err.msg}", "danger")
    except Exception as e:
        current_app.logger.error(f"General error editing patient {patient_id}: {e}", exc_info=True)
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.autocommit = True
            connection.close()
    # If error, redirect back to edit form
    return redirect(url_for('patient_management.edit_patient_form', patient_id=patient_id))


@patient_management.route('/admin/patients/delete/<int:patient_id>', methods=['GET'])
@login_required
def delete_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route')) # Use your actual login route
    patient = get_patient_base_info(patient_id)
    if not patient:
        flash("Patient not found", "danger"); return redirect(url_for('patient_management.index'))
    return render_template('Admin_Portal/Patients/delete_confirmation.html', patient=patient)


@patient_management.route('/admin/patients/delete/<int:patient_id>', methods=['POST'])
@login_required
def delete_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('patient_management.index'))

    connection = None; cursor = None # Initialize
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise MySQLError("Database connection failed.")
            
        connection.autocommit = False
        cursor = connection.cursor()

        # Fetch patient info for logging before deletion
        patient_info_for_log = get_patient_base_info(patient_id) # Uses a separate connection

        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_id,))
        deleted_rows = cursor.rowcount

        if deleted_rows > 0:
            action_details = f"Admin deleted patient account '{patient_info_for_log.get('username', 'N/A') if patient_info_for_log else 'Unknown'}' (ID: {patient_id}) and associated data."
            cursor.execute("""
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                VALUES (%s, 'patient_deleted', %s, %s, 'users', %s)
            """, (patient_id, action_details, current_admin_id, patient_id))
            connection.commit()
            flash("Patient and associated records deleted successfully.", "success")
        else:
            if connection.in_transaction: connection.rollback()
            flash("Patient not found or already deleted.", "warning")

    except MySQLError as db_err:
        current_app.logger.error(f"MySQL error deleting patient {patient_id}: {db_err}")
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
        flash(f"Database error deleting patient: {db_err.msg}", "danger")
    except Exception as e:
        current_app.logger.error(f"General error deleting patient {patient_id}: {e}", exc_info=True)
        if connection and connection.is_connected() and connection.in_transaction:
            connection.rollback()
        flash(f"An error occurred deleting patient: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            connection.autocommit = True
            connection.close()

    return redirect(url_for('patient_management.index'))