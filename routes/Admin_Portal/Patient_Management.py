# patient_management.py

import os
import datetime # Keep for date formatting
from flask import (Blueprint, render_template, request, session, flash,
                   redirect, url_for, current_app)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from db import get_db_connection
from math import ceil

patient_management = Blueprint('patient_management', __name__)

# --- Constants ---
PER_PAGE_PATIENTS = 15
ALLOWED_PATIENT_SORT_COLUMNS = {
    'first_name', 'last_name', 'email', 'date_of_birth', 'gender',
    'insurance_provider_name', 'created_at'
}

# --- Helper Function (Get Patient Base Info) ---
def get_patient_base_info(patient_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    patient = None
    try:
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone, u.created_at
            FROM users u
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """, (patient_id,))
        patient = cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Error in get_patient_base_info for ID {patient_id}: {e}")
        flash("Database error fetching patient info.", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return patient

# --- Helper to get ENUM values ---
def get_enum_values(cursor, table_name, column_name):
    try:
        cursor.execute("""
            SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
        """, (table_name, column_name))
        result = cursor.fetchone()
        if result and result['COLUMN_TYPE']:
            raw_values = result['COLUMN_TYPE'][5:-1] # Strip 'enum(' and ')'
            values = [val.strip("'") for val in raw_values.split(',')]
            return values
        return []
    except Exception as e:
        current_app.logger.error(f"Error fetching ENUM for {table_name}.{column_name}: {e}")
        return []

# --- Helper to get Current User ID ---
def get_current_user_id():
    return getattr(current_user, 'user_id', getattr(current_user, 'id', None))

# --- Routes ---

@patient_management.route('/admin/patients', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by = request.args.get('sort_by', 'last_name').lower()
    if sort_by not in ALLOWED_PATIENT_SORT_COLUMNS: sort_by = 'last_name'
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    patients = []
    total_items = 0
    total_pages = 0

    try:
        base_query = """
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
            WHERE u.user_type = 'patient'
        """
        params = []
        if search_term:
            base_query += """ AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s
                                OR u.phone LIKE %s OR ip.provider_name LIKE %s) """
            like_term = f"%{search_term}%"
            params.extend([like_term] * 5)

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
                   p.date_of_birth, p.gender, ip.provider_name AS insurance_provider_name
            {base_query} ORDER BY {sort_expression} {sort_order}, u.last_name ASC, u.first_name ASC
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE_PATIENTS, offset]
        cursor.execute(data_query, tuple(final_params)); patients = cursor.fetchall()

    except Exception as e:
        flash(f"Database error fetching patients: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching patients list: {e}")
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
        return redirect(url_for('login.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    insurance_providers, gender_options, blood_types, marital_statuses = [], [], [], []

    try:
        cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
        insurance_providers = cursor.fetchall()
        gender_options = get_enum_values(cursor, 'patients', 'gender')
        blood_types = get_enum_values(cursor, 'patients', 'blood_type')
        marital_statuses = get_enum_values(cursor, 'patients', 'marital_status')
    except Exception as e:
        flash(f"Error loading form data: {str(e)}", "danger")
        current_app.logger.error(f"Error loading patient add form data: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/add_patient.html',
                           insurance_providers=insurance_providers,
                           gender_options=gender_options, # Pass to template
                           blood_types=blood_types,
                           marital_statuses=marital_statuses)

@patient_management.route('/admin/patients/add', methods=['POST'])
@login_required
def add_patient():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    redirect_target = url_for('patient_management.add_patient_form')

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None
    date_of_birth = request.form.get('date_of_birth') or None
    gender = request.form.get('gender') # Will be a string, e.g. "Male" or "" if not selected (but it's required)
    
    blood_type = request.form.get('blood_type')
    if blood_type == '': blood_type = None # Convert empty selection to NULL

    height_cm_str = request.form.get('height_cm')
    weight_kg_str = request.form.get('weight_kg')
    insurance_provider_id = request.form.get('insurance_provider_id') or None
    insurance_policy_number = request.form.get('insurance_policy_number') or None
    insurance_group_number = request.form.get('insurance_group_number') or None
    insurance_expiration = request.form.get('insurance_expiration') or None
    
    marital_status = request.form.get('marital_status')
    if marital_status == '': marital_status = None # Convert empty selection to NULL
    
    occupation = request.form.get('occupation') or None

    if not all([username, email, password, first_name, last_name, date_of_birth, gender]):
        flash("Missing required fields (Username, Email, Password, Name, DOB, Gender).", "danger")
        return redirect(redirect_target)
    
    # Ensure gender is not an empty string if it's required.
    # The `all()` check above handles if gender is None or empty string.
    # The main issue is if the string `gender` is not a valid ENUM.
    # This relies on the form select options matching DB ENUMs.

    height_cm, weight_kg, insurance_provider_id_int = None, None, None
    try:
        if height_cm_str: height_cm = float(height_cm_str)
        if weight_kg_str: weight_kg = float(weight_kg_str)
        if insurance_provider_id and insurance_provider_id != '':
             insurance_provider_id_int = int(insurance_provider_id)
        else: insurance_provider_id_int = None
    except ValueError:
        flash("Invalid number format for height, weight, or insurance ID.", "danger")
        return redirect(redirect_target)

    password_hash = generate_password_hash(password)
    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(redirect_target)

    connection = get_db_connection()
    cursor = connection.cursor()
    new_user_id = None

    try:
        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        if cursor.fetchone():
            flash("Email or Username already exists.", "danger")
            return redirect(redirect_target)

        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name, user_type, phone)
            VALUES (%s, %s, %s, %s, %s, 'patient', %s)
        """, (username, email, password, first_name, last_name, phone))
        new_user_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO patients (user_id, date_of_birth, gender, blood_type, height_cm, weight_kg,
                               insurance_provider_id, insurance_policy_number, insurance_group_number,
                               insurance_expiration, marital_status, occupation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_user_id, date_of_birth, gender, blood_type, height_cm, weight_kg,
              insurance_provider_id_int, insurance_policy_number, insurance_group_number,
              insurance_expiration, marital_status, occupation))

        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'patient_created', 'New patient account created by admin', %s)
        """, (new_user_id, current_admin_id))

        connection.commit()
        flash(f"Patient '{first_name} {last_name}' added successfully", "success")
        redirect_target = url_for('patient_management.view_patient', patient_id=new_user_id)

    except Exception as e:
        current_app.logger.error(f"Error adding patient {username}: {e}") # Log before potential rollback
        if connection.is_connected():
            if connection.in_transaction:
                connection.rollback()
        flash(f"Error adding patient: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)

@patient_management.route('/admin/patients/view/<int:patient_id>', methods=['GET'])
@login_required
def view_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    patient, allergies, diagnoses, upcoming_appointments = None, [], [], []

    try:
        # Fetch patient profile details with insurance provider name
        # Removed appointment_type join from main patient query for simplicity, fetch in appointments query
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
         """, (patient_id,)); upcoming_appointments = cursor.fetchall()

    except Exception as e:
        flash(f"Database error fetching patient details: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching details for patient {patient_id}: {e}")
        return redirect(url_for('patient_management.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/view_patient.html',
                           patient=patient, allergies=allergies, diagnoses=diagnoses,
                           upcoming_appointments=upcoming_appointments)


@patient_management.route('/admin/patients/edit/<int:patient_id>', methods=['GET'])
@login_required
def edit_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    patient, insurance_providers, gender_options, blood_types, marital_statuses = None, [], [], [], []

    try:
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

        patient['dob_formatted'] = patient.get('date_of_birth').strftime('%Y-%m-%d') if patient.get('date_of_birth') else ''
        patient['insurance_exp_formatted'] = patient.get('insurance_expiration').strftime('%Y-%m-%d') if patient.get('insurance_expiration') else ''

    except Exception as e:
        flash(f"Database error loading edit form: {str(e)}", "danger")
        current_app.logger.error(f"Error loading edit form for patient {patient_id}: {e}")
        return redirect(url_for('patient_management.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Patients/edit_patient.html',
                           patient=patient, insurance_providers=insurance_providers,
                           gender_options=gender_options, # Pass to template
                           blood_types=blood_types,
                           marital_statuses=marital_statuses)

@patient_management.route('/admin/patients/edit/<int:patient_id>', methods=['POST'])
@login_required
def edit_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    redirect_target = url_for('patient_management.edit_patient_form', patient_id=patient_id)

    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone') or None
    date_of_birth = request.form.get('date_of_birth') or None
    gender = request.form.get('gender') # Value from form
    
    blood_type = request.form.get('blood_type')
    if blood_type == '': blood_type = None # Convert empty selection to NULL
    
    height_cm_str = request.form.get('height_cm')
    weight_kg_str = request.form.get('weight_kg')
    insurance_provider_id = request.form.get('insurance_provider_id') or None
    insurance_policy_number = request.form.get('insurance_policy_number') or None
    insurance_group_number = request.form.get('insurance_group_number') or None
    insurance_expiration = request.form.get('insurance_expiration') or None
    
    marital_status = request.form.get('marital_status')
    if marital_status == '': marital_status = None # Convert empty selection to NULL
    
    occupation = request.form.get('occupation') or None
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    # Ensure required fields are present and gender is not empty
    if not all([first_name, last_name, email, date_of_birth, gender]):
        flash("Missing required fields (First Name, Last Name, Email, DOB, Gender).", "danger")
        return redirect(redirect_target)

    height_cm, weight_kg, insurance_provider_id_int = None, None, None
    try:
        if height_cm_str: height_cm = float(height_cm_str)
        if weight_kg_str: weight_kg = float(weight_kg_str)
        if insurance_provider_id and insurance_provider_id != '':
             insurance_provider_id_int = int(insurance_provider_id)
        else: insurance_provider_id_int = None
    except ValueError:
        flash("Invalid number format for height, weight, or insurance ID.", "danger")
        return redirect(redirect_target)

    update_password = False; new_password_hash = None
    if new_password or confirm_password:
        if not new_password :
            flash("New Password is required if Confirm Password is provided.", "warning"); return redirect(redirect_target)
        if not confirm_password :
            flash("Confirm Password is required if New Password is provided.", "warning"); return redirect(redirect_target)
        if new_password != confirm_password:
            flash("New passwords do not match.", "danger"); return redirect(redirect_target)
        if len(new_password) < 8 :
            flash("New password must be at least 8 characters long.", "danger"); return redirect(redirect_target)
        new_password_hash = generate_password_hash(new_password); update_password = True

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(redirect_target)

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, patient_id))
        if cursor.fetchone():
            flash("Email address already in use by another user.", "danger")
            return redirect(redirect_target)

        user_update_query = "UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s"
        user_params = [first_name, last_name, email, phone]
        if update_password:
            user_update_query += ", password = %s"; user_params.append(new_password_hash)
        user_update_query += " WHERE user_id = %s"; user_params.append(patient_id)
        cursor.execute(user_update_query, tuple(user_params))

        cursor.execute("""
            UPDATE patients SET date_of_birth=%s, gender=%s, blood_type=%s, height_cm=%s, weight_kg=%s,
                insurance_provider_id=%s, insurance_policy_number=%s, insurance_group_number=%s,
                insurance_expiration=%s, marital_status=%s, occupation=%s
            WHERE user_id = %s
        """, (date_of_birth, gender, blood_type, height_cm, weight_kg, insurance_provider_id_int,
             insurance_policy_number, insurance_group_number, insurance_expiration,
             marital_status, occupation, patient_id))

        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'patient_updated', 'Patient profile updated by admin', %s)
        """, (patient_id, current_admin_id))

        connection.commit()
        flash_msg = "Patient updated successfully"
        if update_password: flash_msg += " (Password Changed)"
        flash(flash_msg, "success")
        redirect_target = url_for('patient_management.view_patient', patient_id=patient_id)

    except Exception as e:
        current_app.logger.error(f"Error editing patient {patient_id}: {e}") # Log before potential rollback
        if connection.is_connected():
            if connection.in_transaction:
                connection.rollback()
        flash(f"Error updating patient: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)


@patient_management.route('/admin/patients/delete/<int:patient_id>', methods=['GET'])
@login_required
def delete_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    patient = get_patient_base_info(patient_id)
    if not patient:
        flash("Patient not found", "danger"); return redirect(url_for('patient_management.index'))
    return render_template('Admin_Portal/Patients/delete_confirmation.html', patient=patient)


@patient_management.route('/admin/patients/delete/<int:patient_id>', methods=['POST'])
@login_required
def delete_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(url_for('patient_management.index'))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Assuming ON DELETE CASCADE is correctly set for foreign keys in 'patients' table
        # and other related tables that point to 'users.user_id'.
        # If not, you would need to delete from child tables first.
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_id,))
        deleted_rows = cursor.rowcount

        if deleted_rows > 0:
            cursor.execute("""
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
                VALUES (%s, 'patient_deleted', 'Admin deleted patient account and associated data', %s)
            """, (patient_id, current_admin_id))
            connection.commit()
            flash("Patient and associated records deleted successfully.", "success")
        else:
            if connection.in_transaction: # Should not be necessary if no DML before this check
                connection.rollback()
            flash("Patient not found or already deleted.", "warning")

    except Exception as e:
        current_app.logger.error(f"Error deleting patient {patient_id}: {e}") # Log before potential rollback
        if connection.is_connected():
            if connection.in_transaction:
                connection.rollback()
        flash(f"Error deleting patient: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('patient_management.index'))