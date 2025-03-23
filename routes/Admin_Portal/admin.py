from flask import Blueprint, render_template, request, session, flash, redirect, url_for
from flask_login import login_required, current_user
from db import get_db_connection

admin_main = Blueprint('admin_main', __name__,template_folder='templates')
@admin_main.route('/admin/dashboard', methods=['GET'])
@login_required
def dashboard():
    # Prevent non-admin users from accessing the page
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    
    # Fetch dashboard statistics
    cursor.execute("SELECT COUNT(*) AS total_doctors FROM doctors")
    total_doctors = cursor.fetchone()["total_doctors"]
    
    cursor.execute("SELECT COUNT(*) AS total_patients FROM patients")
    total_patients = cursor.fetchone()["total_patients"]
    
    cursor.execute("SELECT COUNT(*) AS appointments_today FROM appointments WHERE DATE(appointment_date) = CURDATE()")
    appointments_today = cursor.fetchone()["appointments_today"]
    
    cursor.execute("SELECT COUNT(*) AS pending_approvals FROM appointments WHERE status = 'scheduled'")
    pending_approvals = cursor.fetchone()["pending_approvals"]
    
    # Additional statistics
    cursor.execute("SELECT COUNT(*) AS active_users FROM users WHERE account_status = 'active'")
    active_users = cursor.fetchone()["active_users"]
    
    cursor.execute("""
        SELECT user_type, COUNT(*) as count FROM users 
        GROUP BY user_type 
        ORDER BY count DESC
    """)
    user_type_distribution = cursor.fetchall()
    
    # Appointments by status
    cursor.execute("""
        SELECT status, COUNT(*) as count FROM appointments 
        GROUP BY status 
        ORDER BY count DESC
    """)
    appointment_status_stats = cursor.fetchall()
    
    # Appointments by month (for trending)
    cursor.execute("""
        SELECT DATE_FORMAT(appointment_date, '%Y-%m') as month, 
               COUNT(*) as count 
        FROM appointments 
        WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        GROUP BY month 
        ORDER BY month
    """)
    monthly_appointments = cursor.fetchall()
    
    # Fetch recent appointments
    cursor.execute("""
        SELECT a.appointment_id, 
               CONCAT(p_user.first_name, ' ', p_user.last_name) as patient_name, 
               CONCAT(d_user.first_name, ' ', d_user.last_name) as doctor_name,
               a.appointment_date, 
               a.start_time,
               a.appointment_type,
               a.status
        FROM appointments a
        JOIN patients p ON a.patient_id = p.user_id
        JOIN users p_user ON p.user_id = p_user.user_id
        JOIN doctors d ON a.doctor_id = d.user_id
        JOIN users d_user ON d.user_id = d_user.user_id
        ORDER BY a.appointment_date DESC, a.start_time DESC 
        LIMIT 10
    """)
    appointments = cursor.fetchall()
    
    # Get newest users/patients
    cursor.execute("""
        SELECT u.user_id, 
               CONCAT(u.first_name, ' ', u.last_name) as name,
               u.user_type,
               u.created_at
        FROM users u
        ORDER BY u.created_at DESC
        LIMIT 5
    """)
    newest_users = cursor.fetchall()
    
    cursor.close()
    connection.close()
    
    return render_template(
        'Admin_Portal/Dashboard.html',
        total_doctors=total_doctors,
        total_patients=total_patients,
        appointments_today=appointments_today,
        pending_approvals=pending_approvals,
        active_users=active_users,
        user_type_distribution=user_type_distribution,
        appointment_status_stats=appointment_status_stats,
        monthly_appointments=monthly_appointments,
        newest_users=newest_users,
        appointments=appointments
    )