# Registiration_Approval_System.py

from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, current_app, jsonify)
from flask_login import login_required, current_user
from db import get_db_connection
from math import ceil
import datetime # For setting approval/processed dates and getting current time
import mysql.connector # Specifically for error handling
import os # For os.path operations (basename, join, getsize, exists) - may not be needed now

registration_approval = Blueprint('registration_approval', __name__, template_folder="../templates")

# --- Constants ---
PER_PAGE_REGISTRATIONS = 15
ALLOWED_REG_SORT_COLUMNS = {
    'date_submitted', 'last_name', 'email', 'username',
    'department_id', 'specialization_id', 'status', 'date_processed', 'user_id'
}
ALLOWED_STATUS_FILTERS = ['pending', 'approved', 'rejected', 'all']

# --- Helper ---
def get_current_user_id():
    user_id_str = getattr(current_user, 'id', None)
    user_id_int = None
    if user_id_str is not None:
        try:
            user_id_int = int(user_id_str)
        except (ValueError, TypeError):
            current_app.logger.error(f"Could not convert current_user.id '{user_id_str}' to integer.")
    return user_id_int

# --- Routes ---

@registration_approval.route('/admin/registrations/doctors', methods=['GET'])
@login_required
def index():
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route')) # Replace with your actual login route name

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'pending').lower()
    sort_by = request.args.get('sort_by', 'date_submitted').lower()
    
    if sort_by == 'specialization': sort_by = 'specialization_id'
    if sort_by == 'department': sort_by = 'department_id'

    if sort_by not in ALLOWED_REG_SORT_COLUMNS: sort_by = 'date_submitted'

    sort_order = request.args.get('sort_order', 'desc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'desc'
    if status_filter not in ALLOWED_STATUS_FILTERS: status_filter = 'pending'

    connection = None; cursor = None
    registrations, stats = [], {}
    total_items, total_pages = 0, 0

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        cursor = connection.cursor(dictionary=True)

        base_query_from = """
            FROM pending_registrations pr
            LEFT JOIN specializations s ON pr.specialization_id = s.specialization_id
            LEFT JOIN departments dpt ON pr.department_id = dpt.department_id 
        """
        params = []
        where_clauses = ["pr.user_type_requested = 'doctor'"]

        if status_filter != 'all':
            if status_filter == 'approved':
                 where_clauses.append("pr.status IN ('approved', 'approved_user_created')")
            else:
                 where_clauses.append("pr.status = %s")
                 params.append(status_filter)

        if search_term:
            where_clauses.append("""(
                pr.first_name LIKE %s OR pr.last_name LIKE %s OR pr.email LIKE %s OR
                pr.username LIKE %s OR s.name LIKE %s OR dpt.name LIKE %s OR pr.license_number LIKE %s
            )""")
            like_term = f"%{search_term}%"
            params.extend([like_term] * 7)

        final_where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        count_query = f"SELECT COUNT(pr.id) as total {base_query_from} {final_where_clause}"
        cursor.execute(count_query, tuple(params))
        result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_REGISTRATIONS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_REGISTRATIONS

        sort_column_sql = f"pr.{sort_by}" 

        data_query = f""" SELECT pr.id, pr.first_name, pr.last_name, pr.email, pr.username,
                                 s.name AS specialization_name, 
                                 dpt.name AS department_name,
                                 pr.license_number, pr.license_state,
                                 pr.license_expiration, pr.date_submitted, pr.status,
                                 pr.date_processed, pr.user_id
                                 -- Removed document path columns from select if they were here
                          {base_query_from} {final_where_clause}
                          ORDER BY {sort_column_sql} {sort_order}
                          LIMIT %s OFFSET %s """
        final_data_params = params + [PER_PAGE_REGISTRATIONS, offset]
        cursor.execute(data_query, tuple(final_data_params))
        registrations = cursor.fetchall()

        cursor.execute(""" SELECT status, COUNT(*) as count FROM pending_registrations
                           WHERE user_type_requested = 'doctor' GROUP BY status """)
        stats_raw = cursor.fetchall()
        stats = {status_key: 0 for status_key in ALLOWED_STATUS_FILTERS if status_key != 'all'}
        total_calculated = 0
        for s_item in stats_raw:
            current_status_val = s_item['status']
            display_status = 'approved' if current_status_val == 'approved_user_created' else current_status_val
            if display_status in stats:
                 stats[display_status] += s_item['count']
            total_calculated += s_item['count']
        stats['all'] = total_calculated

    except mysql.connector.Error as db_err:
        flash(f"Database error fetching doctor registrations: {db_err}", "danger")
        current_app.logger.error(f"Database error fetching doctor registrations list: {db_err}")
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error fetching doctor registrations list: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Registrations/manage_registrations.html',
        registrations=registrations,
        stats=stats, page=page, total_pages=total_pages,
        per_page=PER_PAGE_REGISTRATIONS, total_items=total_items, search_term=search_term,
        current_status=status_filter, sort_by=sort_by, sort_order=sort_order,
        registration_type='Doctor',
        allowed_statuses=ALLOWED_STATUS_FILTERS
    )

@registration_approval.route('/admin/registrations/doctors/view/<int:reg_id>', methods=['GET'])
@login_required
def view_registration(reg_id):
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))

    connection = None; cursor = None; registration = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        cursor = connection.cursor(dictionary=True)

        # Ensure you are selecting all necessary fields from pending_registrations
        # Document path columns (e.g., id_document_path) are no longer needed
        query = """
            SELECT
                pr.id, pr.first_name, pr.last_name, pr.email, pr.username,
                pr.phone, pr.country, pr.user_type_requested,
                pr.department_id, dpt.name as department_name,
                pr.specialization_id, s.name as specialization_name,
                pr.license_number, pr.license_state, pr.license_expiration,
                pr.date_submitted, pr.status, pr.notes, pr.date_processed,
                pr.user_id, pr.processed_by,
                CONCAT(u_proc.first_name, ' ', u_proc.last_name) as processed_by_name,
                u_linked.account_status AS linked_account_status,
                doc_profile.verification_status AS doctor_verification_status
            FROM pending_registrations pr
            LEFT JOIN specializations s ON pr.specialization_id = s.specialization_id
            LEFT JOIN departments dpt ON pr.department_id = dpt.department_id
            LEFT JOIN users u_proc ON pr.processed_by = u_proc.user_id
            LEFT JOIN users u_linked ON pr.user_id = u_linked.user_id
            LEFT JOIN doctors doc_profile ON pr.user_id = doc_profile.user_id
            WHERE pr.id = %s AND pr.user_type_requested = 'doctor'
        """
        cursor.execute(query, (reg_id,))
        registration = cursor.fetchone()

        if not registration:
            flash("Doctor registration record not found.", "danger")
            return redirect(url_for('registration_approval.index'))

    except mysql.connector.Error as db_err:
        flash(f"Error fetching doctor registration details: {db_err}", "danger")
        current_app.logger.error(f"Database error fetching doctor registration {reg_id}: {db_err}")
        return redirect(url_for('registration_approval.index'))
    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error fetching doctor registration {reg_id}: {e}", exc_info=True)
        return redirect(url_for('registration_approval.index'))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Registrations/view_registration.html',
        registration=registration,
        registration_type='Doctor'
    )

@registration_approval.route('/admin/registrations/doctors/approve/<int:reg_id>', methods=['POST'])
@login_required
def approve_registration(reg_id):
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied.", "danger"); return redirect(url_for('login.login_route'))

    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    
    connection = None; cursor = None
    new_user_id = None; reg_data = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        
        connection.autocommit = False
        cursor = connection.cursor(dictionary=True)

        # Fetch all necessary fields for creating user and doctor records
        # Document path columns are no longer needed
        cursor.execute("""
            SELECT 
                pr.id, pr.username, pr.email, pr.password, pr.first_name, pr.last_name,
                pr.phone, pr.country, pr.department_id, pr.specialization_id,
                pr.license_number, pr.license_state, pr.license_expiration
            FROM pending_registrations pr
            WHERE pr.id = %s AND pr.status = 'pending' AND pr.user_type_requested = 'doctor'
            FOR UPDATE
        """, (reg_id,))
        reg_data = cursor.fetchone()

        if not reg_data:
            flash("Doctor registration not found in 'pending' state, or already processed.", "warning")
            if connection.is_connected(): connection.rollback()
            return redirect(url_for('registration_approval.index'))

        if not reg_data.get('password'):
            flash("Critical error: Pending registration is missing a password. Cannot approve.", "danger")
            if connection.is_connected(): connection.rollback()
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
        if reg_data.get('department_id') is None:
            flash("Critical error: Pending registration is missing department information. Cannot approve.", "danger")
            if connection.is_connected(): connection.rollback()
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s",
                       (reg_data['email'], reg_data['username']))
        if cursor.fetchone():
             flash(f"Cannot approve: Username '{reg_data['username']}' or Email '{reg_data['email']}' already exists in users table.", "danger")
             if connection.is_connected(): connection.rollback()
             return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

        insert_user_sql = """
            INSERT INTO users (username, email, password, first_name, last_name,
                              user_type, phone, country, account_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'doctor', %s, %s, 'active', %s, %s)
        """
        now_time = datetime.datetime.now()
        user_params = (
            reg_data['username'], reg_data['email'], reg_data['password'], 
            reg_data['first_name'], reg_data['last_name'],
            reg_data.get('phone'), reg_data.get('country', 'United States'),
            now_time, now_time
        )
        cursor.execute(insert_user_sql, user_params)
        new_user_id = cursor.lastrowid
        if not new_user_id:
             if connection.is_connected(): connection.rollback()
             raise Exception("Failed to get new user ID after insert into users table.")
        current_app.logger.info(f"Created ACTIVE user ID {new_user_id} for registration {reg_id}.")

        update_doctor_sql = """
            UPDATE doctors
            SET verification_status = 'approved', 
                specialization_id = %s,
                department_id = %s,
                license_number = COALESCE(%s, license_number),
                license_state = COALESCE(%s, license_state),
                license_expiration = COALESCE(%s, license_expiration),
                approval_date = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        """
        cursor.execute(update_doctor_sql, (
            reg_data.get('specialization_id'),
            reg_data.get('department_id'),
            reg_data.get('license_number'),
            reg_data.get('license_state'),
            reg_data.get('license_expiration'),
            new_user_id
        ))
        if cursor.rowcount == 0:
             if connection.is_connected(): connection.rollback()
             current_app.logger.error(f"Failed to find/update doctor record for user_id {new_user_id} (Reg ID: {reg_id}). Trigger might have failed.")
             flash("Critical Error: Could not find or update the doctor profile. Approval aborted.", "danger")
             return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
        current_app.logger.info(f"Updated doctors table for user {new_user_id} and set verification_status='approved'.")

        # Document insertion logic removed

        new_pending_status = 'approved_user_created'
        update_pending_sql = """
            UPDATE pending_registrations
            SET status = %s, user_id = %s, processed_by = %s, date_processed = CURRENT_TIMESTAMP,
                notes = 'Doctor approved and account activated.' 
            WHERE id = %s AND status = 'pending' 
        """
        cursor.execute(update_pending_sql, (new_pending_status, new_user_id, current_admin_id, reg_id))
        if cursor.rowcount == 0:
             if connection.is_connected(): connection.rollback()
             raise Exception("Failed to update pending registration status to 'approved_user_created'.")

        audit_details = f"Approved doctor registration; User account ACTIVATED (ID: {new_user_id}). Doctor details updated. (Reg ID: {reg_id})"
        audit_sql = """
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(audit_sql, (new_user_id, 'doctor_registration_approved', audit_details, current_admin_id, 'users', new_user_id))

        connection.commit()
        current_app.logger.info(f"Successfully approved registration {reg_id}, activated user {new_user_id}.")
        flash(f"Doctor '{reg_data['username']}' approved and user account activated successfully.", "success")
        return redirect(url_for('registration_approval.index', status='approved'))

    except mysql.connector.Error as db_err:
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"Database error during approval: {db_err}.", "danger")
        current_app.logger.error(f"Database error during approval for reg {reg_id}: {db_err}. New User ID (if created): {new_user_id}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    except Exception as e:
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"An unexpected error occurred during approval: {str(e)}.", "danger")
        current_app.logger.error(f"Unexpected error during approval for reg {reg_id}: {e}. New User ID (if created): {new_user_id}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()

# Reject DOCTOR Registration
@registration_approval.route('/admin/registrations/doctors/reject/<int:reg_id>', methods=['POST'])
@login_required
def reject_registration(reg_id):
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger"); return redirect(url_for('login.login_route'))
    
    rejection_reason = request.form.get('rejection_reason', '').strip()
    current_admin_id = get_current_user_id()

    if not rejection_reason:
        flash("Rejection reason is required.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

    connection = None; cursor = None; reg_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        
        connection.autocommit = False
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, email, status, user_id
            FROM pending_registrations
            WHERE id=%s AND status = 'pending' AND user_type_requested = 'doctor'
            FOR UPDATE
        """, (reg_id,))
        reg_info = cursor.fetchone()

        if not reg_info:
            flash("Registration not found in 'pending' state, or already processed.", "warning")
            if connection.is_connected(): connection.rollback()
            return redirect(url_for('registration_approval.index'))

        update_sql = """
            UPDATE pending_registrations SET status = 'rejected', processed_by = %s,
                   date_processed = CURRENT_TIMESTAMP, notes = %s
            WHERE id = %s AND status = 'pending' 
        """
        cursor.execute(update_sql, (current_admin_id, rejection_reason, reg_id))

        if cursor.rowcount > 0:
            log_details = f"Rejected doctor registration. Reason: {rejection_reason} (Reg ID: {reg_id}, User: {reg_info.get('username','N/A')})"
            audit_sql = """
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(audit_sql, (None, 'doctor_registration_rejected', log_details, current_admin_id, 'pending_registrations', reg_id))
            connection.commit()
            current_app.logger.info(f"Successfully rejected registration {reg_id}.")
            flash("Doctor registration rejected successfully.", "success")
            return redirect(url_for('registration_approval.index', status='rejected'))
        else:
            if connection.is_connected(): connection.rollback()
            flash("Failed to update registration status during rejection (record might have changed).", "danger")
            current_app.logger.error(f"Failed to update registration {reg_id} to rejected state after locking.")
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

    except mysql.connector.Error as db_err:
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"Database error rejecting registration: {db_err}", "danger")
        current_app.logger.error(f"Database error rejecting registration {reg_id}: {db_err}")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    except Exception as e:
        if connection and connection.is_connected() and not connection.autocommit: connection.rollback()
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error rejecting registration {reg_id}: {e}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected():
            if not connection.autocommit: connection.autocommit = True
            connection.close()