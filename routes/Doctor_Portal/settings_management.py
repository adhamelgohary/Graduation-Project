# routes/Doctor_Portal/settings_management.py
import sys
import mysql.connector
import os
import uuid # Keep for generate_secure_filename if it uses it
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, session, send_from_directory, abort
)
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from db import get_db_connection
from datetime import time, date, datetime, timedelta
import logging
import json

from utils.directory_configs import get_relative_path_for_db

try:
    from .utils import ( # Changed to relative import assuming utils.py is in Doctor_Portal
        check_doctor_authorization,
        get_provider_id,
        allowed_file,
        generate_secure_filename,
    )
except ImportError as e:
    # If utils.py is at the root of 'routes' or in a global 'utils' package, adjust import
    # Example for root 'routes.utils': from ...utils import ...
    # Example for global 'utils': from utils import ...
    # For now, assuming ..utils for routes/Doctor_Portal/utils.py
    logging.getLogger(__name__).error(f"CRITICAL: Settings - Failed to import utils. Details: {e}", exc_info=True)
    def check_doctor_authorization(user): return False
    def get_provider_id(user): return None
    def allowed_file(f, ext_set): return True
    def generate_secure_filename(original_filename): return f"error_{original_filename}"


logger = logging.getLogger(__name__)

try:
    from ..Website.home import get_all_departments_from_db # Adjusted for deeper structure
except ImportError as e:
    logger.error(f"Could not import get_all_departments_from_db. Error: {e}", exc_info=True)
    def get_all_departments_from_db():
        logger.warning("Fallback: get_all_departments_from_db returning empty list.")
        return []


# --- Helper Functions (Data Fetching for Settings) ---
def get_all_specializations_with_departments():
    specializations = []; conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB conn failed for specializations.")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT specialization_id, name, department_id FROM specializations ORDER BY name ASC")
        specializations = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error fetching specializations: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specializations

def get_doctor_details(doctor_user_id):
    conn = None; cursor = None; doctor_info = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError(f"DB conn failed for doctor details (User ID: {doctor_user_id})")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.username, u.email, u.first_name, u.last_name,
                u.phone, u.country, u.account_status,
                d.user_id as doctor_user_id,
                d.specialization_id, s.name AS specialization_name,
                d.license_number, d.license_state, d.license_expiration,
                d.npi_number, d.medical_school, d.graduation_year, d.certifications,
                d.accepting_new_patients, d.biography, d.profile_photo_url,
                d.clinic_address, d.verification_status,
                d.department_id, dep.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone()

        if doctor_info:
            if doctor_info.get('license_expiration') and isinstance(doctor_info['license_expiration'], date):
                 doctor_info['license_expiration_str'] = doctor_info['license_expiration'].isoformat()
        else:
            logger.warning(f"No doctor record found for user_id {doctor_user_id} in get_doctor_details.")
            return None # Important to return None if not found

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB error fetching doctor details user_id {doctor_user_id}: {err}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching doctor details user_id {doctor_user_id}: {e}", exc_info=True)
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_info

def get_doctor_documents(doctor_id_from_users_table):
    conn = None; cursor = None; documents = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for documents.")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT document_id, document_type, file_name, upload_date, file_path, file_size
            FROM doctor_documents
            WHERE doctor_id = %s
            ORDER BY upload_date DESC
        """
        cursor.execute(query, (doctor_id_from_users_table,))
        documents = cursor.fetchall()
        for doc in documents:
            if doc.get('upload_date') and isinstance(doc['upload_date'], datetime):
                 doc['upload_date_str'] = doc['upload_date'].strftime('%Y-%m-%d %H:%M')
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error getting documents for doctor (user_id) {doctor_id_from_users_table}: {err}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting documents for doctor (user_id) {doctor_id_from_users_table}: {e}", exc_info=True)
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return documents

# --- Blueprint Definition ---
# NEW URL PREFIX AND TEMPLATE FOLDER
settings_bp = Blueprint(
    'settings',
    __name__,
    url_prefix='/portal/settings', # Changed from '/Doctor_Portal/Settings' to '/portal/settings' for consistency with other portal BPs
    template_folder='../../templates/Doctor_Portal/Settings' # Path relative to this file (settings_management.py)
)

# --- Settings Main Page / Profile Settings (GET and POST) ---
@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('login.login_route'))

    doctor_id = current_user.id
    if doctor_id is None:
        flash("Session error or provider ID not found. Please log in again.", "danger")
        return redirect(url_for('login.login_route'))

    # Fields that become non-editable once set
    # Store as (form_field_name, db_column_name, friendly_name)
    locked_fields_config = [
        ('npi_number', 'npi_number', 'NPI Number'),
        ('department_id', 'department_id', 'Department'),
        ('specialization_id', 'specialization_id', 'Specialization'),
        ('license_number', 'license_number', 'License Number'),
        ('license_state', 'license_state', 'License State'),
        # License expiration is usually updatable by the doctor
        ('medical_school', 'medical_school', 'Medical School'),
        ('graduation_year', 'graduation_year', 'Graduation Year'),
    ]

    if request.method == 'POST':
        conn = None; cursor = None; operation_successful = False
        try:
            # Fetch current doctor data to compare for locked fields
            current_doctor_data = get_doctor_details(doctor_id)
            if not current_doctor_data:
                flash("Could not retrieve current profile data. Update aborted.", "danger")
                return redirect(url_for('.profile_settings'))

            # Get all form data
            form_data = request.form.to_dict()

            # Initialize values to be updated
            update_values_user = {
                'first_name': form_data.get('first_name', '').strip(),
                'last_name': form_data.get('last_name', '').strip(),
                'email': form_data.get('email', '').strip(),
                'phone': form_data.get('phone', '').strip() or None,
            }
            update_values_doctor = {
                # Fields always updatable
                'certifications': form_data.get('certifications', '').strip() or None,
                'biography': form_data.get('biography', '').strip() or None,
                'accepting_new_patients': form_data.get('accepting_new_patients') == 'on',
                'clinic_address': form_data.get('clinic_address', '').strip() or None,
            }

            # Handle license expiration separately as it's usually updatable
            license_expiration_str = form_data.get('license_expiration', '').strip()
            if license_expiration_str:
                try:
                    update_values_doctor['license_expiration'] = date.fromisoformat(license_expiration_str)
                except ValueError:
                    flash("Invalid license expiration date format (YYYY-MM-DD). Update date only.", 'warning') # Warn but continue
            elif not current_doctor_data.get('license_expiration'): # If not set and not provided
                 flash("License expiration date is required.", 'danger')
                 # Potentially stop here or ensure it's handled in errors list

            # --- Process locked fields ---
            for form_name, db_col, friendly_name in locked_fields_config:
                submitted_value_str = form_data.get(form_name, '').strip()
                current_db_value = current_doctor_data.get(db_col)

                # Convert submitted string to appropriate type for comparison if needed
                submitted_value_typed = None
                if submitted_value_str:
                    if db_col in ['specialization_id', 'department_id', 'graduation_year']:
                        try: submitted_value_typed = int(submitted_value_str)
                        except ValueError:
                            flash(f"Invalid format for {friendly_name}.", "warning")
                            continue # Skip this field if format is bad
                    else:
                        submitted_value_typed = submitted_value_str
                
                # If current value is set (not None, not empty string for text fields)
                is_current_value_set = current_db_value is not None
                if isinstance(current_db_value, str) and not current_db_value.strip():
                    is_current_value_set = False


                if is_current_value_set:
                    # Field is already set, check if user tried to change it
                    # Compare typed values
                    if submitted_value_typed is not None and submitted_value_typed != current_db_value:
                        flash(f"{friendly_name} cannot be changed after being set. Please contact administration if an update is required.", "info")
                    # Keep the existing DB value
                    update_values_doctor[db_col] = current_db_value
                elif submitted_value_typed is not None:
                    # Field was not set, and user is providing a value
                    update_values_doctor[db_col] = submitted_value_typed
                else:
                    # Field was not set, and user did not provide a value (or provided empty)
                    update_values_doctor[db_col] = None # Or handle as required field error if applicable

            # --- Validation (Basic required fields not covered by locked logic) ---
            errors = []
            if not update_values_user['first_name']: errors.append("First name is required.")
            if not update_values_user['last_name']: errors.append("Last name is required.")
            if not update_values_user['email']: errors.append("Email is required.")
            
            # For fields that are newly set but required
            if 'specialization_id' not in update_values_doctor or not update_values_doctor['specialization_id']:
                if not current_doctor_data.get('specialization_id'): errors.append("Specialization is required.")
            if 'license_number' not in update_values_doctor or not update_values_doctor['license_number']:
                 if not current_doctor_data.get('license_number'): errors.append("License number is required.")
            if 'license_state' not in update_values_doctor or not update_values_doctor['license_state']:
                 if not current_doctor_data.get('license_state'): errors.append("License state is required.")
            if 'license_expiration' not in update_values_doctor or not update_values_doctor['license_expiration']:
                 if not current_doctor_data.get('license_expiration'): errors.append("License expiration date is required.")


            if errors:
                for error in errors: flash(error, 'danger')
            else:
                conn = get_db_connection()
                if not conn: raise ConnectionError("DB Connection failed for profile update.")
                if conn.in_transaction: conn.rollback()

                conn.start_transaction()
                cursor = conn.cursor()

                # Update users table
                sql_update_user = "UPDATE users SET first_name=%s, last_name=%s, email=%s, phone=%s, updated_at=NOW() WHERE user_id=%s"
                cursor.execute(sql_update_user, (
                    update_values_user['first_name'], update_values_user['last_name'],
                    update_values_user['email'], update_values_user['phone'], doctor_id
                ))

                # Update doctors table
                # Build the SET part of the query dynamically based on keys in update_values_doctor
                set_clauses_doctor = []
                params_doctor_list = []
                for key, value in update_values_doctor.items():
                    set_clauses_doctor.append(f"{key} = %s")
                    params_doctor_list.append(value)
                
                if set_clauses_doctor: # Only update if there's something to update
                    set_clauses_doctor.append("updated_at = NOW()") # Always update timestamp
                    sql_update_doctor = f"UPDATE doctors SET {', '.join(set_clauses_doctor)} WHERE user_id = %s"
                    params_doctor_list.append(doctor_id)
                    cursor.execute(sql_update_doctor, tuple(params_doctor_list))

                conn.commit()
                operation_successful = True
                flash("Profile updated successfully.", "success")

        except ValueError as ve: # Should be caught by specific field checks now mostly
            flash(str(ve), 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            logger.error(f"DB/Conn Error updating profile P:{doctor_id}: {err}", exc_info=True)
            flash_msg = f"Database error: {err.msg}" if hasattr(err, 'msg') else "Database error."
            if hasattr(err, 'errno'):
                if err.errno == 1062: flash_msg = "Database error: A unique value (e.g., Email or NPI) already exists."
                elif err.errno == 1452: flash_msg = "Database error: Invalid Specialization or Department ID."
            flash(flash_msg, "danger")
        except Exception as e:
            logger.error(f"Unexpected error updating profile P:{doctor_id}: {e}", exc_info=True)
            flash("An unexpected error occurred while updating your profile.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error profile update: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.profile_settings'))

    try:
        doctor_info = get_doctor_details(doctor_id)
        if not doctor_info:
            flash("Could not load your profile details. Please contact support if this persists.", "danger")
            return redirect(url_for('doctor_main.dashboard'))

        all_departments = get_all_departments_from_db()
        all_specializations = get_all_specializations_with_departments()

    except Exception as e:
            logger.error(f"Error loading profile settings page data for P:{doctor_id}: {e}", exc_info=True)
            flash("Could not load profile settings data. Please try again later.", "danger")
            doctor_info = {}
            all_departments = []
            all_specializations = []

    # Pass the list of locked DB column names to the template
    locked_db_cols = [item[1] for item in locked_fields_config]

    return render_template(
        'settings_profile.html',
        active_tab='profile',
        doctor_info=doctor_info,
        all_departments=all_departments,
        all_specializations=all_specializations,
        all_specializations_json=json.dumps(all_specializations),
        current_year=datetime.now().year,
        locked_db_cols=locked_db_cols # Pass this to the template
    )


@settings_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('login.login_route'))
    doctor_id = current_user.id

    if request.method == 'POST':
        conn = None; cursor = None; operation_successful = False
        try:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            errors = []
            if not all([current_password, new_password, confirm_password]): errors.append("All password fields are required.")
            elif new_password != confirm_password: errors.append("New password and confirmation do not match.")
            elif len(new_password) < 8: errors.append("New password must be at least 8 characters long.")

            if errors:
                for error in errors: flash(error, 'danger')
            else:
                conn = get_db_connection()
                if not conn: raise ConnectionError("DB Connection failed for password update.")

                with conn.cursor(dictionary=True) as check_cursor:
                    check_cursor.execute("SELECT password FROM users WHERE user_id = %s", (doctor_id,))
                    user_data = check_cursor.fetchone()

                if not user_data or not check_password_hash(user_data.get('password', ''), current_password):
                    flash("Incorrect current password.", "danger")
                else:
                    if conn.in_transaction: conn.rollback()

                    conn.start_transaction()
                    cursor = conn.cursor()
                    new_password_hash = generate_password_hash(new_password)
                    cursor.execute("UPDATE users SET password = %s, updated_at = NOW() WHERE user_id = %s", (new_password_hash, doctor_id))
                    conn.commit()
                    operation_successful = True
                    flash("Password updated successfully.", "success")

        except (mysql.connector.Error, ConnectionError) as err:
            logger.error(f"DB/Conn Error updating password P:{doctor_id}: {err}", exc_info=True)
            flash("Database error updating password.", "danger")
        except Exception as e:
            logger.error(f"Unexpected error updating password P:{doctor_id}: {e}", exc_info=True)
            flash("An unexpected error occurred while updating password.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error security update: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.security_settings'))

    return render_template('settings_security.html', active_tab='security')


@settings_bp.route('/photo', methods=['GET', 'POST'])
@login_required
def photo_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('login.login_route'))
    doctor_id = current_user.id

    if request.method == 'POST':
        conn = None; cursor = None; operation_successful = False
        saved_file_absolute_path = None
        old_photo_db_path = None

        try:
            if 'profile_photo' not in request.files or not request.files['profile_photo'].filename:
                flash('No file selected.', 'warning')
            else:
                file = request.files['profile_photo']
                allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
                upload_dir_profile_absolute = current_app.config.get('UPLOAD_FOLDER_PROFILE')

                if not upload_dir_profile_absolute:
                     logger.error("UPLOAD_FOLDER_PROFILE not configured in app.config.")
                     flash("Server configuration error: Cannot upload photo.", "danger")
                     raise ValueError("UPLOAD_FOLDER_PROFILE not configured.")

                if file and allowed_file(file.filename, allowed_extensions):
                    secure_file_name = generate_secure_filename(file.filename)
                    saved_file_absolute_path = os.path.join(upload_dir_profile_absolute, secure_file_name)
                    os.makedirs(upload_dir_profile_absolute, exist_ok=True)
                    file.save(saved_file_absolute_path)
                    logger.info(f"Profile photo for P:{doctor_id} saved to: {saved_file_absolute_path}")

                    db_storage_path = get_relative_path_for_db(saved_file_absolute_path)
                    if not db_storage_path:
                        logger.error(f"Could not generate DB storage path for P:{doctor_id}, file: {saved_file_absolute_path}")
                        raise ValueError("Failed to determine database storage path for the photo.")

                    conn = get_db_connection()
                    if not conn: raise ConnectionError("DB Connection failed for photo upload.")

                    with conn.cursor(dictionary=True) as check_cursor:
                        check_cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
                        doc_data = check_cursor.fetchone()
                        old_photo_db_path = doc_data.get('profile_photo_url') if doc_data else None

                    if conn.in_transaction: conn.rollback()

                    conn.start_transaction()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE doctors SET profile_photo_url = %s, updated_at = NOW() WHERE user_id = %s", (db_storage_path, doctor_id))
                    conn.commit()
                    operation_successful = True
                    flash('Profile photo updated successfully.', 'success')

                    if old_photo_db_path and old_photo_db_path != db_storage_path:
                        try:
                            # old_photo_db_path is relative to static folder
                            old_photo_absolute_path_on_disk = os.path.join(current_app.static_folder, old_photo_db_path)
                            if os.path.exists(old_photo_absolute_path_on_disk):
                                 os.remove(old_photo_absolute_path_on_disk)
                                 logger.info(f"Deleted old profile photo file for P:{doctor_id}: {old_photo_absolute_path_on_disk}")
                        except OSError as e_os:
                             logger.error(f"Error deleting old photo file {old_photo_db_path} for P:{doctor_id}: {e_os}")
                else:
                    flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

        except (mysql.connector.Error, ConnectionError, OSError, IOError, ValueError) as err:
            logger.error(f"Error uploading photo P:{doctor_id}: {err}", exc_info=True)
            flash(f'An error occurred uploading photo: {str(err)}', 'danger')
            if saved_file_absolute_path and os.path.exists(saved_file_absolute_path):
                try: os.remove(saved_file_absolute_path)
                except OSError: logger.error(f"Failed to cleanup photo on error for P:{doctor_id}: {saved_file_absolute_path}")
        except Exception as e:
            logger.error(f"Unexpected error uploading photo P:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred during photo upload.', 'danger')
            if saved_file_absolute_path and os.path.exists(saved_file_absolute_path):
                try: os.remove(saved_file_absolute_path)
                except OSError: logger.error(f"Failed to cleanup photo on error for P:{doctor_id}: {saved_file_absolute_path}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error photo upload P:{doctor_id}: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.photo_settings'))

    try:
        doctor_info = get_doctor_details(doctor_id)
        if not doctor_info:
            flash("Could not load profile details.", "danger")
            return redirect(url_for('doctor_main.dashboard'))
    except Exception as e:
        logger.error(f"Error loading photo settings page data P:{doctor_id}: {e}", exc_info=True)
        flash("Error loading page data.", "danger")
        doctor_info = {}

    max_content_length_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 2 * 1024 * 1024)
    max_upload_mb = max_content_length_bytes // (1024 * 1024)

    return render_template('settings_photo.html', active_tab='photo',
                           doctor_info=doctor_info, max_upload_mb=max_upload_mb)


@settings_bp.route('/photo/delete', methods=['POST'])
@login_required
def delete_photo_action():
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id
    conn = None; cursor = None; operation_successful = False
    old_photo_db_path = None

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for photo delete.")

        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
            doc_data = check_cursor.fetchone()
            old_photo_db_path = doc_data.get('profile_photo_url') if doc_data else None

        if not old_photo_db_path:
            flash("No profile photo to delete.", "info")
        else:
            if conn.in_transaction: conn.rollback()

            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("UPDATE doctors SET profile_photo_url = NULL, updated_at = NOW() WHERE user_id = %s", (doctor_id,))
            conn.commit()
            operation_successful = True

            message = 'Profile photo removed successfully from record.'
            flash_category = 'success'
            try:
                # old_photo_db_path is relative to static folder
                old_photo_absolute_path_on_disk = os.path.join(current_app.static_folder, old_photo_db_path)
                if os.path.exists(old_photo_absolute_path_on_disk):
                    os.remove(old_photo_absolute_path_on_disk)
                    logger.info(f"Deleted old profile photo file for P:{doctor_id}: {old_photo_absolute_path_on_disk}")
                else:
                    message += ' (File not found on server for deletion.)'
                    flash_category = 'warning'
                    logger.warning(f"Profile photo file not found for P:{doctor_id}: {old_photo_absolute_path_on_disk}")
            except OSError as e_os:
                message = 'Photo record updated, but failed to delete the image file.'
                flash_category = 'warning'
                logger.error(f"Error deleting photo file {old_photo_absolute_path_on_disk} for P:{doctor_id}: {e_os}")
            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error removing photo P:{doctor_id}: {err}", exc_info=True)
        flash('Database error removing photo.', 'danger')
    except Exception as e:
        logger.error(f"Unexpected error removing photo P:{doctor_id}: {e}", exc_info=True)
        flash('An unexpected error occurred while removing photo.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction and not operation_successful: conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error photo delete P:{doctor_id}: {rb_err}", exc_info=True)
            finally: conn.close()
    return redirect(url_for('.photo_settings'))


@settings_bp.route('/documents', methods=['GET', 'POST'])
@login_required
def documents_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('login.login_route'))
    doctor_id = current_user.id

    if request.method == 'POST':
        conn = None; cursor = None; operation_successful = False
        saved_doc_absolute_path = None
        upload_dir_docs_absolute = current_app.config.get('UPLOAD_FOLDER_DOCS')

        try:
            doc_type = request.form.get('document_type')
            allowed_doc_types_list = ['license', 'certification', 'identity', 'education', 'other']
            if not doc_type or doc_type not in allowed_doc_types_list:
                 flash(f'Invalid or missing document type.', 'danger')
            elif 'document_file' not in request.files or not request.files['document_file'].filename:
                flash('No file selected for document upload.', 'warning')
            else:
                file = request.files['document_file']
                allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS')

                if not upload_dir_docs_absolute:
                     logger.error("UPLOAD_FOLDER_DOCS not configured in app.config.")
                     flash("Server configuration error: Cannot upload document.", "danger")
                     raise ValueError("UPLOAD_FOLDER_DOCS not configured.")

                if file and allowed_file(file.filename, allowed_extensions):
                    original_filename = secure_filename(file.filename)
                    unique_secure_filesystem_name = generate_secure_filename(original_filename)
                    saved_doc_absolute_path = os.path.join(upload_dir_docs_absolute, unique_secure_filesystem_name)
                    os.makedirs(upload_dir_docs_absolute, exist_ok=True)
                    file.save(saved_doc_absolute_path)
                    file_size = os.path.getsize(saved_doc_absolute_path)
                    logger.info(f"Document for P:{doctor_id} saved to: {saved_doc_absolute_path}")

                    db_storage_path = get_relative_path_for_db(saved_doc_absolute_path)
                    if not db_storage_path:
                        logger.error(f"Could not generate DB storage path for P:{doctor_id}, file: {saved_doc_absolute_path}")
                        raise ValueError("Failed to determine database storage path for the document.")

                    conn = get_db_connection()
                    if not conn: raise ConnectionError("DB Connection failed for doc upload.")
                    if conn.in_transaction: conn.rollback()

                    conn.start_transaction()
                    cursor = conn.cursor()
                    query = """ INSERT INTO doctor_documents (doctor_id, document_type, file_name, file_path, file_size, upload_date)
                                VALUES (%s, %s, %s, %s, %s, NOW()) """
                    cursor.execute(query, (doctor_id, doc_type, original_filename, db_storage_path, file_size))
                    conn.commit()
                    operation_successful = True
                    flash(f'{doc_type.capitalize()} document uploaded successfully.', 'success')
                else:
                    flash('Invalid file type for document. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

        except (mysql.connector.Error, ConnectionError, OSError, IOError, ValueError) as err:
            logger.error(f"Error uploading document P:{doctor_id}: {err}", exc_info=True)
            flash(f'An error occurred uploading the document: {str(err)}', 'danger')
            if saved_doc_absolute_path and os.path.exists(saved_doc_absolute_path):
                try: os.remove(saved_doc_absolute_path)
                except OSError: logger.error(f"Failed to cleanup doc on error P:{doctor_id}: {saved_doc_absolute_path}")
        except Exception as e:
            logger.error(f"Unexpected error uploading document P:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred during document upload.', 'danger')
            if saved_doc_absolute_path and os.path.exists(saved_doc_absolute_path):
                try: os.remove(saved_doc_absolute_path)
                except OSError: logger.error(f"Failed to cleanup doc on error P:{doctor_id}: {saved_doc_absolute_path}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error doc upload P:{doctor_id}: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.documents_settings'))

    try:
        doctor_documents = get_doctor_documents(doctor_id)
    except Exception as e:
        logger.error(f"Error loading documents page data P:{doctor_id}: {e}", exc_info=True)
        flash("Error loading documents.", "danger")
        doctor_documents = []

    max_content_length_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024)
    max_upload_mb = max_content_length_bytes // (1024 * 1024)

    return render_template('settings_documents.html', active_tab='documents',
                           doctor_documents=doctor_documents, max_upload_mb=max_upload_mb)


@settings_bp.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document_action(document_id):
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id
    conn = None; cursor = None; operation_successful = False
    old_doc_db_path = None

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for doc delete.")

        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute("SELECT file_path FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            doc_data = check_cursor.fetchone()

        if not doc_data:
            flash("Document not found or access denied.", 'warning')
        else:
            old_doc_db_path = doc_data.get('file_path')
            if conn.in_transaction: conn.rollback()

            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            conn.commit()
            operation_successful = True

            message = 'Document record deleted successfully.'
            flash_category = 'success'
            if old_doc_db_path:
                try:
                    # old_doc_db_path is relative to static folder
                    old_doc_absolute_path_on_disk = os.path.join(current_app.static_folder, old_doc_db_path)
                    if os.path.exists(old_doc_absolute_path_on_disk):
                        os.remove(old_doc_absolute_path_on_disk)
                        logger.info(f"Deleted document file for P:{doctor_id}: {old_doc_absolute_path_on_disk}")
                    else:
                        message += ' (File not found on server for deletion.)'
                        flash_category = 'warning'
                        logger.warning(f"Document file not found for P:{doctor_id}: {old_doc_absolute_path_on_disk}")
                except OSError as e_os:
                    message = 'Document record updated, but failed to delete the file.'
                    flash_category = 'warning'
                    logger.error(f"Error deleting document file {old_doc_absolute_path_on_disk} for P:{doctor_id}: {e_os}")
            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error deleting document {document_id} P:{doctor_id}: {err}", exc_info=True)
        flash("Database error deleting document.", 'danger')
    except Exception as e:
        logger.error(f"Unexpected error deleting document {document_id} P:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while deleting document.", 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction and not operation_successful: conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error doc delete P:{doctor_id}: {rb_err}", exc_info=True)
            finally: conn.close()
    return redirect(url_for('.documents_settings'))


@settings_bp.route('/documents/view/<path:file_path_from_url>')
@login_required
def view_uploaded_document(file_path_from_url): # Changed URL variable name for clarity
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id
    conn = None; cursor = None

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for viewing document.")

        cursor = conn.cursor(dictionary=True)
        query = "SELECT document_id, file_path FROM doctor_documents WHERE doctor_id = %s AND file_path = %s"
        cursor.execute(query, (doctor_id, file_path_from_url))
        doc_data = cursor.fetchone()

        if not doc_data:
            logger.warning(f"Doc access denied or not found: User {doctor_id}, Path {file_path_from_url}")
            flash("Document not found or you do not have permission.", "danger")
            abort(404)

        # file_path_from_url (which is doc_data['file_path']) is relative to current_app.static_folder
        absolute_static_path = current_app.static_folder
        full_file_path_on_disk = os.path.join(absolute_static_path, file_path_from_url)

        if not os.path.exists(full_file_path_on_disk):
            logger.error(f"File not found on disk: {full_file_path_on_disk} (DB path: {file_path_from_url})")
            flash("File not found on server.", "danger")
            abort(404)

        return send_from_directory(directory=absolute_static_path, path=file_path_from_url, as_attachment=False)

    except FileNotFoundError: # Should be caught by os.path.exists now
        logger.error(f"FileNotFound (should be caught by os.path.exists): Path {file_path_from_url}")
        flash("The requested document file could not be found on the server.", "danger")
        abort(404)
    except (mysql.connector.Error, ConnectionError) as err:
         logger.error(f"DB/Conn Error serving doc Path:{file_path_from_url} D:{doctor_id}: {err}", exc_info=True)
         flash("Error accessing document due to a database issue.", "danger")
         abort(500)
    except Exception as e:
        logger.error(f"Unexpected error serving doc Path:{file_path_from_url} D:{doctor_id}: {e}", exc_info=True)
        flash("Could not serve document due to an unexpected error.", "danger")
        abort(500)
    finally:
       if cursor: cursor.close()
       if conn and conn.is_connected(): conn.close()