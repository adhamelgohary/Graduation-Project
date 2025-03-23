from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection

admin_doctors = Blueprint('admin_doctors', __name__)


# Add doctor form route
@admin_doctors.route('/admin/doctors/add', methods=['GET'])
@login_required
def add_doctor_form():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    return render_template('Admin_Portal/Doctors/add_doctors.html')

# Process add doctor form
@admin_doctors.route('/admin/doctors/add', methods=['POST'])
@login_required
def add_doctor():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Extract form data
    username = request.form.get('username')
    email = request.form.get('email')
    password_hash = request.form.get('password_hash')  # Ensure this is properly hashed
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone')
    specialization = request.form.get('specialization')
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state')
    license_expiration = request.form.get('license_expiration')
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # First, insert into users table
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name, 
                              user_type, phone)
            VALUES (%s, %s, %s, %s, %s, 'doctor', %s)
        """, (username, email, password_hash, first_name, last_name, phone))
        
        # Get the auto-generated user_id
        user_id = cursor.lastrowid
        
        # Then, insert into doctors table
        cursor.execute("""
            INSERT INTO doctors (user_id, specialization, license_number, 
                               license_state, license_expiration, accepting_new_patients)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, specialization, license_number, license_state, 
              license_expiration, accepting_new_patients))
        
        # Commit changes
        connection.commit()
        flash("Doctor added successfully", "success")
        
    except Exception as e:
        flash(f"Error adding doctor: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))

# Edit doctor form route
@admin_doctors.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET'])
@login_required
def edit_doctor_form(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get doctor data with join
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
               d.specialization, d.license_number, d.license_state, 
               d.license_expiration, d.accepting_new_patients
        FROM users u
        JOIN doctors d ON u.user_id = d.user_id
        WHERE u.user_id = %s AND u.user_type = 'doctor'
    """, (doctor_id,))
    
    doctor = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    if not doctor:
        flash("Doctor not found", "danger")
        return redirect(url_for('admin_doctors.index'))
    
    return render_template('Admin_Portal/Doctors/edit_doctors.html', doctor=doctor)

# Process edit doctor form
@admin_doctors.route('/admin/doctors/edit/<int:doctor_id>', methods=['POST'])
@login_required
def edit_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Extract form data
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    specialization = request.form.get('specialization')
    license_number = request.form.get('license_number')
    license_state = request.form.get('license_state')
    license_expiration = request.form.get('license_expiration')
    accepting_new_patients = 1 if request.form.get('accepting_new_patients') else 0
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Update users table
        cursor.execute("""
            UPDATE users 
            SET first_name = %s, last_name = %s, email = %s, phone = %s
            WHERE user_id = %s
        """, (first_name, last_name, email, phone, doctor_id))
        
        # Update doctors table
        cursor.execute("""
            UPDATE doctors 
            SET specialization = %s, license_number = %s, 
                license_state = %s, license_expiration = %s, 
                accepting_new_patients = %s
            WHERE user_id = %s
        """, (specialization, license_number, license_state, 
              license_expiration, accepting_new_patients, doctor_id))
        
        # Commit changes
        connection.commit()
        flash("Doctor updated successfully", "success")
        
    except Exception as e:
        flash(f"Error updating doctor: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_users.index'))

# Delete doctor confirmation form
@admin_doctors.route('/admin/doctors/delete/<int:doctor_id>', methods=['GET'])
@login_required
def delete_doctor_form(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT u.user_id, u.first_name, u.last_name, u.email, 
               d.specialization, d.license_number
        FROM users u
        JOIN doctors d ON u.user_id = d.user_id
        WHERE u.user_id = %s AND u.user_type = 'doctor'
    """, (doctor_id,))
    
    doctor = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    if not doctor:
        flash("Doctor not found", "danger")
        return redirect(url_for('admin_doctors.index'))
    
    return render_template('Admin_Portal/Doctors/delete_confirmation.html', doctor=doctor)