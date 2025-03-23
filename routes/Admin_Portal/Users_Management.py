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

@admin_users.route('/admin/users/redirect/<int:user_id>', methods=['GET'])
@login_required
def redirect_user(user_id):
    """Redirect to appropriate route based on user type"""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get the user's type
    cursor.execute("SELECT user_type FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    if not user:
        flash("User not found", "danger")
        return redirect(url_for('admin_users.index'))
    
    # Redirect based on user type
    if user['user_type'] == 'doctor':
        return redirect(url_for('admin_doctors.edit_doctor', doctor_id=user_id))
    elif user['user_type'] == 'patient':
        return redirect(url_for('admin_patients.edit_patient', patient_id=user_id))
    elif user['user_type'] == 'admin':
        return redirect(url_for('admin_management.edit_admin', admin_id=user_id))
    else:
        # Default to the view_user route for any other type
        return redirect(url_for('admin_users.view_user', user_id=user_id))

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
                   p.insurance_expiration, p.marital_status, p.occupation
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
    
    cursor.close()
    connection.close()
    
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
    
    if request.method == 'POST':
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
                
                cursor.execute("""
                    INSERT INTO patients (user_id, date_of_birth, gender, blood_type)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, date_of_birth, gender, blood_type))
            
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
    
    # For GET request - show the form
    return render_template('Admin_Portal/Users/add_user.html')

@admin_users.route('/admin/users/delete/<int:user_id>', methods=['GET', 'POST'])
@login_required
def delete_user(user_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Prevent admins from deleting themselves
    if user_id == current_user.id:  
        flash("Cannot delete your own account", "danger")
        return redirect(url_for('admin_users.index'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # For GET request - show confirmation page
    if request.method == 'GET':
        cursor.execute("""
            SELECT user_id, username, email, first_name, last_name, user_type
            FROM users WHERE user_id = %s
        """, (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin_users.index'))
        
        cursor.close()
        connection.close()
        
        return render_template('Admin_Portal/Users/delete_confirmation.html', user=user)
    
    # For POST request - actually delete the user
    try:
        # Get user type first
        cursor.execute("SELECT user_type FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash("User not found", "danger")
            return redirect(url_for('admin_users.index'))
        
        user_type = user['user_type']
        
        # No explicit transaction start - we'll assume the connection is already in transaction mode
        # or is in auto-commit mode
        
        # Handle dependencies first - you should add more tables if needed
        # Check if audit_log table references user_id
        try:
            cursor.execute("DELETE FROM audit_log WHERE user_id = %s", (user_id,))
        except Exception as e:
            # If this fails (table doesn't exist or no foreign key), continue
            pass
            
        # Check if appointments table references user_id
        try:
            cursor.execute("DELETE FROM appointments WHERE doctor_id = %s OR patient_id = %s", (user_id, user_id))
        except Exception as e:
            # If this fails, continue
            pass
        
        # Delete from type-specific tables
        if user_type == 'doctor':
            cursor.execute("DELETE FROM doctors WHERE user_id = %s", (user_id,))
        elif user_type == 'patient':
            cursor.execute("DELETE FROM patients WHERE user_id = %s", (user_id,))
        
        # Delete from users table
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Add audit log entry (separate from the deleted user)
        cursor.execute("""
            INSERT INTO audit_log (action_type, action_details, performed_by_id)
            VALUES (%s, %s, %s)
        """, ('user_deleted', f"User ID {user_id} ({user_type}) was deleted", current_user.id))
        
        # Commit the transaction
        connection.commit()
        
        flash("User deleted successfully", "success")
        
    except Exception as e:
        # Try to rollback, but don't throw an error if it fails
        try:
            connection.rollback()
        except:
            pass
        flash(f"Error deleting user: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))