# admin_main.py
# No changes needed - all operations were read-only.

from flask import Blueprint, render_template, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection

admin_main = Blueprint('admin_main', __name__)

@admin_main.route('/admin/dashboard', methods=['GET'])
@login_required
def dashboard():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Use your actual login route

    connection = None
    cursor = None
    dashboard_data = { # Initialize with defaults
        'total_doctors': 0, 'total_patients': 0, 'appointments_today': 0,
        'pending_appointment_approvals': 0, # Assuming 'scheduled' appointments
        'active_users': 0,
        'user_type_distribution': [], 'appointment_status_stats': [],
        'monthly_appointments': [], 'appointments': [], 'newest_users': []
        # Add 'pending_doctor_verification': 0 if tracking that
    }

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
             current_app.logger.error(f"DB connection failed in admin dashboard")
             raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)

        # Fetch dashboard statistics (All read-only)
        cursor.execute("SELECT COUNT(user_id) AS count FROM doctors"); result = cursor.fetchone()
        dashboard_data['total_doctors'] = result['count'] if result else 0

        cursor.execute("SELECT COUNT(user_id) AS count FROM patients"); result = cursor.fetchone()
        dashboard_data['total_patients'] = result['count'] if result else 0

        cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE DATE(appointment_date) = CURDATE()"); result = cursor.fetchone()
        dashboard_data['appointments_today'] = result['count'] if result else 0

        cursor.execute("SELECT COUNT(*) AS count FROM appointments WHERE status = 'scheduled'"); result = cursor.fetchone()
        dashboard_data['pending_appointment_approvals'] = result['count'] if result else 0
        # If tracking pending doctor verification:
        # cursor.execute("SELECT COUNT(*) AS count FROM doctors WHERE verification_status = 'pending'"); result = cursor.fetchone()
        # dashboard_data['pending_doctor_verification'] = result['count'] if result else 0

        cursor.execute("SELECT COUNT(*) AS count FROM users WHERE account_status = 'active'"); result = cursor.fetchone()
        dashboard_data['active_users'] = result['count'] if result else 0

        cursor.execute("SELECT user_type, COUNT(*) as count FROM users GROUP BY user_type ORDER BY count DESC")
        dashboard_data['user_type_distribution'] = cursor.fetchall()

        cursor.execute("""SELECT status, COUNT(*) as count FROM appointments GROUP BY status
                          ORDER BY FIELD(status, 'scheduled', 'confirmed', 'completed', 'canceled', 'no-show', 'rescheduled')""")
        dashboard_data['appointment_status_stats'] = cursor.fetchall()

        cursor.execute("""SELECT DATE_FORMAT(appointment_date, '%Y-%m') as month, COUNT(*) as count
                          FROM appointments WHERE appointment_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH) AND appointment_date <= CURDATE()
                          GROUP BY month ORDER BY month""")
        dashboard_data['monthly_appointments'] = cursor.fetchall()

        cursor.execute("""SELECT a.appointment_id, CONCAT(p_user.first_name, ' ', p_user.last_name) as patient_name,
                          CONCAT(d_user.first_name, ' ', d_user.last_name) as doctor_name, a.appointment_date,
                          a.start_time, a.appointment_type, a.status
                          FROM appointments a JOIN patients p ON a.patient_id = p.user_id
                          JOIN users p_user ON p.user_id = p_user.user_id JOIN doctors d ON a.doctor_id = d.user_id
                          JOIN users d_user ON d.user_id = d_user.user_id
                          ORDER BY a.appointment_date DESC, a.start_time DESC LIMIT 10""")
        dashboard_data['appointments'] = cursor.fetchall()

        cursor.execute("""SELECT u.user_id, CONCAT(u.first_name, ' ', u.last_name) as name, u.user_type, u.created_at
                          FROM users u ORDER BY u.created_at DESC LIMIT 5""")
        dashboard_data['newest_users'] = cursor.fetchall()

    except Exception as e:
        flash(f"Error loading dashboard data: {str(e)}", "danger")
        current_app.logger.error(f"Error loading dashboard: {e}")
        # Return template with potentially partial data (or default values)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template('Admin_Portal/Dashboard.html', **dashboard_data)