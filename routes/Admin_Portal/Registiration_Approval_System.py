# registration_approval.py

from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, current_app)
from flask_login import login_required, current_user
from db import get_db_connection
from math import ceil
import datetime # For setting approval/processed dates
import mysql.connector # Specifically for error handling

registration_approval = Blueprint('registration_approval', __name__)

# --- Constants ---
PER_PAGE_REGISTRATIONS = 15
# Allowed sort columns now reflect the new table structure
ALLOWED_REG_SORT_COLUMNS = {
    'date_submitted', 'last_name', 'email', 'specialization', 'status', 'date_processed'
}
# Define allowed statuses if filtering needs to be specific
ALLOWED_STATUS_FILTERS = ['pending', 'approved_user_created', 'rejected', 'info_requested', 'all']

# --- Helper to get Current User ID ---
def get_current_user_id():
    """Safely gets the user ID from Flask-Login's current_user."""
    return getattr(current_user, 'user_id', getattr(current_user, 'id', None))

# --- Routes ---

# List Pending/Processed DOCTOR Registrations
@registration_approval.route('/admin/registrations/doctors', methods=['GET']) # Renamed route slightly for clarity
@login_required
def index():
    # Only admins can access this doctor approval workflow
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Or redirect to admin dashboard if appropriate

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'pending') # Default to pending
    sort_by = request.args.get('sort_by', 'date_submitted').lower()
    if sort_by not in ALLOWED_REG_SORT_COLUMNS: sort_by = 'date_submitted'
    sort_order = request.args.get('sort_order', 'desc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'desc'

    connection = None
    cursor = None
    registrations, stats = [], {}
    total_items, total_pages = 0, 0

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Querying the modified pending_registrations table (which now ONLY contains doctors)
        base_query = """ FROM pending_registrations pr """
        params = []
        where_clauses = [] # No need to filter by user_type='doctor' anymore

        if status_filter != 'all':
            if status_filter in ALLOWED_STATUS_FILTERS:
                 # Make sure the status enum in the DB matches these values
                where_clauses.append("pr.status = %s")
                params.append(status_filter)
            else: # Default back to pending if invalid status given
                status_filter = 'pending'
                where_clauses.append("pr.status = %s")
                params.append(status_filter)

        if search_term:
            # Search relevant doctor pending fields
            where_clauses.append("""(pr.first_name LIKE %s OR pr.last_name LIKE %s OR pr.email LIKE %s
                                   OR pr.username LIKE %s OR pr.specialization LIKE %s OR pr.license_number LIKE %s)""")
            like_term = f"%{search_term}%"
            params.extend([like_term] * 6) # Adjust count based on fields searched

        if where_clauses: base_query += " WHERE " + " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(pr.id) as total {base_query}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_REGISTRATIONS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_REGISTRATIONS

        sort_column = f"pr.{sort_by}"

        # Select columns available in the new pending_registrations table
        data_query = f""" SELECT pr.id, pr.first_name, pr.last_name, pr.email, pr.username,
                                 pr.specialization, pr.license_state, pr.date_submitted, pr.status
                          {base_query} ORDER BY {sort_column} {sort_order}
                          LIMIT %s OFFSET %s """
        final_params = params + [PER_PAGE_REGISTRATIONS, offset]
        cursor.execute(data_query, tuple(final_params)); registrations = cursor.fetchall()

        # Get Stats (counts statuses within the doctor-only pending table)
        cursor.execute(""" SELECT status, COUNT(*) as count FROM pending_registrations
                           GROUP BY status """)
        stats_raw = cursor.fetchall()
        stats = {s['status']: s['count'] for s in stats_raw}
        stats['all'] = sum(stats.values())

    except mysql.connector.Error as db_err:
        flash(f"Database error fetching doctor registrations: {db_err}", "danger")
        current_app.logger.error(f"Database error fetching doctor registrations list: {db_err}")
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error fetching doctor registrations list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Update template path if desired (e.g., Admin_Portal/Registrations/manage_doctor_registrations.html)
    return render_template(
        'Admin_Portal/Registrations/manage_registrations.html',
        registrations=registrations, stats=stats, page=page, total_pages=total_pages,
        per_page=PER_PAGE_REGISTRATIONS, total_items=total_items, search_term=search_term,
        current_status=status_filter, sort_by=sort_by, sort_order=sort_order,
        registration_type='Doctor' # Pass type to template if needed for headings etc.
    )

# View DOCTOR Registration Details
@registration_approval.route('/admin/registrations/doctors/view/<int:reg_id>', methods=['GET']) # Renamed route slightly
@login_required
def view_registration(reg_id):
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    registration = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        # Fetch from the modified pending_registrations table
        # Join users table to get processed_by admin's name
        cursor.execute("""
            SELECT pr.*, CONCAT(u.first_name, ' ', u.last_name) as processed_by_name
            FROM pending_registrations pr
            LEFT JOIN users u ON pr.processed_by = u.user_id
            WHERE pr.id = %s
        """, (reg_id,))
        registration = cursor.fetchone()
        if not registration:
            flash("Doctor registration record not found.", "danger")
            return redirect(url_for('registration_approval.index')) # Redirect back to the doctor list

    except mysql.connector.Error as db_err:
        flash(f"Error fetching doctor registration details: {db_err}", "danger")
        current_app.logger.error(f"Database error fetching doctor registration {reg_id}: {db_err}")
        return redirect(url_for('registration_approval.index'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error fetching doctor registration {reg_id}: {e}")
        return redirect(url_for('registration_approval.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Update template path if desired
    return render_template(
        'Admin_Portal/Registrations/view_registration.html',
        registration=registration,
        registration_type='Doctor' # Pass type to template
    )


# Approve DOCTOR Registration (Step 1: Create User, Link Pending, Rely on Triggers for Role)
@registration_approval.route('/admin/registrations/doctors/approve/<int:reg_id>', methods=['POST']) # Renamed route slightly
@login_required
def approve_registration(reg_id):
    """
    Performs Step 1 of DOCTOR registration approval:
    1. Creates the basic user record (type='doctor', status='inactive', no password).
    2. Relies on database triggers to create corresponding doctors record.
    3. Updates the 'pending_registrations' status and links the new user_id.
    Requires a Step 2 process to set password and activate the account.
    Uses explicit transactions for atomicity.
    """
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin.", "danger")
        return redirect(url_for('registration_approval.index'))

    connection = None
    cursor_dict = None
    cursor_check = None
    cursor_update = None
    new_user_id = None

    try:
        connection = get_db_connection()
        connection.start_transaction()

        # 1. Fetch the pending DOCTOR registration record
        cursor_dict = connection.cursor(dictionary=True)
        # Fetching from the modified pending_registrations table
        cursor_dict.execute("SELECT * FROM pending_registrations WHERE id = %s AND status = 'pending'", (reg_id,))
        reg_data = cursor_dict.fetchone()
        cursor_dict.close()
        cursor_dict = None

        if not reg_data:
            flash("Doctor registration not found or already processed.", "warning")
            connection.rollback()
            if connection and connection.is_connected(): connection.close()
            return redirect(url_for('registration_approval.index'))

        # 2. Check if username/email already exists in the main users table
        cursor_check = connection.cursor()
        # Check using data fetched from pending_registrations
        cursor_check.execute("SELECT user_id FROM users WHERE email = %s OR username = %s",
                             (reg_data['email'], reg_data['username']))
        if cursor_check.fetchone():
            flash(f"Cannot approve: Username '{reg_data['username']}' or Email '{reg_data['email']}' already exists.", "danger")
            connection.rollback()
            cursor_check.close()
            if connection and connection.is_connected(): connection.close()
            # Redirect to view this specific registration
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
        cursor_check.close()
        cursor_check = None

        # --- Transaction continues ---
        cursor_update = connection.cursor()

        # 3. Insert into users table (user_type='doctor', status='inactive', NO password)
        #    Data comes from the pending_registrations table
        cursor_update.execute("""
            INSERT INTO users (username, email, first_name, last_name,
                              user_type, phone, country, account_status, created_at)
            VALUES (%s, %s, %s, %s, 'doctor', %s, %s, 'inactive', %s)
        """, (reg_data['username'], reg_data['email'],
              reg_data['first_name'], reg_data['last_name'],
              reg_data.get('phone'), reg_data.get('country', 'United States'), # Use .get for optional fields
              reg_data['date_submitted']))
        new_user_id = cursor_update.lastrowid

        # 4. Doctor-specific table insertion is handled by SQL TRIGGER 'after_users_insert_doctor'.
        #    It will use the default/placeholder values defined in the trigger initially.
        #    The detailed license info etc. from pending_registrations is NOT automatically transferred by the basic trigger.
        #    Step 2 activation process should potentially update the doctors table with details from pending_registrations.

        # 5. Update pending_registrations: set status, processed_by, and link user_id
        new_pending_status = 'approved_user_created'
        cursor_update.execute("""
            UPDATE pending_registrations
            SET status = %s, user_id = %s, processed_by = %s, date_processed = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_pending_status, new_user_id, current_admin_id, reg_id))

        # 6. Add Audit Log entry for Step 1 DOCTOR approval
        audit_details = f"Doctor user record created (Step 1 approval) for {reg_data['first_name']} {reg_data['last_name']} (Email: {reg_data['email']}). Awaiting activation (Step 2)."
        cursor_update.execute("""
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, 'doctor_registration_step1_approved', %s, %s, 'pending_registrations', %s)
        """, (new_user_id, audit_details, current_admin_id, reg_id))

        # 7. Commit Transaction
        connection.commit()
        flash(f"Doctor user record for {reg_data['first_name']} {reg_data['last_name']}' created (Step 1). Account requires activation (Step 2).", "success")

    except mysql.connector.Error as db_err:
        if connection and connection.in_transaction: connection.rollback()
        # Check specific error: Modify if password_hash column name is different
        if db_err.errno == 1364 and 'password_hash' in db_err.msg: # Or check for 'password' if that's the name
             flash("Database Error: The 'password_hash' column in the 'users' table does not allow NULL values or have a default. Please run 'ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NULL DEFAULT NULL;' on your database.", "danger")
             current_app.logger.error(f"Schema Error during Step 1 approval for registration {reg_id}: {db_err}")
        else:
             flash(f"Database error during Step 1 approval: {db_err}.", "danger")
             current_app.logger.error(f"Database error during Step 1 approval for registration {reg_id}: {db_err}. New User ID (if created): {new_user_id}")
        # Redirect back to the specific registration view on error
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    except Exception as e:
        if connection and connection.in_transaction: connection.rollback()
        flash(f"An unexpected error occurred during Step 1 approval: {str(e)}.", "danger")
        current_app.logger.error(f"Unexpected error during Step 1 approval for registration {reg_id}: {e}. New User ID (if created): {new_user_id}")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    finally:
        # Ensure all cursors are closed
        if cursor_update: cursor_update.close()
        if cursor_check: cursor_check.close()
        if cursor_dict: cursor_dict.close()
        if connection and connection.is_connected(): connection.close()

    # Redirect showing the new status in the doctor list
    return redirect(url_for('registration_approval.index', status=new_pending_status))


# Reject DOCTOR Registration
@registration_approval.route('/admin/registrations/doctors/reject/<int:reg_id>', methods=['POST']) # Renamed route slightly
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

    connection = None
    cursor = None
    cursor_dict = None

    try:
        connection = get_db_connection()
        connection.start_transaction()

        # Fetch username/email for logging before update
        cursor_dict = connection.cursor(dictionary=True)
        cursor_dict.execute("SELECT username, email FROM pending_registrations WHERE id=%s", (reg_id,))
        reg_info = cursor_dict.fetchone()
        cursor_dict.close()
        cursor_dict = None

        # --- Transaction continues ---
        cursor = connection.cursor()

        # Update pending_registrations status and notes
        # Ensure status='pending' to avoid race conditions/double processing
        cursor.execute("""
            UPDATE pending_registrations SET status = 'rejected', processed_by = %s,
                   date_processed = CURRENT_TIMESTAMP, notes = %s
            WHERE id = %s AND status = 'pending'
        """, (current_admin_id, rejection_reason, reg_id))
        updated_rows = cursor.rowcount

        if updated_rows > 0:
            # Add Audit Log entry
            log_details = f"Doctor registration rejected. Reason: {rejection_reason}"
            if reg_info: log_details += f" (User: {reg_info.get('username','N/A')}, Email: {reg_info.get('email','N/A')})"
            cursor.execute("""
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                VALUES (NULL, 'doctor_registration_rejected', %s, %s, 'pending_registrations', %s)
            """, (log_details, current_admin_id, reg_id))

            connection.commit()
            flash("Doctor registration rejected successfully.", "success")
        else:
            connection.rollback() # Rollback if no rows were updated
            flash("Doctor registration not found in 'pending' state or already processed.", "warning")

    except mysql.connector.Error as db_err:
        if connection and connection.in_transaction: connection.rollback()
        flash(f"Database error rejecting doctor registration: {db_err}", "danger")
        current_app.logger.error(f"Database error rejecting doctor registration {reg_id}: {db_err}")
    except Exception as e:
        if connection and connection.in_transaction: connection.rollback()
        flash(f"An unexpected error occurred rejecting doctor registration: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error rejecting doctor registration {reg_id}: {e}")
    finally:
        if cursor_dict: cursor_dict.close()
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Redirect back to the doctor list, showing rejected status
    return redirect(url_for('registration_approval.index', status='rejected'))