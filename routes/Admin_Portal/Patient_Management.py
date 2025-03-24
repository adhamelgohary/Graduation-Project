from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection

admin_patients = Blueprint('admin_patients', __name__)

@admin_patients.route('/admin/patients', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get search query if present
    search_query = request.args.get('search', '')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    if search_query:
        # If search query exists, filter results
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                   p.date_of_birth, p.gender, p.blood_type, p.insurance_provider
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_type = 'patient'
            AND (
                u.first_name LIKE %s OR 
                u.last_name LIKE %s OR 
                u.email LIKE %s
            )
            ORDER BY u.last_name, u.first_name
        """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        # Otherwise get all patients
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                   p.date_of_birth, p.gender, p.blood_type, p.insurance_provider
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_type = 'patient'
            ORDER BY u.last_name, u.first_name
        """)
    
    patients = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/Patients/manage_patients.html', patients=patients, search_query=search_query)
# Add patient form route
@admin_patients.route('/admin/patients/add', methods=['GET'])
@login_required
def add_patient_form():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get insurance providers for dropdown
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
    insurance_providers = cursor.fetchall()
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/Patients/add_patient.html', insurance_providers=insurance_providers)

# Process add patient form
@admin_patients.route('/admin/patients/add', methods=['POST'])
@login_required
def add_patient():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Extract form data
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    date_of_birth = request.form.get('date_of_birth')
    gender = request.form.get('gender')
    blood_type = request.form.get('blood_type')
    height_cm = request.form.get('height_cm')
    weight_kg = request.form.get('weight_kg')
    insurance_provider = request.form.get('insurance_provider')
    insurance_policy_number = request.form.get('insurance_policy_number')
    insurance_group_number = request.form.get('insurance_group_number')
    insurance_expiration = request.form.get('insurance_expiration')
    marital_status = request.form.get('marital_status')
    occupation = request.form.get('occupation')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # First, insert into users table
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name, 
                              user_type, phone)
            VALUES (%s, %s, %s, %s, %s, 'patient', %s)
        """, (username, email, password_hash, first_name, last_name, phone))
        
        # Get the auto-generated user_id
        user_id = cursor.lastrowid
        
        # Then, insert into patients table
        cursor.execute("""
            INSERT INTO patients (user_id, date_of_birth, gender, blood_type, 
                               height_cm, weight_kg, insurance_provider, 
                               insurance_policy_number, insurance_group_number, 
                               insurance_expiration, marital_status, occupation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, date_of_birth, gender, blood_type, 
              height_cm, weight_kg, insurance_provider, 
              insurance_policy_number, insurance_group_number, 
              insurance_expiration, marital_status, occupation))
        
        # Commit changes
        connection.commit()
        flash("Patient added successfully", "success")
        
    except Exception as e:
        flash(f"Error adding patient: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))

# Patient details view route
@admin_patients.route('/admin/patients/view/<int:patient_id>', methods=['GET'])
@login_required
def view_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get patient profile details
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, u.account_status,
               p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
               p.insurance_provider, p.insurance_policy_number, p.insurance_group_number,
               p.insurance_expiration, p.marital_status, p.occupation
        FROM users u
        JOIN patients p ON u.user_id = p.user_id
        WHERE u.user_id = %s AND u.user_type = 'patient'
    """, (patient_id,))
    
    patient = cursor.fetchone()
    
    # Get patient allergies
    cursor.execute("""
        SELECT a.allergy_name, a.allergy_type, pa.severity, pa.reaction_description,
               pa.diagnosed_date, pa.notes
        FROM patient_allergies pa
        JOIN allergies a ON pa.allergy_id = a.allergy_id
        WHERE pa.patient_id = %s
    """, (patient_id,))
    
    allergies = cursor.fetchall()
    
    # Get patient diagnoses
    cursor.execute("""
        SELECT d.diagnosis_id, d.diagnosis_date, d.diagnosis_code, d.diagnosis_name,
               d.diagnosis_type, d.severity, d.is_chronic, d.is_resolved,
               CONCAT(u.first_name, ' ', u.last_name) AS doctor_name
        FROM diagnoses d
        JOIN users u ON d.doctor_id = u.user_id
        WHERE d.patient_id = %s
        ORDER BY d.diagnosis_date DESC
    """, (patient_id,))
    
    diagnoses = cursor.fetchall()
    
    # Get upcoming appointments
    cursor.execute("""
        SELECT a.appointment_id, a.appointment_date, a.start_time, a.end_time,
               a.appointment_type, a.status, a.reason,
               CONCAT(u.first_name, ' ', u.last_name) AS doctor_name
        FROM appointments a
        JOIN users u ON a.doctor_id = u.user_id
        WHERE a.patient_id = %s AND a.appointment_date >= CURDATE()
        ORDER BY a.appointment_date, a.start_time
    """, (patient_id,))
    
    upcoming_appointments = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    if not patient:
        flash("Patient not found", "danger")
        return redirect(url_for('admin_patients.index'))
    
    return render_template('Admin_Portal/Patients/view_patient.html', 
                           patient=patient, 
                           allergies=allergies,
                           diagnoses=diagnoses,
                           appointments=upcoming_appointments)

# Edit patient form route
@admin_patients.route('/admin/patients/edit/<int:patient_id>', methods=['GET'])
@login_required
def edit_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get patient data with join
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
               p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
               p.insurance_provider, p.insurance_policy_number, p.insurance_group_number,
               p.insurance_expiration, p.marital_status, p.occupation
        FROM users u
        JOIN patients p ON u.user_id = p.user_id
        WHERE u.user_id = %s AND u.user_type = 'patient'
    """, (patient_id,))
    
    patient = cursor.fetchone()
    
    # Get insurance providers for dropdown
    cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
    insurance_providers = cursor.fetchall()
    
    # Get blood type enum values from database
    cursor.execute("""
        SELECT COLUMN_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = 'patients' 
        AND COLUMN_NAME = 'blood_type'
    """)
    
    blood_type_enum = cursor.fetchone()['COLUMN_TYPE']
    # Extract values from enum('value1','value2',...) format
    blood_types = [bt.strip("'") for bt in blood_type_enum.strip('enum()').split(',')]
    
    # Get marital status enum values from database
    cursor.execute("""
        SELECT COLUMN_TYPE 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = 'patients' 
        AND COLUMN_NAME = 'marital_status'
    """)
    
    marital_status_enum = cursor.fetchone()['COLUMN_TYPE']
    # Extract values from enum('value1','value2',...) format
    marital_statuses = [ms.strip("'") for ms in marital_status_enum.strip('enum()').split(',')]
    
    cursor.close()
    connection.close()
    
    if not patient:
        flash("Patient not found", "danger")
        return redirect(url_for('admin_patients.index'))
    
    return render_template('Admin_Portal/Patients/edit_patient.html', 
                           patient=patient, 
                           insurance_providers=insurance_providers,
                           blood_types=blood_types,
                           marital_statuses=marital_statuses)

# Process edit patient form
@admin_patients.route('/admin/patients/edit/<int:patient_id>', methods=['POST'])
@login_required
def edit_patient(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Extract form data
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    date_of_birth = request.form.get('date_of_birth')
    gender = request.form.get('gender')
    blood_type = request.form.get('blood_type')
    height_cm = request.form.get('height_cm') if request.form.get('height_cm') else None
    weight_kg = request.form.get('weight_kg') if request.form.get('weight_kg') else None
    marital_status = request.form.get('marital_status')
    occupation = request.form.get('occupation')
    
    # Check if insurance toggle is enabled
    has_insurance = 'has_insurance' in request.form
    
    # Set insurance fields as None if insurance toggle is off
    if has_insurance:
        insurance_provider = request.form.get('insurance_provider') if request.form.get('insurance_provider') else None
        insurance_policy_number = request.form.get('insurance_policy_number')
        insurance_group_number = request.form.get('insurance_group_number')
        insurance_expiration = request.form.get('insurance_expiration') if request.form.get('insurance_expiration') else None
    else:
        insurance_provider = None
        insurance_policy_number = None
        insurance_group_number = None
        insurance_expiration = None
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Update users table
        cursor.execute("""
            UPDATE users 
            SET first_name = %s, last_name = %s, email = %s, phone = %s
            WHERE user_id = %s
        """, (first_name, last_name, email, phone, patient_id))
        
        # Update patients table
        cursor.execute("""
            UPDATE patients 
            SET date_of_birth = %s, gender = %s, blood_type = %s, 
                height_cm = %s, weight_kg = %s, insurance_provider = %s,
                insurance_policy_number = %s, insurance_group_number = %s,
                insurance_expiration = %s, marital_status = %s, occupation = %s
            WHERE user_id = %s
        """, (date_of_birth, gender, blood_type,
             height_cm, weight_kg, insurance_provider,
             insurance_policy_number, insurance_group_number,
             insurance_expiration, marital_status, occupation, patient_id))
        
        # Commit changes
        connection.commit()
        flash("Patient updated successfully", "success")
        
    except Exception as e:
        flash(f"Error updating patient: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))

# Delete patient confirmation form
@admin_patients.route('/admin/patients/delete/<int:patient_id>', methods=['GET'])
@login_required
def delete_patient_form(patient_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email,
               p.date_of_birth, p.gender, p.insurance_provider
        FROM users u
        JOIN patients p ON u.user_id = p.user_id
        WHERE u.user_id = %s AND u.user_type = 'patient'
    """, (patient_id,))
    
    patient = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    if not patient:
        flash("Patient not found", "danger")
        return redirect(url_for('admin_users.index'))
    
    return render_template('Admin_Portal/Patients/delete_confirmation.html', patient=patient)