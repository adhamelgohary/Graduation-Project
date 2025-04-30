# registration_approval.py

from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, current_app, jsonify)
from flask_login import login_required, current_user
from db import get_db_connection
from math import ceil
import datetime # For setting approval/processed dates and getting current time
import mysql.connector # Specifically for error handling
import os # For os.path operations (basename, join, getsize, exists)

registration_approval = Blueprint('registration_approval', __name__)

# --- Constants ---
PER_PAGE_REGISTRATIONS = 15
# Added specialization_id to allowed sorts
ALLOWED_REG_SORT_COLUMNS = {
    'date_submitted', 'last_name', 'email', 'username',
    'specialization_id', 'status', 'date_processed', 'user_id'
}
ALLOWED_STATUS_FILTERS = ['pending', 'approved', 'rejected', 'all']

# --- Helper ---
def get_current_user_id():
    """Safely gets the user ID as an integer from Flask-Login's current_user."""
    user_id_str = getattr(current_user, 'id', None)
    user_id_int = None
    if user_id_str is not None:
        try:
            user_id_int = int(user_id_str)
        except (ValueError, TypeError):
            current_app.logger.error(f"Could not convert current_user.id '{user_id_str}' to integer.")
    return user_id_int

# --- Routes ---

# List Pending/Processed DOCTOR Registrations
@registration_approval.route('/admin/registrations/doctors', methods=['GET'])
@login_required
def index():
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'pending').lower()
    sort_by = request.args.get('sort_by', 'date_submitted').lower()
    # Default sort by specialization_id if chosen
    if sort_by == 'specialization': sort_by = 'specialization_id'
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

        # Join with specializations to allow sorting/filtering by name if needed later
        base_query = """
            FROM pending_registrations pr
            LEFT JOIN specializations s ON pr.specialization_id = s.specialization_id
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
            # Search specialization name as well
            where_clauses.append("""(pr.first_name LIKE %s OR pr.last_name LIKE %s OR pr.email LIKE %s
                                   OR pr.username LIKE %s OR s.name LIKE %s OR pr.license_number LIKE %s)""")
            like_term = f"%{search_term}%"
            params.extend([like_term] * 6)

        base_query += " WHERE " + " AND ".join(where_clauses)

        count_query = f"SELECT COUNT(pr.id) as total {base_query}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE_REGISTRATIONS) if total_items > 0 else 0
        offset = (page - 1) * PER_PAGE_REGISTRATIONS

        # Determine actual sort column (handle specialization name if needed)
        sort_column_sql = f"pr.{sort_by}" # Use ID for sorting by default
        # If you wanted to sort by specialization *name*:
        # if sort_by == 'specialization_name': sort_column_sql = 's.name'
        # else: sort_column_sql = f"pr.{sort_by}"

        data_query = f""" SELECT pr.id, pr.first_name, pr.last_name, pr.email, pr.username,
                                 s.name AS specialization_name, -- Fetch name for display
                                 pr.license_number, pr.license_state,
                                 pr.license_expiration, pr.date_submitted, pr.status,
                                 pr.date_processed, pr.user_id
                          {base_query} ORDER BY {sort_column_sql} {sort_order}
                          LIMIT %s OFFSET %s """
        final_params = params + [PER_PAGE_REGISTRATIONS, offset]
        cursor.execute(data_query, tuple(final_params)); registrations = cursor.fetchall()

        # Get Stats
        cursor.execute(""" SELECT status, COUNT(*) as count FROM pending_registrations
                           WHERE user_type_requested = 'doctor' GROUP BY status """)
        stats_raw = cursor.fetchall()
        stats = {status: 0 for status in ALLOWED_STATUS_FILTERS if status != 'all'}
        total_calculated = 0
        for s in stats_raw:
            current_status = s['status']
            if current_status == 'approved_user_created': current_status = 'approved'
            if current_status in stats:
                 stats[current_status] += s['count']
                 total_calculated += s['count']
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
        registrations=registrations, stats=stats, page=page, total_pages=total_pages,
        per_page=PER_PAGE_REGISTRATIONS, total_items=total_items, search_term=search_term,
        current_status=status_filter, sort_by=sort_by, sort_order=sort_order,
        registration_type='Doctor',
        allowed_statuses=ALLOWED_STATUS_FILTERS
    )

# View DOCTOR Registration Details
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

        # Fetch details including document paths and specialization name
        query = """
            SELECT
                pr.*, -- Select all columns from pending_registrations
                s.name as specialization_name, -- Fetch specialization name
                CONCAT(u_proc.first_name, ' ', u_proc.last_name) as processed_by_name,
                u_linked.account_status AS linked_account_status,
                d.verification_status AS doctor_verification_status
            FROM pending_registrations pr
            LEFT JOIN specializations s ON pr.specialization_id = s.specialization_id -- Join for name
            LEFT JOIN users u_proc ON pr.processed_by = u_proc.user_id
            LEFT JOIN users u_linked ON pr.user_id = u_linked.user_id
            LEFT JOIN doctors d ON pr.user_id = d.user_id
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

# Approve DOCTOR Registration
@registration_approval.route('/admin/registrations/doctors/approve/<int:reg_id>', methods=['POST'])
@login_required
def approve_registration(reg_id):
    # --- Authorization and Admin ID Check ---
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))
    current_admin_id = get_current_user_id()
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

    # --- Initialize Variables ---
    connection = None; cursor = None
    new_user_id = None; reg_data = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        connection.start_transaction() # Start transaction
        cursor = connection.cursor(dictionary=True) # Use dictionary cursor initially

        # 1. Lock pending registration, check status, and fetch required data including department_id
        cursor.execute("""
            SELECT pr.*, s.department_id
            FROM pending_registrations pr
            LEFT JOIN specializations s ON pr.specialization_id = s.specialization_id
            WHERE pr.id = %s AND pr.status = 'pending' AND pr.user_type_requested = 'doctor'
            FOR UPDATE
        """, (reg_id,))
        reg_data = cursor.fetchone()

        if not reg_data:
            flash("Doctor registration not found in 'pending' state, or already processed.", "warning")
            connection.rollback()
            return redirect(url_for('registration_approval.index'))

        # --- Transaction continues ---
        # Switch to standard cursor if needed for inserts/updates (though dictionary usually works fine)
        # cursor.close(); cursor = connection.cursor()

        # 2. Check if username/email already exists in the main users table
        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s",
                       (reg_data['email'], reg_data['username']))
        if cursor.fetchone():
            flash(f"Cannot approve: Username '{reg_data['username']}' or Email '{reg_data['email']}' already exists.", "danger")
            connection.rollback()
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

        # 3. Insert into users table (triggers should fire here)
        insert_user_sql = """
            INSERT INTO users (username, email, password, first_name, last_name,
                              user_type, phone, country, account_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'doctor', %s, %s, 'active', %s, %s)
        """
        # Generate a temporary, unusable password hash
        temp_unusable_password_hash = f"needs_reset_{reg_id}_{datetime.datetime.now().timestamp()}" # Or use generate_password_hash("...")
        now_time = datetime.datetime.now()
        user_params = (
            reg_data['username'], reg_data['email'], temp_unusable_password_hash,
            reg_data['first_name'], reg_data['last_name'],
            reg_data.get('phone'), reg_data.get('country', 'United States'),
            now_time, now_time
        )
        cursor.execute(insert_user_sql, user_params)
        new_user_id = cursor.lastrowid
        if not new_user_id:
             connection.rollback(); raise Exception("Failed to get new user ID after insert into users table.")
        current_app.logger.info(f"Created ACTIVE user ID {new_user_id} for registration {reg_id}. Trigger should create doctor record.")

        # 4. UPDATE the DOCTORS table (created by trigger) with specific data from pending_registrations
        update_doctor_sql = """
            UPDATE doctors
            SET verification_status = 'approved',
                specialization_id = %s,          -- Set correct specialization ID
                department_id = %s,              -- Set correct department ID
                license_number = COALESCE(%s, license_number), -- Update if provided
                license_state = COALESCE(%s, license_state),   -- Update if provided
                license_expiration = COALESCE(%s, license_expiration), -- Update if provided
                approval_date = CURRENT_TIMESTAMP, -- Set approval date
                rejection_reason = NULL,           -- Clear rejection reason
                updated_at = CURRENT_TIMESTAMP     -- Update timestamp
            WHERE user_id = %s
        """
        cursor.execute(update_doctor_sql, (
            reg_data.get('specialization_id'), # Use the ID from pending data
            reg_data.get('department_id'),    # Use the department_id fetched via JOIN
            reg_data.get('license_number'),
            reg_data.get('license_state'),
            reg_data.get('license_expiration'),
            new_user_id
        ))
        if cursor.rowcount == 0:
             # This is critical - means the trigger likely failed or the user wasn't found
             connection.rollback()
             current_app.logger.error(f"Failed to find/update doctor record for user_id {new_user_id} during approval of reg {reg_id}. Trigger might have failed or record missing.")
             flash("Critical Error: Could not find or update the corresponding doctor profile record. Approval aborted.", "danger")
             return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
        current_app.logger.info(f"Updated doctors table for user {new_user_id} with specific details and set verification_status='approved'.")

        # 5. INSERT Document Records into doctor_documents
        doc_path_map = {
            # Map pending_registration column name to document_type ENUM value
            'id_document_path': 'identity',
            'license_document_path': 'license',
            'specialization_document_path': 'certification', # Or 'education' based on what it represents
            'other_document_path': 'other'
        }
        insert_doc_sql = """
            INSERT INTO doctor_documents
            (doctor_id, document_type, file_name, file_path, file_size, upload_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        docs_inserted_count = 0
        for path_col, doc_type in doc_path_map.items():
            file_path = reg_data.get(path_col) # Get the relative path from pending_reg
            if file_path:
                file_name = os.path.basename(file_path) # Extract simple filename
                file_size = -1 # Default size if check fails
                upload_date = reg_data.get('date_submitted', now_time) # Use submission date

                try:
                    # Construct full path to check existence and size
                    # IMPORTANT: Assumes file_path is relative to the app's static folder root
                    if not current_app.static_folder:
                        current_app.logger.error("Cannot determine static folder path to check document size.")
                    else:
                        full_file_path = os.path.join(current_app.static_folder, file_path)
                        if os.path.exists(full_file_path):
                            file_size = os.path.getsize(full_file_path)
                        else:
                             current_app.logger.warning(f"Document file for approval not found at {full_file_path} (Reg {reg_id}, Col {path_col}). Cannot get size.")
                except Exception as size_err:
                     current_app.logger.error(f"Error getting size for file {file_path} (Reg {reg_id}): {size_err}")

                try:
                    cursor.execute(insert_doc_sql, (
                        new_user_id,  # The doctor's user_id (same as new_user_id)
                        doc_type,     # The determined document type
                        file_name,    # Extracted filename (could use original if stored)
                        file_path,    # The relative path from pending_reg
                        file_size if file_size >= 0 else 0, # Ensure non-negative size
                        upload_date
                    ))
                    docs_inserted_count += 1
                    current_app.logger.info(f"Inserted document record for user {new_user_id}, type '{doc_type}', path '{file_path}'")
                except mysql.connector.Error as doc_insert_err:
                     # Log error but maybe don't fail the whole approval? Or maybe do? Decide policy.
                     current_app.logger.error(f"Failed to insert document record for user {new_user_id}, type '{doc_type}': {doc_insert_err}")
                     # Optionally re-raise or flash a warning:
                     # flash(f"Warning: Could not save record for document type '{doc_type}'.", "warning")
                     # If failing is desired:
                     # connection.rollback(); raise Exception(f"Failed to insert document record for type '{doc_type}'.")

        current_app.logger.info(f"Inserted {docs_inserted_count} document records for doctor {new_user_id}.")


        # 6. Update pending_registrations status
        new_pending_status = 'approved'
        update_pending_sql = """
            UPDATE pending_registrations
            SET status = %s, user_id = %s, processed_by = %s, date_processed = CURRENT_TIMESTAMP,
                notes = 'Doctor approved and account activated. Password setup required.'
            WHERE id = %s AND status = 'pending'
        """
        cursor.execute(update_pending_sql, (new_pending_status, new_user_id, current_admin_id, reg_id))
        if cursor.rowcount == 0:
             connection.rollback() # Rollback ALL changes if this fails
             current_app.logger.error(f"Failed to update pending registration status for {reg_id} to 'approved' (Concurrency?).")
             raise Exception("Failed to update pending registration status to 'approved'.")

        # 7. Add Audit Log entry
        audit_details = f"Approved doctor registration; User account ACTIVATED (ID: {new_user_id}). Doctor details updated. Documents linked: {docs_inserted_count}. (Reg ID: {reg_id})"
        audit_sql = """
            INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(audit_sql, (new_user_id, 'doctor_registration_approved', audit_details, current_admin_id, 'users', new_user_id))

        # 8. Commit Transaction
        connection.commit()
        current_app.logger.info(f"Successfully approved registration {reg_id}, activated user {new_user_id}, updated pending_reg, added audit log.")
        flash(f"Doctor '{reg_data['username']}' approved and user account activated. Inform doctor to set/reset their password.", "success")
        return redirect(url_for('registration_approval.index', status=new_pending_status)) # Redirect to approved list

    except mysql.connector.Error as db_err:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"Database error during approval: {db_err}.", "danger")
        current_app.logger.error(f"Database error during approval for reg {reg_id}: {db_err}. New User ID (if created): {new_user_id}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    except Exception as e:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"An unexpected error occurred during approval: {str(e)}.", "danger")
        current_app.logger.error(f"Unexpected error during approval for reg {reg_id}: {e}. New User ID (if created): {new_user_id}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()


# Reject DOCTOR Registration
@registration_approval.route('/admin/registrations/doctors/reject/<int:reg_id>', methods=['POST'])
@login_required
def reject_registration(reg_id):
    # --- Authorization and Input Validation ---
    if getattr(current_user, 'user_type', None) != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login_route'))
    rejection_reason = request.form.get('rejection_reason', '').strip()
    current_admin_id = get_current_user_id()
    if not rejection_reason:
        flash("Rejection reason is required.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    if not current_admin_id:
        flash("Could not identify performing admin. Action aborted.", "danger")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

    # --- DB Operation ---
    connection = None; cursor = None; reg_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected(): raise ConnectionError("Database connection failed")
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        # Lock and fetch pending record
        cursor.execute("""
            SELECT id, username, email, status, user_id
            FROM pending_registrations
            WHERE id=%s AND status = 'pending' AND user_type_requested = 'doctor'
            FOR UPDATE
        """, (reg_id,))
        reg_info = cursor.fetchone()

        if not reg_info:
            flash("Registration not found in 'pending' state, or already processed.", "warning")
            connection.rollback()
            return redirect(url_for('registration_approval.index'))

        # --- Transaction continues ---
        # 1. Update pending_registrations status
        update_sql = """
            UPDATE pending_registrations SET status = 'rejected', processed_by = %s,
                   date_processed = CURRENT_TIMESTAMP, notes = %s
            WHERE id = %s AND status = 'pending'
        """
        cursor.execute(update_sql, (current_admin_id, rejection_reason, reg_id))

        if cursor.rowcount > 0:
            # 2. Add Audit Log
            log_details = f"Rejected doctor registration. Reason: {rejection_reason} (Reg ID: {reg_id}, User: {reg_info.get('username','N/A')})"
            audit_sql = """
                INSERT INTO audit_log (user_id, action_type, action_details, performed_by_id, target_table, target_record_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(audit_sql, (None, 'doctor_registration_rejected', log_details, current_admin_id, 'pending_registrations', reg_id))

            # 3. Commit
            connection.commit()
            current_app.logger.info(f"Successfully rejected registration {reg_id}.")
            flash("Doctor registration rejected successfully.", "success")
            return redirect(url_for('registration_approval.index', status='rejected'))
        else:
            # Should not happen if locked correctly, but handle defensively
            connection.rollback()
            flash("Failed to update registration status during rejection.", "danger")
            current_app.logger.error(f"Failed to update registration {reg_id} to rejected state after locking.")
            return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))

    except mysql.connector.Error as db_err:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"Database error rejecting doctor registration: {db_err}", "danger")
        current_app.logger.error(f"Database error rejecting doctor registration {reg_id}: {db_err}")
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    except Exception as e:
        if connection and connection.is_connected(): connection.rollback()
        flash(f"An unexpected error occurred rejecting doctor registration: {str(e)}", "danger")
        current_app.logger.error(f"Unexpected error rejecting doctor registration {reg_id}: {e}", exc_info=True)
        return redirect(url_for('registration_approval.view_registration', reg_id=reg_id))
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()