import os
from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from db import get_db_connection

admin_doctors = Blueprint('admin_doctors', __name__)

# Index route to view all doctors
@admin_doctors.route('/admin/doctors', methods=['GET'])
@login_required
def index():
    print(f"Current User: {current_user.id}")
    print(f"User Type: {current_user.user_type}")

    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Fetch all doctors with their user details and document count
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                   d.specialization, d.license_number, d.license_state, 
                   d.license_expiration, d.accepting_new_patients,
                   COUNT(dd.document_id) as document_count
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN doctor_documents dd ON u.user_id = dd.doctor_id
            WHERE u.user_type = 'doctor'
            GROUP BY u.user_id
            ORDER BY u.last_name, u.first_name
        """)
        
        doctors = cursor.fetchall()
        
        return render_template('Admin_Portal/Doctors/view_doctors.html', doctors=doctors)
    
    
    finally:
        cursor.close()
        connection.close()

# Route to add a new doctor
@admin_doctors.route('/admin/doctors/add', methods=['GET', 'POST'])
@login_required
def add_doctor():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    if request.method == 'GET':
        return render_template('Admin_Portal/Doctors/add_doctor.html')
    
    # POST method for form submission
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
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
        
        # Generate a temporary password
        temp_password = os.urandom(8).hex()
        hashed_password = generate_password_hash(temp_password)
        
        # Start transaction
        connection.start_transaction()
        
        # Insert into users table
        cursor.execute("""
            INSERT INTO users 
            (first_name, last_name, email, phone, password, user_type)
            VALUES (%s, %s, %s, %s, %s, 'doctor')
        """, (first_name, last_name, email, phone, hashed_password))
        
        # Get the last inserted user ID
        user_id = cursor.lastrowid
        
        # Insert into doctors table
        cursor.execute("""
            INSERT INTO doctors 
            (user_id, specialization, license_number, license_state, 
            license_expiration, accepting_new_patients)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, specialization, license_number, license_state, 
              license_expiration, accepting_new_patients))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_created', 'New doctor account created', %s)
        """, (user_id, current_user.user_id))
        
        # Commit transaction
        connection.commit()
        
        flash(f"Doctor added successfully. Temporary password: {temp_password}", "success")
        return redirect(url_for('admin_doctors.index'))
    
    
    finally:
        cursor.close()
        connection.close()

# Route to view doctor details
@admin_doctors.route('/admin/doctors/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # Get doctor details with documents
        cursor.execute("""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                   d.specialization, d.license_number, d.license_state, 
                   d.license_expiration, d.accepting_new_patients,
                   dd.document_id, dd.document_type, dd.file_name, 
                   dd.file_path, dd.upload_date
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN doctor_documents dd ON u.user_id = dd.doctor_id
            WHERE u.user_id = %s
        """, (doctor_id,))
        
        results = cursor.fetchall()
        
        if not results:
            flash("Doctor not found", "danger")
            return redirect(url_for('admin_doctors.index'))
        
        # Organize doctor details and documents
        doctor = {
            'user_id': results[0]['user_id'],
            'first_name': results[0]['first_name'],
            'last_name': results[0]['last_name'],
            'email': results[0]['email'],
            'phone': results[0]['phone'],
            'specialization': results[0]['specialization'],
            'license_number': results[0]['license_number'],
            'license_state': results[0]['license_state'],
            'license_expiration': results[0]['license_expiration'],
            'accepting_new_patients': results[0]['accepting_new_patients'],
            'documents': []
        }
        
        # Add documents if they exist
        for result in results:
            if result['document_id']:
                doctor['documents'].append({
                    'document_id': result['document_id'],
                    'document_type': result['document_type'],
                    'file_name': result['file_name'],
                    'file_path': result['file_path'],
                    'upload_date': result['upload_date']
                })
        
        return render_template('Admin_Portal/Doctors/doctor_details.html', doctor=doctor)
    
    
    finally:
        cursor.close()
        connection.close()

# Edit doctor form route (existing method from previous code)
@admin_doctors.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET'])
@login_required
def edit_doctor_form(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
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
        
        if not doctor:
            flash("Doctor not found", "danger")
            return redirect(url_for('admin_doctors.index'))
        
        return render_template('Admin_Portal/Doctors/edit_doctors.html', doctor=doctor)
    
    
    finally:
        cursor.close()
        connection.close()

# Process edit doctor form (existing method from previous code)
@admin_doctors.route('/admin/doctors/edit/<int:doctor_id>', methods=['POST'])
@login_required
def edit_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
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
    
    # Basic validation
    if not all([first_name, last_name, email, specialization, license_number]):
        flash("All required fields must be filled", "danger")
        return redirect(url_for('admin_doctors.edit_doctor_form', doctor_id=doctor_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Start transaction
        connection.start_transaction()
        
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
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_updated', 'Doctor profile updated', %s)
        """, (doctor_id, current_user.user_id))
        
        # Commit changes
        connection.commit()
        flash("Doctor updated successfully", "success")
        
        return redirect(url_for('admin_doctors.index'))
    
    
    finally:
        cursor.close()
        connection.close()

# Route to upload doctor document
@admin_doctors.route('/admin/doctors/upload-document/<int:doctor_id>', methods=['POST'])
@login_required
def upload_doctor_document(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    # Check if the post request has the file part
    if 'document' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('admin_doctors.view_doctor', doctor_id=doctor_id))
    
    file = request.files['document']
    document_type = request.form.get('document_type')
    
    # If no file is selected
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('admin_doctors.view_doctor', doctor_id=doctor_id))
    
    # Validate document type
    valid_document_types = ['license', 'certification', 'identity', 'education', 'other']
    if document_type not in valid_document_types:
        flash('Invalid document type', 'danger')
        return redirect(url_for('admin_doctors.view_doctor', doctor_id=doctor_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join('uploads', 'doctor_documents', str(doctor_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # Secure the filename
        filename = secure_filename(file.filename)
        file_path = os.path.join(upload_dir, filename)
        
        # Save the file
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Insert document record
        cursor.execute("""
            INSERT INTO doctor_documents 
            (doctor_id, document_type, file_name, file_path, file_size)
            VALUES (%s, %s, %s, %s, %s)
        """, (doctor_id, document_type, filename, file_path, file_size))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'document_upload', %s, %s)
        """, (doctor_id, f"Uploaded {document_type} document", current_user.user_id))
        
        connection.commit()
        flash(f"Document uploaded successfully", "success")
        
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_doctors.view_doctor', doctor_id=doctor_id))

# Route to delete doctor document
@admin_doctors.route('/admin/doctors/delete-document/<int:document_id>', methods=['POST'])
@login_required
def delete_doctor_document(document_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    try:
        # First, retrieve document details
        cursor.execute("""
            SELECT doctor_id, file_path, document_type 
            FROM doctor_documents 
            WHERE document_id = %s
        """, (document_id,))
        
        document = cursor.fetchone()
        
        if not document:
            flash("Document not found", "danger")
            return redirect(url_for('admin_doctors.index'))
        
        # Delete file from filesystem
        if os.path.exists(document['file_path']):
            os.remove(document['file_path'])
        
        # Delete document record from database
        cursor.execute("""
            DELETE FROM doctor_documents 
            WHERE document_id = %s
        """, (document_id,))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'document_deleted', %s, %s)
        """, (document['doctor_id'], 
              f"Deleted {document['document_type']} document", 
              current_user.user_id))
        
        connection.commit()
        flash("Document deleted successfully", "success")
        
        return redirect(url_for('admin_doctors.view_doctor', doctor_id=document['doctor_id']))
    
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('admin_doctors.index'))

# Route to delete a doctor
@admin_doctors.route('/admin/doctors/delete/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('auth.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Start a transaction
        connection.start_transaction()
        
        # Delete associated doctor documents first
        cursor.execute("""
            DELETE FROM doctor_documents 
            WHERE doctor_id = %s
        """, (doctor_id,))
        
        # Add audit log entry for document deletion
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_delete', 'Deleted all doctor documents', %s)
        """, (doctor_id, current_user.user_id))
        
        # Delete from doctors table
        cursor.execute("""
            DELETE FROM doctors 
            WHERE user_id = %s
        """, (doctor_id,))
        
        # Delete from users table
        cursor.execute("""
            DELETE FROM users 
            WHERE user_id = %s AND user_type = 'doctor'
        """, (doctor_id,))
        
        # Add audit log entry for doctor deletion
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_delete', 'Deleted doctor account', %s)
        """, (doctor_id, current_user.user_id))
        
        # Commit the transaction
        connection.commit()
        
        flash("Doctor deleted successfully", "success")
        return redirect(url_for('admin_doctors.index'))
    
    finally:
        cursor.close()
        connection.close()