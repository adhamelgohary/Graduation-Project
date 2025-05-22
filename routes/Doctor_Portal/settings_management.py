# routes/Doctor_Portal/settings_management.py
import sys
import mysql.connector
import os
import uuid
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, session, send_from_directory, abort
)
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from db import get_db_connection
from datetime import time, date, datetime, timedelta # Ensure all are used or remove unused
import logging
import json

# Assuming utils.py is in the same directory or correctly referenced
try:
    from .utils import (
        check_doctor_authorization,
        get_provider_id,
        allowed_file,
        generate_secure_filename,
    )
except ImportError as e:
    logging.getLogger(__name__).error(f"CRITICAL: Settings - Failed to import utils. Details: {e}", exc_info=True)
    def check_doctor_authorization(user): return False
    def get_provider_id(user): return None
    def allowed_file(f, ext): return False
    def generate_secure_filename(f): return "error_filename"

logger = logging.getLogger(__name__)

# --- Import function to get all departments ---
try:
    if 'routes.Website.home' not in sys.modules: # Avoid re-appending if already done
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from routes.Website.home import get_all_departments_from_db
except ImportError as e:
    logger.error(f"Could not import get_all_departments_from_db. Error: {e}", exc_info=True)
    def get_all_departments_from_db():
        logger.warning("Fallback: get_all_departments_from_db.")
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
                d.user_id as doctor_user_id, /* This is redundant if u.user_id is already doctor_id */
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
        else: # Doctor profile not found for the user_id
            logger.warning(f"No doctor record found for user_id {doctor_user_id} in get_doctor_details.")
            return None # Explicitly return None

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB error fetching doctor details user_id {doctor_user_id}: {err}", exc_info=True)
        raise # Re-raise to be caught by calling route
    except Exception as e:
        logger.error(f"Unexpected error fetching doctor details user_id {doctor_user_id}: {e}", exc_info=True)
        raise # Re-raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_info

def get_doctor_documents(doctor_id_from_users_table): # doctor_id here is user_id from users table
    conn = None; cursor = None; documents = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for documents.")
        cursor = conn.cursor(dictionary=True)
        # The doctor_documents table should link to doctors.user_id (which is the FK to users.user_id)
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
settings_bp = Blueprint(
    'settings',
    __name__,
    url_prefix='/portal/settings', # Standardized prefix for all settings
    template_folder='../../templates' # Base template folder
)

# --- Settings Main Page / Profile Settings (GET and POST) ---
@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login_route')) # Use your actual login route
    
    # doctor_id is the user_id for the doctor
    doctor_id = get_provider_id(current_user) # This should be current_user.id if provider_id is just user_id
    if doctor_id is None:
        flash("Session error or provider ID not found. Please log in again.", "danger")
        return redirect(url_for('auth.login_route'))

    if request.method == 'POST':
        # --- UPDATE PROFILE LOGIC ---
        conn = None; cursor = None; operation_successful = False
        try:
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip() or None
            specialization_id_str = request.form.get('specialization_id', '').strip()
            department_id_str = request.form.get('department_id', '').strip()
            npi_number = request.form.get('npi_number', '').strip() or None
            license_number = request.form.get('license_number', '').strip()
            license_state = request.form.get('license_state', '').strip()
            license_expiration_str = request.form.get('license_expiration', '').strip()
            medical_school = request.form.get('medical_school', '').strip() or None
            graduation_year_str = request.form.get('graduation_year', '').strip() or None
            certifications = request.form.get('certifications', '').strip() or None
            biography = request.form.get('biography', '').strip() or None
            accepting_new = request.form.get('accepting_new_patients') == 'on'
            clinic_address = request.form.get('clinic_address', '').strip() or None

            errors = []
            if not first_name: errors.append("First name is required.")
            # ... (all other validations from your original POST route) ...
            if not email: errors.append("Email is required.") # Add more email validation if needed
            if not specialization_id_str: errors.append("Specialization is required.")
            if specialization_id_str:
                try: specialization_id = int(specialization_id_str)
                except ValueError: errors.append("Invalid specialization selected.")
            else: specialization_id = None

            if department_id_str:
                try: department_id = int(department_id_str)
                except ValueError: errors.append("Invalid department selected.")
            else: department_id = None
            
            license_expiration_date = None
            if license_expiration_str:
                try: license_expiration_date = date.fromisoformat(license_expiration_str)
                except ValueError: errors.append("Invalid license expiration date format (YYYY-MM-DD).")

            graduation_year = None
            if graduation_year_str:
                try:
                    graduation_year = int(graduation_year_str)
                    if not (1900 <= graduation_year <= datetime.now().year + 5) : errors.append("Invalid graduation year.")
                except ValueError: errors.append("Graduation year must be a number.")


            if errors:
                for error in errors: flash(error, 'danger')
                # Fall through to render the GET part of the page with errors
            else: # No validation errors, proceed with DB update
                conn = get_db_connection()
                if not conn: raise ConnectionError("DB Connection failed for profile update.")
                if conn.in_transaction:
                    logger.warning(f"Profile update: Conn already in transaction P:{doctor_id}")
                    try: conn.rollback()
                    except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")

                conn.start_transaction()
                cursor = conn.cursor()

                sql_update_user = "UPDATE users SET first_name=%s, last_name=%s, email=%s, phone=%s, updated_at=NOW() WHERE user_id=%s"
                cursor.execute(sql_update_user, (first_name, last_name, email, phone, doctor_id))

                sql_update_doctor = """
                    UPDATE doctors SET specialization_id=%s, npi_number=%s, license_number=%s, license_state=%s,
                    license_expiration=%s, medical_school=%s, graduation_year=%s, certifications=%s,
                    biography=%s, accepting_new_patients=%s, clinic_address=%s, department_id=%s, updated_at=NOW()
                    WHERE user_id=%s
                """
                params_doctor = (specialization_id, npi_number, license_number, license_state, license_expiration_date,
                                 medical_school, graduation_year, certifications, biography, accepting_new,
                                 clinic_address, department_id, doctor_id)
                cursor.execute(sql_update_doctor, params_doctor)
                conn.commit()
                operation_successful = True
                flash("Profile updated successfully.", "success")
                # Update current_user details if they are mutable and session-cached, or force re-login.
                # For simplicity here, we assume basic user details might be updated in session elsewhere if needed.
        
        except ValueError as ve: # Catch specific validation errors if any are raised explicitly
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
                    if conn.in_transaction and not operation_successful:
                        logger.info(f"Profile update: Rolling back transaction P:{doctor_id}")
                        conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error profile update: {rb_err}", exc_info=True)
                finally: conn.close()
        # After POST, always redirect to the GET version of the page to show updated data and clear form
        return redirect(url_for('.profile_settings'))

        # --- RENDER PROFILE PAGE (GET request or after POST error/success) ---
    try:
        doctor_info = get_doctor_details(doctor_id)
        if not doctor_info:
            flash("Could not load your profile. Please contact support.", "danger")
            return redirect(url_for('doctor_main.dashboard')) 
        
        all_departments = get_all_departments_from_db()
        all_specializations = get_all_specializations_with_departments() # This is your Python list of dicts

    except Exception as e:
            logger.error(f"Error loading profile settings page data for P:{doctor_id}: {e}", exc_info=True)
            flash("Could not load profile settings data. Please try again later.", "danger")
            doctor_info = {} 
            all_departments = []
            all_specializations = [] # Pass empty list on error

    return render_template(
        'Doctor_Portal/settings_profile.html', 
        active_tab='profile',
        doctor_info=doctor_info,
        all_departments=all_departments,
        all_specializations=all_specializations,  # <--- Pass the Python list directly
        all_specializations_json=json.dumps(all_specializations), # Keep this for JS
        current_year=datetime.now().year
    )


@settings_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login_route'))
    doctor_id = current_user.id # Assuming current_user.id is the user_id

    if request.method == 'POST':
        # --- UPDATE PASSWORD LOGIC ---
        conn = None; cursor = None; operation_successful = False
        try:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            errors = []
            if not all([current_password, new_password, confirm_password]): errors.append("All password fields are required.")
            elif new_password != confirm_password: errors.append("New password and confirmation do not match.")
            elif len(new_password) < 8: errors.append("New password must be at least 8 characters long.")
            # Add more password complexity rules if needed

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
                    if conn.in_transaction: # Should not be, but defensive
                        logger.warning(f"Security update: Conn already in transaction P:{doctor_id}")
                        try: conn.rollback()
                        except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")
                    
                    conn.start_transaction()
                    cursor = conn.cursor() # New cursor for update
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
                    if conn.in_transaction and not operation_successful:
                        logger.info(f"Security update: Rolling back transaction P:{doctor_id}")
                        conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error security update: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.security_settings'))

    # --- RENDER SECURITY PAGE (GET request) ---
    return render_template('Doctor_Portal/settings_security.html', active_tab='security')


@settings_bp.route('/photo', methods=['GET', 'POST'])
@login_required
def photo_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login_route'))
    doctor_id = current_user.id

    if request.method == 'POST':
        # --- UPLOAD PROFILE PHOTO LOGIC ---
        conn = None; cursor = None; operation_successful = False
        upload_path_full = None; old_photo_path_db = None
        try:
            if 'profile_photo' not in request.files or not request.files['profile_photo'].filename:
                flash('No file selected.', 'warning')
            else:
                file = request.files['profile_photo']
                allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
                upload_folder_profile = current_app.config.get('UPLOAD_FOLDER_PROFILE') # e.g., 'static/uploads/profile_photos'
                static_folder_abs = current_app.static_folder # Absolute path to static folder

                if not upload_folder_profile:
                     logger.error("UPLOAD_FOLDER_PROFILE not configured.")
                     flash("Server configuration error: Cannot upload photo.", "danger")
                elif file and allowed_file(file.filename, allowed_extensions):
                    secure_name = generate_secure_filename(file.filename) # Includes unique prefix
                    
                    # Absolute path for saving the file
                    absolute_upload_dir = os.path.join(static_folder_abs, os.path.dirname(upload_folder_profile.split('static/', 1)[-1]))
                    upload_path_full = os.path.join(absolute_upload_dir, secure_name)
                    
                    # Relative path for storing in DB (relative to static folder)
                    db_path = os.path.join(os.path.dirname(upload_folder_profile.split('static/', 1)[-1]), secure_name).replace(os.path.sep, '/')


                    conn = get_db_connection()
                    if not conn: raise ConnectionError("DB Connection failed for photo upload.")

                    with conn.cursor(dictionary=True) as check_cursor:
                        check_cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
                        doc_data = check_cursor.fetchone()
                        old_photo_path_db = doc_data.get('profile_photo_url') if doc_data else None
                    
                    os.makedirs(absolute_upload_dir, exist_ok=True)
                    file.save(upload_path_full)

                    if conn.in_transaction: # Defensive
                        try: conn.rollback()
                        except: pass
                    
                    conn.start_transaction()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE doctors SET profile_photo_url = %s, updated_at = NOW() WHERE user_id = %s", (db_path, doctor_id))
                    conn.commit()
                    operation_successful = True
                    flash('Profile photo updated successfully.', 'success')

                    if old_photo_path_db and old_photo_path_db != db_path : # Don't delete if it's the same file somehow
                        try:
                            old_photo_path_full_abs = os.path.join(static_folder_abs, old_photo_path_db)
                            if os.path.exists(old_photo_path_full_abs):
                                 os.remove(old_photo_path_full_abs)
                                 logger.info(f"Deleted old profile photo: {old_photo_path_full_abs}")
                        except OSError as e_os:
                             logger.error(f"Error deleting old photo file {old_photo_path_full_abs}: {e_os}")
                else: # File not allowed
                    flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')
        
        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            logger.error(f"Error uploading photo P:{doctor_id}: {err}", exc_info=True)
            flash('An error occurred uploading photo.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup uploaded file on error
                try: os.remove(upload_path_full)
                except OSError: logger.error(f"Failed to cleanup photo on error: {upload_path_full}")
        except Exception as e:
            logger.error(f"Unexpected error uploading photo P:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred during photo upload.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup
                try: os.remove(upload_path_full)
                except OSError: logger.error(f"Failed to cleanup photo on error: {upload_path_full}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error photo upload: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.photo_settings'))

    # --- RENDER PHOTO PAGE (GET request) ---
    try:
        doctor_info = get_doctor_details(doctor_id)
        if not doctor_info:
            flash("Could not load profile details.", "danger")
            return redirect(url_for('doctor_main.dashboard'))
    except Exception as e:
        logger.error(f"Error loading photo settings page data P:{doctor_id}: {e}", exc_info=True)
        flash("Error loading page data.", "danger")
        doctor_info = {} # Avoid template error

    max_content_length_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 2 * 1024 * 1024) # Default 2MB
    max_upload_mb = max_content_length_bytes // (1024 * 1024)

    return render_template('Doctor_Portal/settings_photo.html', active_tab='photo',
                           doctor_info=doctor_info, max_upload_mb=max_upload_mb)


@settings_bp.route('/photo/delete', methods=['POST']) # Action route
@login_required
def delete_photo_action(): # Renamed to avoid conflict if it were a GET view
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id
    conn = None; cursor = None; operation_successful = False
    old_photo_path_db = None
    static_folder_abs = current_app.static_folder
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for photo delete.")

        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
            doc_data = check_cursor.fetchone()
            old_photo_path_db = doc_data.get('profile_photo_url') if doc_data else None

        if not old_photo_path_db:
            flash("No profile photo to delete.", "info")
        else:
            if conn.in_transaction: # Defensive
                try: conn.rollback()
                except: pass
            
            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("UPDATE doctors SET profile_photo_url = NULL, updated_at = NOW() WHERE user_id = %s", (doctor_id,))
            conn.commit()
            operation_successful = True
            
            message = 'Profile photo removed successfully from record.'
            flash_category = 'success'
            try:
                old_photo_path_full_abs = os.path.join(static_folder_abs, old_photo_path_db)
                if os.path.exists(old_photo_path_full_abs):
                    os.remove(old_photo_path_full_abs)
                    logger.info(f"Deleted old profile photo file: {old_photo_path_full_abs}")
                else:
                    message += ' (File not found on server for deletion.)'
                    flash_category = 'warning'
                    logger.warning(f"Profile photo file not found for deletion: {old_photo_path_full_abs}")
            except OSError as e_os:
                message = 'Photo record updated, but failed to delete the image file.'
                flash_category = 'warning'
                logger.error(f"Error deleting photo file {old_photo_path_full_abs}: {e_os}")
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
            except Exception as rb_err: logger.error(f"Rollback error photo delete: {rb_err}", exc_info=True)
            finally: conn.close()
    return redirect(url_for('.photo_settings'))


@settings_bp.route('/documents', methods=['GET', 'POST']) # Combined GET for view, POST for upload
@login_required
def documents_settings():
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login_route'))
    doctor_id = current_user.id

    if request.method == 'POST':
        # --- UPLOAD DOCUMENT LOGIC ---
        conn = None; cursor = None; operation_successful = False
        upload_path_full = None
        static_folder_abs = current_app.static_folder
        upload_folder_docs_config = current_app.config.get('UPLOAD_FOLDER_DOCS') # e.g. 'static/uploads/doctor_docs'

        try:
            doc_type = request.form.get('document_type')
            allowed_doc_types = ['license', 'certification', 'identity', 'education', 'other']
            if not doc_type or doc_type not in allowed_doc_types:
                 flash(f'Invalid or missing document type.', 'danger')
            elif 'document_file' not in request.files or not request.files['document_file'].filename:
                flash('No file selected for document upload.', 'warning')
            else:
                file = request.files['document_file']
                allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'})

                if not upload_folder_docs_config:
                     logger.error("UPLOAD_FOLDER_DOCS not configured.")
                     flash("Server configuration error: Cannot upload document.", "danger")
                elif file and allowed_file(file.filename, allowed_extensions):
                    original_filename = secure_filename(file.filename) # Original name for DB
                    unique_secure_name = generate_secure_filename(original_filename) # Secure name for filesystem

                    # Path relative to static folder (for DB)
                    # e.g. if UPLOAD_FOLDER_DOCS is 'static/uploads/docs', then db_path_segment = 'uploads/docs'
                    db_path_segment = upload_folder_docs_config.split('static/', 1)[-1] if 'static/' in upload_folder_docs_config else upload_folder_docs_config
                    db_path = os.path.join(db_path_segment, unique_secure_name).replace(os.path.sep, '/')

                    # Absolute path for saving file
                    absolute_upload_dir = os.path.join(static_folder_abs, db_path_segment)
                    upload_path_full = os.path.join(absolute_upload_dir, unique_secure_name)
                    
                    os.makedirs(absolute_upload_dir, exist_ok=True)
                    file.save(upload_path_full)
                    file_size = os.path.getsize(upload_path_full)

                    conn = get_db_connection()
                    if not conn: raise ConnectionError("DB Connection failed for doc upload.")
                    if conn.in_transaction: # Defensive
                        try: conn.rollback()
                        except: pass
                    
                    conn.start_transaction()
                    cursor = conn.cursor()
                    query = """ INSERT INTO doctor_documents (doctor_id, document_type, file_name, file_path, file_size, upload_date) 
                                VALUES (%s, %s, %s, %s, %s, NOW()) """
                    cursor.execute(query, (doctor_id, doc_type, original_filename, db_path, file_size))
                    conn.commit()
                    operation_successful = True
                    flash(f'{doc_type.capitalize()} document uploaded successfully.', 'success')
                else: # File not allowed
                    flash('Invalid file type for document. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')
        
        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            logger.error(f"Error uploading document P:{doctor_id}: {err}", exc_info=True)
            flash('An error occurred uploading the document.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full)
                except OSError: logger.error(f"Failed to cleanup doc on error: {upload_path_full}")
        except Exception as e:
            logger.error(f"Unexpected error uploading document P:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred during document upload.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full)
                except OSError: logger.error(f"Failed to cleanup doc on error: {upload_path_full}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected():
                try:
                    if conn.in_transaction and not operation_successful: conn.rollback()
                except Exception as rb_err: logger.error(f"Rollback error doc upload: {rb_err}", exc_info=True)
                finally: conn.close()
        return redirect(url_for('.documents_settings'))

    # --- RENDER DOCUMENTS PAGE (GET request) ---
    try:
        doctor_documents = get_doctor_documents(doctor_id)
    except Exception as e:
        logger.error(f"Error loading documents page data P:{doctor_id}: {e}", exc_info=True)
        flash("Error loading documents.", "danger")
        doctor_documents = []

    max_content_length_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024) # Default 5MB for docs
    max_upload_mb = max_content_length_bytes // (1024 * 1024)

    return render_template('Doctor_Portal/settings_documents.html', active_tab='documents',
                           doctor_documents=doctor_documents, max_upload_mb=max_upload_mb)


@settings_bp.route('/documents/<int:document_id>/delete', methods=['POST']) # Action route
@login_required
def delete_document_action(document_id): # Renamed to avoid conflict
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id
    conn = None; cursor = None; operation_successful = False
    old_doc_path_db = None
    static_folder_abs = current_app.static_folder
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for doc delete.")

        with conn.cursor(dictionary=True) as check_cursor:
            check_cursor.execute("SELECT file_path FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            doc_data = check_cursor.fetchone()
        
        if not doc_data:
            flash("Document not found or access denied.", 'warning')
        else:
            old_doc_path_db = doc_data.get('file_path')
            if conn.in_transaction: # Defensive
                try: conn.rollback()
                except: pass
            
            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            conn.commit()
            operation_successful = True
            
            message = 'Document record deleted successfully.'
            flash_category = 'success'
            if old_doc_path_db:
                try:
                    old_doc_path_full_abs = os.path.join(static_folder_abs, old_doc_path_db)
                    if os.path.exists(old_doc_path_full_abs):
                        os.remove(old_doc_path_full_abs)
                        logger.info(f"Deleted document file: {old_doc_path_full_abs}")
                    else:
                        message += ' (File not found on server for deletion.)'
                        flash_category = 'warning'
                        logger.warning(f"Document file not found for deletion: {old_doc_path_full_abs}")
                except OSError as e_os:
                    message = 'Document record updated, but failed to delete the file.'
                    flash_category = 'warning'
                    logger.error(f"Error deleting document file {old_doc_path_full_abs}: {e_os}")
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
            except Exception as rb_err: logger.error(f"Rollback error doc delete: {rb_err}", exc_info=True)
            finally: conn.close()
    return redirect(url_for('.documents_settings'))


@settings_bp.route('/documents/file/<path:filename>') # Securely serve verified files
@login_required
def view_uploaded_document(filename):
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = current_user.id # Assuming doctor_id for documents table is user_id

    # Filename from URL is just the base name. We need to find the full DB path.
    # This is tricky if multiple docs have same filename but different paths/types.
    # A better approach would be to serve by document_id, then lookup filename.
    # For now, assuming filename is unique enough or we find the first match.
    
    # Construct the relative path part that UPLOAD_FOLDER_DOCS contributes
    upload_folder_docs_config = current_app.config.get('UPLOAD_FOLDER_DOCS', 'static/uploads/doctor_docs')
    db_path_segment = upload_folder_docs_config.split('static/', 1)[-1] if 'static/' in upload_folder_docs_config else upload_folder_docs_config
    
    # The filename from the URL is the base filename (e.g., "license.pdf")
    # The path stored in DB is like "uploads/doctor_docs/unique_prefix_license.pdf"
    # We need to query the DB for a record matching doctor_id and where file_path ENDS WITH filename
    # or, if you stored original_filename, query by that.
    # Assuming generate_secure_filename prepends a UUID, the filename in URL might be the original.
    # Let's assume filename in URL is the original_filename stored in DB.

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for viewing document.")
        
        cursor = conn.cursor(dictionary=True)
        # Query for a document belonging to the doctor that has the given original filename.
        # If multiple exist, this fetches one. You might need a more specific way if filenames aren't unique per doctor.
        query = "SELECT file_path FROM doctor_documents WHERE doctor_id = %s AND file_name = %s ORDER BY upload_date DESC LIMIT 1"
        cursor.execute(query, (doctor_id, filename))
        doc_data = cursor.fetchone()

        if not doc_data or not doc_data.get('file_path'):
            logger.warning(f"Doc access denied or not found: User {doctor_id}, Original Filename {filename}")
            flash("Document not found or you do not have permission.", "danger")
            return redirect(url_for('.documents_settings')), 404

        # doc_data['file_path'] is like "uploads/doctor_docs/securename.pdf"
        # We need the directory part and the actual secure filename part
        path_parts = doc_data['file_path'].split('/')
        actual_secure_filename = path_parts[-1]
        # The directory for send_from_directory should be the absolute path to the folder containing the file.
        # This is current_app.static_folder + os.path.join(*path_parts[:-1])
        
        file_dir_relative_to_static = os.path.join(*path_parts[:-1])
        absolute_file_directory = os.path.join(current_app.static_folder, file_dir_relative_to_static)

        if not os.path.exists(os.path.join(absolute_file_directory, actual_secure_filename)):
            logger.error(f"File not found on disk: {os.path.join(absolute_file_directory, actual_secure_filename)}")
            flash("File not found on server.", "danger")
            return redirect(url_for('.documents_settings')), 404

        return send_from_directory(absolute_file_directory, actual_secure_filename, as_attachment=False)

    except FileNotFoundError: # Should be caught by os.path.exists now
        flash("The requested document file could not be found on the server.", "danger")
        return redirect(url_for('.documents_settings')), 404
    except (mysql.connector.Error, ConnectionError) as err:
         logger.error(f"DB/Conn Error serving doc F:{filename} D:{doctor_id}: {err}", exc_info=True)
         flash("Error accessing document due to a database issue.", "danger")
         return redirect(url_for('.documents_settings')), 500
    except Exception as e:
        logger.error(f"Unexpected error serving doc F:{filename} D:{doctor_id}: {e}", exc_info=True)
        flash("Could not serve document due to an unexpected error.", "danger")
        return redirect(url_for('.documents_settings')), 500
    finally:
       if cursor: cursor.close()
       if conn and conn.is_connected(): conn.close()