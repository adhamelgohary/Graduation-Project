from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import datetime

doctor_approvals = Blueprint('doctor_approvals', __name__)

@doctor_approvals.route('/admin/doctor-approvals', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    # Get filter parameters
    status = request.args.get('status', 'pending')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Base query for doctor registrations
    query = """
        SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, 
               u.phone, u.account_status, u.created_at,
               d.specialization, d.license_number, d.license_state, 
               d.license_expiration, d.verification_status,
               d.document_id, d.rejection_reason
        FROM users u
        JOIN doctors d ON u.user_id = d.user_id
        WHERE u.user_type = 'doctor'
    """
    
    # Add status filter
    if status != 'all':
        query += " AND d.verification_status = %s"
        params = (status,)
    else:
        params = ()
    
    # Add sorting
    valid_sort_fields = {
        'created_at': 'u.created_at',
        'last_name': 'u.last_name',
        'specialization': 'd.specialization',
        'license_expiration': 'd.license_expiration'
    }
    
    sort_field = valid_sort_fields.get(sort_by, 'u.created_at')
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    
    query += f" ORDER BY {sort_field} {sort_direction}"
    
    # Execute query
    cursor.execute(query, params)
    doctor_registrations = cursor.fetchall()
    
    # Get statistics
    cursor.execute("""
        SELECT 
            COUNT(*) AS total_doctors,
            SUM(CASE WHEN verification_status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
            SUM(CASE WHEN verification_status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN verification_status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
        FROM doctors
    """)
    
    stats = cursor.fetchone()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/DoctorApprovals/doctor_approvals.html', 
                          doctor_registrations=doctor_registrations, 
                          stats=stats,
                          current_status=status,
                          sort_by=sort_by,
                          sort_order=sort_order)

@doctor_approvals.route('/admin/doctor-approvals/view/<int:doctor_id>', methods=['GET'])
@login_required
def view_application(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Get doctor application details
    cursor.execute("""
        SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, 
               u.phone, u.account_status, u.created_at,
               d.specialization, d.license_number, d.license_state, 
               d.license_expiration, d.accepting_new_patients,
               d.verification_status, d.document_id, d.rejection_reason,
               d.clinic_address, d.education, d.certifications
        FROM users u
        JOIN doctors d ON u.user_id = d.user_id
        WHERE u.user_id = %s AND u.user_type = 'doctor'
    """, (doctor_id,))
    
    doctor = cursor.fetchone()
    
    if not doctor:
        flash("Doctor application not found", "danger")
        return redirect(url_for('doctor_approvals.index'))
    
    # Get uploaded documents if any
    cursor.execute("""
        SELECT document_id, document_type, file_name, upload_date
        FROM doctor_documents
        WHERE doctor_id = %s
        ORDER BY upload_date DESC
    """, (doctor_id,))
    
    documents = cursor.fetchall()
    
    # Get review history
    cursor.execute("""
        SELECT review_id, reviewer_id, review_date, action, notes,
               CONCAT(u.first_name, ' ', u.last_name) AS reviewer_name
        FROM doctor_reviews
        JOIN users u ON reviewer_id = u.user_id
        WHERE doctor_id = %s
        ORDER BY review_date DESC
    """, (doctor_id,))
    
    reviews = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return render_template('Admin_Portal/DoctorApprovals/view_application.html', 
                          doctor=doctor,
                          documents=documents,
                          reviews=reviews)

@doctor_approvals.route('/admin/doctor-approvals/approve/<int:doctor_id>', methods=['POST'])
@login_required
def approve_application(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    notes = request.form.get('approval_notes', '')
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Begin transaction
        connection.begin()
        
        # Update doctor verification status
        cursor.execute("""
            UPDATE doctors SET verification_status = 'approved',
            approval_date = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (doctor_id,))
        
        # Update user account status
        cursor.execute("""
            UPDATE users SET account_status = 'active'
            WHERE user_id = %s AND user_type = 'doctor'
        """, (doctor_id,))
        
        # Add review record
        cursor.execute("""
            INSERT INTO doctor_reviews (doctor_id, reviewer_id, review_date, action, notes)
            VALUES (%s, %s, CURRENT_TIMESTAMP, 'approved', %s)
        """, (doctor_id, current_user.user_id, notes))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_approval', 'Doctor registration approved', %s)
        """, (doctor_id, current_user.user_id))
        
        # Commit transaction
        connection.commit()
        flash("Doctor registration approved successfully", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error approving doctor registration: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('doctor_approvals.index'))

@doctor_approvals.route('/admin/doctor-approvals/reject/<int:doctor_id>', methods=['POST'])
@login_required
def reject_application(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    rejection_reason = request.form.get('rejection_reason', '')
    notes = request.form.get('rejection_notes', '')
    
    if not rejection_reason:
        flash("Rejection reason is required", "danger")
        return redirect(url_for('doctor_approvals.view_application', doctor_id=doctor_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Begin transaction
        connection.begin()
        
        # Update doctor verification status
        cursor.execute("""
            UPDATE doctors SET verification_status = 'rejected',
            rejection_reason = %s
            WHERE user_id = %s
        """, (rejection_reason, doctor_id))
        
        # Add review record
        cursor.execute("""
            INSERT INTO doctor_reviews (doctor_id, reviewer_id, review_date, action, notes)
            VALUES (%s, %s, CURRENT_TIMESTAMP, 'rejected', %s)
        """, (doctor_id, current_user.user_id, notes))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'doctor_rejection', %s, %s)
        """, (doctor_id, f"Doctor registration rejected: {rejection_reason}", current_user.user_id))
        
        # Commit transaction
        connection.commit()
        flash("Doctor registration rejected", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error rejecting doctor registration: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('doctor_approvals.index'))

@doctor_approvals.route('/admin/doctor-approvals/request-info/<int:doctor_id>', methods=['POST'])
@login_required
def request_additional_info(doctor_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    requested_info = request.form.get('requested_info', '')
    
    if not requested_info:
        flash("You must specify what additional information is needed", "danger")
        return redirect(url_for('doctor_approvals.view_application', doctor_id=doctor_id))
    
    connection = get_db_connection()
    cursor = connection.cursor()
    
    try:
        # Begin transaction
        connection.begin()
        
        # Update doctor verification status
        cursor.execute("""
            UPDATE doctors SET verification_status = 'pending_info',
            info_requested = %s, info_requested_date = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """, (requested_info, doctor_id))
        
        # Add review record
        cursor.execute("""
            INSERT INTO doctor_reviews (doctor_id, reviewer_id, review_date, action, notes)
            VALUES (%s, %s, CURRENT_TIMESTAMP, 'info_requested', %s)
        """, (doctor_id, current_user.user_id, requested_info))
        
        # Add audit log entry
        cursor.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id)
            VALUES (%s, 'additional_info_requested', %s, %s)
        """, (doctor_id, f"Additional information requested: {requested_info}", current_user.user_id))
        
        # Commit transaction
        connection.commit()
        flash("Additional information requested from doctor", "success")
        
    except Exception as e:
        connection.rollback()
        flash(f"Error requesting additional information: {str(e)}", "danger")
    
    finally:
        cursor.close()
        connection.close()
    
    return redirect(url_for('doctor_approvals.index'))
