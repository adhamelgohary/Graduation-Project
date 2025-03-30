# registration_approval.py

from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, current_app)
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash # Only needed if regenerating hash on approval? Usually not.
from db import get_db_connection
from math import ceil
import datetime # For setting approval/processed dates

registration_approval = Blueprint('registration_approval', __name__)

# --- Constants ---
PER_PAGE_REGISTRATIONS = 15
ALLOWED_REG_SORT_COLUMNS = {
    'date_submitted', 'last_name', 'email', 'user_type', 'status', 'date_processed'
}

# --- Helper to get Current User ID ---
def get_current_user_id():
    """Safely gets the user ID from Flask-Login's current_user."""
    return getattr(current_user, 'user_id', getattr(current_user, 'id', None))

# --- Routes ---

# List Pending/Processed Registrations
@registration_approval.route('/admin/registrations', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'pending') # Default to pending
    sort_by = request.args.get('sort_by', 'date_submitted').lower()
    if sort_by not in ALLOWED_REG_SORT_COLUMNS: sort_by = 'date_submitted'
    sort_order = request.args.get('sort_order', 'desc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'desc'

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    registrations, stats = [], {}
    total_items, total_pages = 0, 0

    try:
        base_query = """ FROM pending_registrations pr """
        params = []
        where_clauses = []

        if status_filter != 'all':
            valid_statuses = ['pending', 'approved', 'rejected']
            if status_filter in valid_statuses:
                where_clauses.append("pr.status = %s")
                params.append(status_filter)
            else: # Default back to pending if invalid status given
                status_filter = 'pending'
                where_clauses.append("pr.status = %s")
                params.append(status_filter)

        if search_term:
            where_clauses.append("""(pr.first_name LIKE %s OR pr.last_name LIKE %s OR pr.email LIKE %s
                                   OR pr.username LIKE %s OR pr.user_type LIKE %s)""")
            like_term = f"%{search_term}%"; params.extend([like_term] * 5)

        if where_clauses: base_query += " WHERE " + " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(pr.id) as total {base_query}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_REGISTRATIONS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_REGISTRATIONS

        # Note: Sorting happens directly on pending_registrations columns
        sort_column = f"pr.{sort_by}" # Assuming column names match ALLOWED_REG_SORT_COLUMNS

        data_query = f""" SELECT pr.id, pr.first_name, pr.last_name, pr.email, pr.user_type,
                                 pr.date_submitted, pr.status
                          {base_query} ORDER BY {sort_column} {sort_order}
                          LIMIT %s OFFSET %s """
        final_params = params + [PER_PAGE_REGISTRATIONS, offset]
        cursor.execute(data_query, tuple(final_params)); registrations = cursor.fetchall()

        # Get Stats
        cursor.execute(""" SELECT status, COUNT(*) as count FROM pending_registrations
                           GROUP BY status """)
        stats_raw = cursor.fetchall()
        stats = {s['status']: s['count'] for s in stats_raw}
        stats['all'] = sum(stats.values())

    except Exception as e:
        flash(f"Database error fetching registrations: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching registrations list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Registrations/manage_registrations.html', # Adjust template path
        registrations=registrations, stats=stats, page=page, total_pages=total_pages,
        per_page=PER_PAGE_REGISTRATIONS, total_items=total_items, search_term=search_term,
        current_status=status_filter, sort_by=sort_by, sort_order=sort_order
    )

# View Registration Details
@registration_approval.route('/admin/registrations/view/<int:reg_id>', methods=['GET'])
@login_required
def view_registration(reg_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    registration = None
    try:
        # Fetch registration and processing admin's name if available
        cursor.execute("""
            SELECT pr.*, CONCAT(u.first_name, ' ', u.last_name) as processed_by_name
            FROM pending_registrations pr
            LEFT JOIN users u ON pr.processed_by = u.user_id
            WHERE pr.id = %s
        """, (reg_id,))
        registration = cursor.fetchone()
        if not registration:
            flash("Registration record not found.", "danger")
            return redirect(url_for('registration_approval.index'))

    except Exception as e:
        flash(f"Error fetching registration details: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching registration {reg_id}: {e}")
        return redirect(url_for('registration_approval.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Registrations/view_registration.html', # Adjust template path
        registration=registration
    )


# Approve Registration
@registration_approval.route('/admin/registrations/approve/<int:reg_id>', methods=['POST'])
@login_required
def approve_registration(reg_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(url_for('registration_approval.index'))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True) # Need dictionary for fetching pending data
    new_user_id = None # To store the ID of the created user

    try:
        # 1. Fetch the pending registration record
        cursor.execute("SELECT * FROM pending_registrations WHERE id = %s AND status = 'pending'", (reg_id,))
        reg_data = cursor.fetchone()

        if not reg_data:
            flash("Registration not found or already processed.", "warning")
            return redirect(url_for('registration_approval.index'))

        # 2. Check if username/email already exists in the main users table
        cursor_check = connection.cursor() # Use standard cursor for existence check
        cursor_check.execute("SELECT user_id FROM users WHERE email = %s OR username = %s",
                             (reg_data['email'], reg_data['username']))
        if cursor_check.fetchone():
            flash(f"Cannot approve: Username '{reg_data['username']}' or Email '{reg_data['email']}' already exists in the system.", "danger")
            # Optionally, update pending status to rejected here?
            # cursor_check.execute("UPDATE pending_registrations SET status='rejected', notes='Conflict: Username/Email exists' WHERE id = %s", (reg_id,))
            # connection.commit()
            cursor_check.close()
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
        cursor_check.close()


        # 3. Start Transaction
        connection.start_transaction()
        cursor_update = connection.cursor() # Standard cursor for inserts/updates

        # 4. Insert into users table
        # Note: password_hash comes directly from pending_registrations
        cursor_update.execute("""
            INSERT INTO users (username, email, password_hash, first_name, last_name,
                              user_type, phone, country, account_status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
        """, (reg_data['username'], reg_data['email'], reg_data['password_hash'],
              reg_data['first_name'], reg_data['last_name'], reg_data['user_type'],
              reg_data['phone'], reg_data['country'], reg_data['date_submitted']))
        new_user_id = cursor_update.lastrowid

        # 5. Insert into role-specific table (patients, doctors, admins)
        user_type = reg_data['user_type']
        if user_type == 'patient':
            # Make sure required patient fields have defaults or are nullable in schema if not collected at registration
            cursor_update.execute("""
                INSERT INTO patients (user_id, date_of_birth, gender, insurance_provider_id,
                                   insurance_policy_number, insurance_group_number)
                VALUES (%s, %s, %s, NULL, %s, %s)
            """, (new_user_id, reg_data.get('date_of_birth'), reg_data.get('gender', 'unknown'), # Default gender if needed
                  reg_data.get('insurance_policy_number'), reg_data.get('insurance_group_number')))
             # NOTE: Insurance provider needs mapping from name (if collected) to ID, or collect ID. Assuming NULL for now.
        elif user_type == 'doctor':
            # Set default verification status for doctors created via approval
            cursor_update.execute("""
                INSERT INTO doctors (user_id, specialization, license_number, license_state,
                                  license_expiration, verification_status, approval_date)
                VALUES (%s, %s, %s, %s, %s, 'approved', CURRENT_TIMESTAMP)
            """, (new_user_id, reg_data.get('specialization'), reg_data.get('license_number'),
                  reg_data.get('license_state'), reg_data.get('license_expiration')))
        elif user_type == 'admin':
            cursor_update.execute("INSERT INTO admins (user_id, admin_level) VALUES (%s, 'regular')", (new_user_id,)) # Default level
        # Add elif for 'nutritionist' if applicable

        # 6. Update pending_registrations status
        cursor_update.execute("""
            UPDATE pending_registrations SET status = 'approved', processed_by = %s, date_processed = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (current_admin_id, reg_id))

        # 7. Add Audit Log entry
        cursor_update.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, 'registration_approved', 'User registration approved from pending list', %s, 'pending_registrations', %s)
        """, (new_user_id, current_admin_id, reg_id)) # Log against the new user ID

        # 8. Commit Transaction
        connection.commit()
        flash(f"Registration for {reg_data['user_type']} '{reg_data['first_name']} {reg_data['last_name']}' approved successfully.", "success")
        # Maybe send welcome email here?

    except Exception as e:
        if connection.is_connected() and connection.in_transaction: connection.rollback()
        flash(f"Error approving registration: {str(e)}", "danger")
        current_app.logger.error(f"Error approving registration {reg_id}: {e}")
    finally:
        # Ensure all cursors are closed
        if 'cursor_update' in locals() and cursor_update: cursor_update.close()
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('registration_approval.index', status='approved'))


# Reject Registration
@registration_approval.route('/admin/registrations/reject/<int:reg_id>', methods=['POST'])
@login_required
def reject_registration(reg_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    rejection_reason = request.form.get('rejection_reason', '').strip()
    current_admin_id = get_current_user_id()

    if not rejection_reason:
        flash("Rejection reason is required.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(url_for('registration_approval.index'))

    connection = get_db_connection()
    cursor = connection.cursor() # Standard cursor for update

    try:
        # Fetch username/email for logging before update
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT username, email FROM pending_registrations WHERE id=%s", (reg_id,))
        reg_info = cursor_dict.fetchone()
        cursor_dict.close()

        connection.start_transaction()

        # Update pending_registrations status and notes
        cursor.execute("""
            UPDATE pending_registrations SET status = 'rejected', processed_by = %s,
                   date_processed = CURRENT_TIMESTAMP, notes = %s
            WHERE id = %s AND status = 'pending'
        """, (current_admin_id, rejection_reason, reg_id))
        updated_rows = cursor.rowcount

        if updated_rows > 0:
            # Add Audit Log entry
            log_details = f"Registration rejected. Reason: {rejection_reason}"
            if reg_info: log_details += f" (User: {reg_info.get('username','N/A')}, Email: {reg_info.get('email','N/A')})"
            cursor.execute("""
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                VALUES (NULL, 'registration_rejected', %s, %s, 'pending_registrations', %s)
            """, (log_details, current_admin_id, reg_id)) # user_id is NULL as no user was created

            connection.commit()
            flash("Registration rejected successfully.", "success")
        else:
            connection.rollback()
            flash("Registration not found in 'pending' state or already processed.", "warning")


    except Exception as e:
        if connection.is_connected() and connection.in_transaction: connection.rollback()
        flash(f"Error rejecting registration: {str(e)}", "danger")
        current_app.logger.error(f"Error rejecting registration {reg_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('registration_approval.index', status='rejected'))