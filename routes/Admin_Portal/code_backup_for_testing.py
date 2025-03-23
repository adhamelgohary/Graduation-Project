from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection
from werkzeug.security import generate_password_hash

admin_users = Blueprint('admin_users', __name__)

@admin_users.route('/admin/users', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get filter parameters
    user_type = request.args.get('user_type', 'all')
    status = request.args.get('status', 'all')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'last_name')
    sort_order = request.args.get('sort_order', 'asc')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Base query without filters
    query = """
        SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, 
               u.user_type, u.phone, u.account_status, u.created_at,
               u.last_login, 
               CASE 
                   WHEN u.user_type = 'doctor' THEN d.specialization
                   ELSE NULL 
               END AS specialization,
               CASE 
                   WHEN u.user_type = 'patient' THEN p.date_of_birth
                   ELSE NULL 
               END AS date_of_birth
        FROM users u
        LEFT JOIN doctors d ON u.user_id = d.user_id AND u.user_type = 'doctor'
        LEFT JOIN patients p ON u.user_id = p.user_id AND u.user_type = 'patient'
        WHERE 1=1
    """
    
    # Initialize parameters list
    params = []
    
    # Add filters to query
    if user_type != 'all':
        query += " AND u.user_type = %s"
        params.append(user_type)
    
    if status != 'all':
        query += " AND u.account_status = %s"
        params.append(status)
    
    if search_query:
        query += """ AND (
            u.username LIKE %s OR 
            u.email LIKE %s OR 
            u.first_name LIKE %s OR 
            u.last_name LIKE %s OR 
            u.phone LIKE %s
        )"""
        search_param = f'%{search_query}%'
        params.extend([search_param, search_param, search_param, search_param, search_param])
    
    # Add sorting
    valid_sort_fields = {
        'username': 'u.username',
        'email': 'u.email',
        'first_name': 'u.first_name',
        'last_name': 'u.last_name',
        'user_type': 'u.user_type',
        'account_status': 'u.account_status',
        'created_at': 'u.created_at',
        'last_login': 'u.last_login'
    }
    
    sort_field = valid_sort_fields.get(sort_by, 'u.last_name')
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    
    query += f" ORDER BY {sort_field} {sort_direction}"
    
    # Execute query
    cursor.execute(query, tuple(params))
    users = cursor.fetchall()
    
    # Get user statistics
    cursor.execute("""
        SELECT 
            COUNT(*) AS total_users,
            SUM(CASE WHEN user_type = 'admin' THEN 1 ELSE 0 END) AS admin_count,
            SUM(CASE WHEN user_type = 'doctor' THEN 1 ELSE 0 END) AS doctor_count,
            SUM(CASE WHEN user_type = 'patient' THEN 1 ELSE 0 END) AS patient_count,
            SUM(CASE WHEN user_type = 'staff' THEN 1 ELSE 0 END) AS staff_count,
            SUM(CASE WHEN account_status = 'active' THEN 1 ELSE 0 END) AS active_count,
            SUM(CASE WHEN account_status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN account_status = 'suspended' THEN 1 ELSE 0 END) AS suspended_count,
            SUM(CASE WHEN account_status = 'deactivated' THEN 1 ELSE 0 END) AS deactivated_count
        FROM users
    """)
    
    user_stats = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/Users/manage_users.html', 
                           users=users, 
                           user_stats=user_stats,
                           filter_user_type=user_type,
                           filter_status=status,
                           search_query=search_query,
                           sort_by=sort_by,
                           sort_order=sort_order)

@admin_users.route('/admin/users/view/<int:user_id>', methods=['GET'])
@login_required
def view_user(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get basic user information
    cursor.execute("""
        SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, 
               u.user_type, u.phone, u.account_status, u.created_at,
               u.last_login
        FROM users u
        WHERE u.user_id = %s
    """, (user_id,))
    
    user = cursor.fetchone()
    
    if not user:
        flash("User not found", "danger")
        return redirect(url_for('admin_users.index'))
    
    # Get additional data based on user type
    if user['user_type'] == 'doctor':
        cursor.execute("""
            SELECT d.specialization, d.license_number, d.license_state, 
                   d.license_expiration, d.accepting_new_patients
            FROM doctors d
            WHERE d.user_id = %s
        """, (user_id,))
        doctor_details = cursor.fetchone()
        user.update(doctor_details or {})
        
        # Get appointment count
        cursor.execute("""
            SELECT COUNT(*) as appointment_count, 
                   COUNT(CASE WHEN appointment_date >= CURDATE() THEN 1 END) as upcoming_count
            FROM appointments 
            WHERE doctor_id = %s
        """, (user_id,))
        appointment_stats = cursor.fetchone()
        user.update(appointment_stats or {})
        
    elif user['user_type'] == 'patient':
        cursor.execute("""
            SELECT p.date_of_birth, p.gender, p.blood_type, p.height_cm, 
                   p.weight_kg, p.insurance_provider, p.insurance_policy_number,
                   p.insurance_group_number, p.insurance_expiration, p.marital_status, p.occupation
            FROM patients p
            WHERE p.user_id = %s
        """, (user_id,))
        patient_details = cursor.fetchone()
        user.update(patient_details or {})
        
        # Get appointment count
        cursor.execute("""
            SELECT COUNT(*) as appointment_count, 
                   COUNT(CASE WHEN appointment_date >= CURDATE() THEN 1 END) as upcoming_count
            FROM appointments 
            WHERE patient_id = %s
        """, (user_id,))
        appointment_stats = cursor.fetchone()
        user.update(appointment_stats or {})
        
        # Get patient allergies
        cursor.execute("""
            SELECT a.allergy_name, a.allergy_type, pa.severity, pa.reaction_description,
                pa.diagnosed_date, pa.notes
            FROM patient_allergies pa
            JOIN allergies a ON pa.allergy_id = a.allergy_id
            WHERE pa.patient_id = %s
        """, (user_id,))
        
        user['allergies'] = cursor.fetchall()
        
        # Get patient diagnoses
        cursor.execute("""
            SELECT d.diagnosis_id, d.diagnosis_date, d.diagnosis_code, d.diagnosis_name,
                d.diagnosis_type, d.severity, d.is_chronic, d.is_resolved,
                CONCAT(u.first_name, ' ', u.last_name) AS doctor_name
            FROM diagnoses d
            JOIN users u ON d.doctor_id = u.user_id
            WHERE d.patient_id = %s
            ORDER BY d.diagnosis_date DESC
        """, (user_id,))
        
        user['diagnoses'] = cursor.fetchall()
    
    # Get audit log entries for this user
    cursor.execute("""
        SELECT action_type, action_details, performed_at, 
               performed_by_id, 
               CONCAT(u.first_name, ' ', u.last_name) as performed_by_name
        FROM audit_log al
        JOIN users u ON al.performed_by_id = u.user_id
        WHERE al.user_id = %s
        ORDER BY performed_at DESC
        LIMIT 10
    """, (user_id,))
    
    audit_logs = cursor.fetchall()
    
    # Get upcoming appointments if patient
    if user['user_type'] == 'patient':
        cursor.execute("""
            SELECT a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                a.appointment_type, a.status, a.reason,
                CONCAT(u.first_name, ' ', u.last_name) AS doctor_name
            FROM appointments a
            JOIN users u ON a.doctor_id = u.user_id
            WHERE a.patient_id = %s AND a.appointment_date >= CURDATE()
            ORDER BY a.appointment_date, a.start_time
        """, (user_id,))
        
        user['upcoming_appointments'] = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    # Determine which template to use based on user type
    if user['user_type'] == 'patient':
        return render_template('Admin_Portal/Patients/view_patient.html', 
                            patient=user, 
                            allergies=user.get('allergies', []),
                            diagnoses=user.get('diagnoses', []),
                            appointments=user.get('upcoming_appointments', []),
                            audit_logs=audit_logs)
    else:
        return render_template('Admin_Portal/Users/view_user.html', 
                            user=user, 
                            audit_logs=audit_logs)

@admin_users.route('/admin/users/update-status/<int:user_id>', methods=['POST'])
@login_required
def update_status(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    new_status = request.form.get('status')
    if new_status not in ['active', 'pending', 'suspended', 'deactivated']:
        flash("Invalid status", "danger")
        return redirect(url_for('admin_users.view_user', user_id=user_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Update user status
        cursor.execute("""
            UPDATE users SET account_status = %s WHERE user_id = %s
        """, (new_status, user_id))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'status_update', %s, %s)
        """, (user_id, f"Account status changed to {new_status}", current_user.user_id))
        
        connection.commit()
        flash(f"User status updated to {new_status}", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error updating user status: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.view_user', user_id=user_id))

@admin_users.route('/admin/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def reset_password(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    new_password = request.form.get('new_password')
    
    # Validate password
    if not new_password or len(new_password) < 8:
        flash("Password must be at least 8 characters long", "danger")
        return redirect(url_for('admin_users.view_user', user_id=user_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Hash password
        password_hash = generate_password_hash(new_password)
        
        # Update user password
        cursor.execute("""
            UPDATE users SET password_hash = %s WHERE user_id = %s
        """, (password_hash, user_id))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'password_reset', %s, %s)
        """, (user_id, "Password reset by administrator", current_user.user_id))
        
        connection.commit()
        flash("User password has been reset", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error resetting password: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.view_user', user_id=user_id))

@admin_users.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    if request.method == 'GET':
        # For GET request - show the form
        # Get insurance providers for dropdown if adding a patient
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
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
        
        cursor.close()
        connection.close()
        
        return render_template('Admin_Portal/Users/add_user.html', 
                              insurance_providers=insurance_providers,
                              blood_types=blood_types)
    
    # For POST request - process the form
    # Extract common user data
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    user_type = request.form.get('user_type')
    account_status = request.form.get('account_status', 'active')
    
    # Validate required fields
    if not all([username, email, password, first_name, last_name, user_type]):
        flash("All required fields must be filled", "danger")
        return redirect(url_for('admin_users.add_user'))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Hash password
        password_hash = generate_password_hash(password)
        
        # Begin transaction
        connection.begin()
        
        # Insert into users table
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name, 
                              user_type, phone, account_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, email, password_hash, first_name, last_name, user_type, phone, account_status))
        
        user_id = cursor.lastrowid
        
        # Handle user-type specific data
        if user_type == 'doctor':
            specialization = request.form.get('specialization')
            license_number = request.form.get('license_number')
            license_state = request.form.get('license_state')
            license_expiration = request.form.get('license_expiration')
            accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
            
            cursor.execute("""
                INSERT INTO doctors (user_id, specialization, license_number, 
                                  license_state, license_expiration, accepting_new_patients)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, specialization, license_number, license_state, 
                  license_expiration, accepting_new_patients))
            
        elif user_type == 'patient':
            date_of_birth = request.form.get('date_of_birth')
            gender = request.form.get('gender')
            blood_type = request.form.get('blood_type')
            height_cm = request.form.get('height_cm') if request.form.get('height_cm') else None
            weight_kg = request.form.get('weight_kg') if request.form.get('weight_kg') else None
            insurance_provider = request.form.get('insurance_provider')
            insurance_policy_number = request.form.get('insurance_policy_number')
            insurance_group_number = request.form.get('insurance_group_number')
            insurance_expiration = request.form.get('insurance_expiration')
            marital_status = request.form.get('marital_status')
            occupation = request.form.get('occupation')
            
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
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'user_created', %s, %s)
        """, (user_id, f"New {user_type} account created", current_user.user_id))
        
        # Commit transaction
        connection.commit()
        flash(f"New {user_type} created successfully", "success")
        return redirect(url_for('admin_users.index'))
        
    except Exception as e:
        connection.rollback()
        flash(f"Error creating user: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.add_user'))

@admin_users.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get user type
    cursor.execute("SELECT user_type FROM users WHERE user_id = %s", (user_id,))
    user_type_result = cursor.fetchone()
    
    if not user_type_result:
        flash("User not found", "danger")
        return redirect(url_for('admin_users.index'))
    
    user_type = user_type_result['user_type']
    
    if request.method == 'GET':
        # For GET request - show the edit form
        if user_type == 'patient':
            # Get patient data with join
            cursor.execute("""
                SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                    p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
                    p.insurance_provider, p.insurance_policy_number, p.insurance_group_number,
                    p.insurance_expiration, p.marital_status, p.occupation
                FROM users u
                JOIN patients p ON u.user_id = p.user_id
                WHERE u.user_id = %s AND u.user_type = 'patient'
            """, (user_id,))
            
            user = cursor.fetchone()
            
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
            
            return render_template('Admin_Portal/Patients/edit_patient.html', 
                                patient=user, 
                                insurance_providers=insurance_providers,
                                blood_types=blood_types,
                                marital_statuses=marital_statuses)
        else:
            # Handle other user types edit forms
            cursor.execute("""
                SELECT * FROM users WHERE user_id = %s
            """, (user_id,))
            
            user = cursor.fetchone()
            
            # For doctors, get additional info
            if user_type == 'doctor':
                cursor.execute("""
                    SELECT * FROM doctors WHERE user_id = %s
                """, (user_id,))
                doctor_info = cursor.fetchone()
                user.update(doctor_info or {})
            
            cursor.close()
            connection.close()
            
            return render_template('Admin_Portal/Users/edit_user.html', user=user)
    
    # For POST request - process the form
    if user_type == 'patient':
        # Extract form data for patient
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
        
        try:
            # Update users table
            cursor.execute("""
                UPDATE users 
                SET first_name = %s, last_name = %s, email = %s, phone = %s
                WHERE user_id = %s
            """, (first_name, last_name, email, phone, user_id))
            
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
                insurance_expiration, marital_status, occupation, user_id))
        
        except Exception as e:
            connection.rollback()
            flash(f"Error updating patient: {str(e)}", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('admin_users.edit_user', user_id=user_id))
    
    else:
        # Handle updates for other user types
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        account_status = request.form.get('account_status')
        
        try:
            # Update users table
            cursor.execute("""
                UPDATE users 
                SET first_name = %s, last_name = %s, email = %s, phone = %s,
                    account_status = %s
                WHERE user_id = %s
            """, (first_name, last_name, email, phone, account_status, user_id))
            
            # If doctor, update doctor-specific fields
            if user_type == 'doctor':
                specialization = request.form.get('specialization')
                license_number = request.form.get('license_number')
                license_state = request.form.get('license_state')
                license_expiration = request.form.get('license_expiration')
                accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
                
                cursor.execute("""
                    UPDATE doctors
                    SET specialization = %s, license_number = %s, license_state = %s,
                        license_expiration = %s, accepting_new_patients = %s
                    WHERE user_id = %s
                """, (specialization, license_number, license_state, 
                     license_expiration, accepting_new_patients, user_id))
            
        except Exception as e:
            connection.rollback()
            flash(f"Error updating user: {str(e)}", "danger")
            cursor.close()
            connection.close()
            return redirect(url_for('admin_users.edit_user', user_id=user_id))
    
    # Add audit log entry
    cursor.execute("""
        INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
        VALUES (%s, 'user_updated', %s, %s)
    """, (user_id, f"User profile updated", current_user.user_id))
    
    # Commit transaction
    connection.commit()
    flash("User updated successfully", "success")
    
    cursor.close()
    connection.close()
    
    return redirect(url_for('admin_users.view_user', user_id=user_id))
@admin_users.route('/admin/users/delete/<int:user_id>', methods=['GET', 'POST'])
@login_required
def delete_user(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Prevent admins from deleting themselves
    if user_id == current_user.user_id:
        flash("Cannot delete your own account", "danger")
        return redirect(url_for('admin_users.index'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # For GET request - show confirmation page
    if request.method == 'GET':
        cursor.execute("""
            SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, u.user_type,
                   CASE 
                       WHEN u.user_type = 'patient' THEN p.date_of_birth
                       ELSE NULL 
                   END AS date_of_birth,
                   CASE 
                       WHEN u.user_type = 'patient' THEN p.gender
                       ELSE NULL 
                   END AS gender,
                   CASE 
                       WHEN u.user_type = 'patient' THEN p.insurance_provider
                       ELSE NULL 
                   END AS insurance_provider
            FROM users u
            LEFT JOIN patients p ON u.user_id = p.user_id AND u.user_type = 'patient'
            WHERE u.user_id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin_users.index'))
        
        # Check if user has any dependencies
        dependencies = []
        
        # Check for appointments if user is a doctor or patient
        if user['user_type'] == 'doctor':
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments
                WHERE doctor_id = %s AND appointment_date >= CURDATE()
            """, (user_id,))
            
            result = cursor.fetchone()
            if result and result['count'] > 0:
                dependencies.append(f"User has {result['count']} upcoming appointments as a doctor")
        
        elif user['user_type'] == 'patient':
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments
                WHERE patient_id = %s AND appointment_date >= CURDATE()
            """, (user_id,))
            
            result = cursor.fetchone()
            if result and result['count'] > 0:
                dependencies.append(f"User has {result['count']} upcoming appointments as a patient")
            
            # Check for active prescriptions
            cursor.execute("""
                SELECT COUNT(*) as count FROM prescriptions
                WHERE patient_id = %s AND end_date >= CURDATE()
            """, (user_id,))
            
            result = cursor.fetchone()
            if result and result['count'] > 0:
                dependencies.append(f"User has {result['count']} active prescriptions")
        
        cursor.close()
        connection.close()
        
        return render_template('Admin_Portal/Users/delete_user.html', 
                              user=user, 
                              dependencies=dependencies)
    
    # For POST request - perform deletion
    try:
        # Begin transaction
        connection.begin()
        
        # Get user type first
        cursor.execute("SELECT user_type FROM users WHERE user_id = %s", (user_id,))
        user_type_result = cursor.fetchone()
        
        if not user_type_result:
            flash("User not found", "danger")
            return redirect(url_for('admin_users.index'))
        
        user_type = user_type_result['user_type']
        
        # Delete user type specific records
        if user_type == 'doctor':
            cursor.execute("DELETE FROM doctors WHERE user_id = %s", (user_id,))
        elif user_type == 'patient':
            # Delete patient allergies
            cursor.execute("DELETE FROM patient_allergies WHERE patient_id = %s", (user_id,))
            
            # Delete patient diagnoses
            cursor.execute("DELETE FROM diagnoses WHERE patient_id = %s", (user_id,))
            
            # Delete patient medication records
            cursor.execute("DELETE FROM patient_medications WHERE patient_id = %s", (user_id,))
            
            # Delete patient table entry
            cursor.execute("DELETE FROM patients WHERE user_id = %s", (user_id,))
        elif user_type == 'staff':
            cursor.execute("DELETE FROM staff WHERE user_id = %s", (user_id,))
        
        # Delete audit log entries
        cursor.execute("DELETE FROM audit_log WHERE user_id = %s", (user_id,))
        
        # Finally delete the user record
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Create a final audit log entry for the deletion, but with the current admin as the reference
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'user_deleted', %s, %s)
        """, (current_user.user_id, f"Deleted user ID {user_id}", current_user.user_id))
        
        # Commit transaction
        connection.commit()
        flash("User deleted successfully", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error deleting user: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))

@admin_users.route('/admin/users/search', methods=['GET'])
@login_required
def search_users():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    search_query = request.args.get('q', '')
    if not search_query or len(search_query) < 2:
        return jsonify([])
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT u.user_id, u.username, u.email, 
               CONCAT(u.first_name, ' ', u.last_name) AS full_name,
               u.user_type
        FROM users u
        WHERE u.username LIKE %s OR 
              u.email LIKE %s OR 
              u.first_name LIKE %s OR 
              u.last_name LIKE %s OR
              CONCAT(u.first_name, ' ', u.last_name) LIKE %s
        LIMIT 10
    """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', 
          f'%{search_query}%', f'%{search_query}%'))
    
    users = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return jsonify(users)

@admin_users.route('/admin/users/export', methods=['GET'])
@login_required
def export_users():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get filter parameters
    user_type = request.args.get('user_type', 'all')
    status = request.args.get('status', 'all')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Base query without filters
    query = """
        SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, 
               u.user_type, u.phone, u.account_status, u.created_at,
               u.last_login
        FROM users u
        WHERE 1=1
    """
    
    # Initialize parameters list
    params = []
    
    # Add filters to query
    if user_type != 'all':
        query += " AND u.user_type = %s"
        params.append(user_type)
    
    if status != 'all':
        query += " AND u.account_status = %s"
        params.append(status)
    
    # Add sorting
    query += " ORDER BY u.last_name, u.first_name"
    
    # Execute query
    cursor.execute(query, tuple(params))
    users = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    # Create CSV response
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header row
    if users:
        writer.writerow(users[0].keys())
    
        # Write data rows
        for user in users:
            writer.writerow(user.values())
    
    # Create response
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=users_export_{datetime.now().strftime('%Y%m%d')}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response

@admin_users.route('/admin/users/audit-log', methods=['GET'])
@login_required
def view_audit_log():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    user_id = request.args.get('user_id')
    action_type = request.args.get('action_type', 'all')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Base query
    query = """
        SELECT al.log_id, al.user_id, al.action_type, 
               al.action_details, al.performed_at, al.performed_by_id,
               CONCAT(u1.first_name, ' ', u1.last_name) AS user_name,
               CONCAT(u2.first_name, ' ', u2.last_name) AS performed_by_name
        FROM audit_log al
        JOIN users u1 ON al.user_id = u1.user_id
        JOIN users u2 ON al.performed_by_id = u2.user_id
        WHERE 1=1
    """
    
    # Initialize parameters list
    params = []
    
    # Add filters to query
    if user_id:
        query += " AND al.user_id = %s"
        params.append(user_id)
    
    if action_type != 'all':
        query += " AND al.action_type = %s"
        params.append(action_type)
    
    if start_date:
        query += " AND DATE(al.performed_at) >= %s"
        params.append(start_date)
    
    if end_date:
        query += " AND DATE(al.performed_at) <= %s"
        params.append(end_date)
    
    # Add sorting
    query += " ORDER BY al.performed_at DESC"
    
    # Add pagination
    page = int(request.args.get('page', 1))
    per_page = 50
    query += " LIMIT %s OFFSET %s"
    params.append(per_page)
    params.append((page - 1) * per_page)
    
    # Execute query
    cursor.execute(query, tuple(params))
    logs = cursor.fetchall()
    
    # Get total count for pagination
    count_query = """
        SELECT COUNT(*) as count FROM audit_log al
        WHERE 1=1
    """
    
    # Reset params list for count query
    count_params = []
    
    if user_id:
        count_query += " AND al.user_id = %s"
        count_params.append(user_id)
    
    if action_type != 'all':
        count_query += " AND al.action_type = %s"
        count_params.append(action_type)
    
    if start_date:
        count_query += " AND DATE(al.performed_at) >= %s"
        count_params.append(start_date)
    
    if end_date:
        count_query += " AND DATE(al.performed_at) <= %s"
        count_params.append(end_date)
    
    cursor.execute(count_query, tuple(count_params))
    total_count = cursor.fetchone()['count']
    
    total_pages = (total_count + per_page - 1) // per_page
    
    # Get unique action types for filter dropdown
    cursor.execute("SELECT DISTINCT action_type FROM audit_log ORDER BY action_type")
    action_types = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/audit_log.html', 
                          logs=logs,
                          action_types=action_types,
                          current_page=page,
                          total_pages=total_pages,
                          filter_user_id=user_id,
                          filter_action_type=action_type,
                          filter_start_date=start_date,
                          filter_end_date=end_date)