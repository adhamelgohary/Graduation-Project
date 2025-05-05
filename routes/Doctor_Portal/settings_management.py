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
from datetime import time, date, datetime, timedelta
import logging
import json # Import json for embedding data in template

from .utils import (
    check_doctor_authorization,
    get_provider_id,
    allowed_file,
    generate_secure_filename,
)

# --- Logger ---
# Configure logger if not already configured at app level
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Add basic configuration if needed, adjust level as necessary
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# --- Import necessary getter functions from other modules ---
try:
    from .availability_management import (
        get_all_provider_location_slots,
        get_overrides,
        get_daily_limits,
        get_all_provider_locations
    )
except ImportError:
    logger.error("CRITICAL: Failed to import availability/location functions into settings.", exc_info=True)
    def get_all_provider_location_slots(doctor_id): logger.error("Dummy: get_all_provider_location_slots called."); return []
    def get_overrides(doctor_id, start_date_str=None, end_date_str=None): logger.error("Dummy: get_overrides called."); return []
    def get_daily_limits(provider_id, start_date_str=None, end_date_str=None): logger.error("Dummy: get_daily_limits called."); return []
    def get_all_provider_locations(provider_id): logger.error("Dummy: get_all_provider_locations called."); return []

# --- Import function to get all departments ---
try:
    # Adjust path if home.py is elsewhere relative to the project root
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from routes.Website.home import get_all_departments_from_db
except ImportError as e:
    logger.error(f"Could not import get_all_departments_from_db from Website.home. Error: {e}", exc_info=True)
    def get_all_departments_from_db():
        logger.warning("Using fallback get_all_departments_from_db due to import error.")
        return [] # Return empty list


# --- Helper Functions (Data Fetching) ---

def get_all_specializations_with_departments():
    """Fetches all specializations along with their department ID."""
    specializations = []
    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            # Include department_id in the query
            cursor.execute("""
                SELECT specialization_id, name, department_id
                FROM specializations
                ORDER BY name ASC
            """)
            specializations = cursor.fetchall()
            # Ensure department_id is consistently present, default to None if NULL in DB
            for spec in specializations:
                spec['department_id'] = spec.get('department_id') # Handles DB NULL
        else:
            logger.error('get_all_specializations_with_departments: DB connection failed.')
    except mysql.connector.Error as err:
        logger.error(f"Error fetching specializations with departments: {err}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations

def get_doctor_details(doctor_user_id):
    """Fetches core doctor profile details including department."""
    conn = None; cursor = None; doctor_info = None
    try:
        conn = get_db_connection()
        if conn is None:
            logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id})")
            return None
        cursor = conn.cursor(dictionary=True)
        # Query includes department info now
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
                d.department_id, dep.name AS department_name -- Added department info
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id -- Join departments
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone()

        # Format date for display
        if doctor_info and doctor_info.get('license_expiration') and isinstance(doctor_info['license_expiration'], date):
             doctor_info['license_expiration_str'] = doctor_info['license_expiration'].isoformat()
        # Ensure department_id is present, even if NULL in DB
        if doctor_info:
            doctor_info['department_id'] = doctor_info.get('department_id')

    except mysql.connector.Error as err:
        logger.error(f"DB error fetching doctor details for user_id {doctor_user_id}: {err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching doctor details for user_id {doctor_user_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_info

def get_doctor_documents(doctor_id):
    """Fetches verification/uploaded documents for the doctor."""
    conn = None; cursor = None; documents = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT document_id, document_type, file_name, upload_date, file_path
            FROM doctor_documents
            WHERE doctor_id = %s
            ORDER BY upload_date DESC
        """
        cursor.execute(query, (doctor_id,))
        documents = cursor.fetchall()
        # Format date for display consistency
        for doc in documents:
            if doc.get('upload_date'):
                 # Convert to datetime object if it's not already
                 if isinstance(doc['upload_date'], str):
                      try: doc['upload_date'] = datetime.fromisoformat(doc['upload_date'])
                      except ValueError: doc['upload_date'] = None # Handle parse error
                 elif not isinstance(doc['upload_date'], datetime):
                      doc['upload_date'] = None # Default to None if not datetime or parsable string
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error getting documents for doctor {doctor_id}: {err}")
    except Exception as e:
        logger.error(f"Unexpected error getting documents for doctor {doctor_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return documents

# --- Blueprint Definition ---
settings_bp = Blueprint(
    'settings',
    __name__,
    url_prefix='/doctor/settings',
    template_folder='../../templates' # Adjust if templates are elsewhere
)

# --- Settings Routes ---

@settings_bp.route('/', methods=['GET'])
@login_required
def view_settings():
    """Displays the main settings page, fetching necessary data including all departments/specializations."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login')) # Use your actual login route name

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        flash("Session error. Please log in again.", "danger")
        return redirect(url_for('auth.login'))

    doctor_info = get_doctor_details(doctor_id)
    if not doctor_info:
        flash("Could not load your profile information. Please contact support.", "danger")
        return redirect(url_for('doctor_main.dashboard')) # Use your actual dashboard route name

    # --- Fetch data for profile/docs sections ---
    # Fetch ALL departments and ALL specializations (with their dept_id)
    all_departments = get_all_departments_from_db()
    all_specializations = get_all_specializations_with_departments()
    doctor_documents = get_doctor_documents(doctor_id)

    # --- Fetch Location & Availability Data ---
    provider_locations = []
    all_location_slots = []
    overrides = []
    daily_limits = []
    days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    today = date.today()
    end_range_display = today + timedelta(days=60) # Example range for display

    try:
        provider_locations = get_all_provider_locations(doctor_id)
        all_location_slots = get_all_provider_location_slots(doctor_id)
        overrides = get_overrides(doctor_id, today.isoformat(), end_range_display.isoformat())
        daily_limits = get_daily_limits(doctor_id, today.isoformat(), end_range_display.isoformat())
    except Exception as e:
        logger.error(f"Failed to load location/availability data for settings P:{doctor_id}: {e}", exc_info=True)
        flash("Could not load location or availability details. Some sections may not display correctly.", "warning")

    current_year = datetime.now().year

    # --- Pass all data to the template ---
    return render_template(
        'Doctor_Portal/settings.html', # Verify template path
        doctor_info=doctor_info,
        # NEW: Pass lists for dropdowns
        all_departments=all_departments,
        all_specializations_json=json.dumps(all_specializations), # Pass as JSON for JS
        # Existing data
        provider_locations=provider_locations,
        all_location_slots=all_location_slots,
        overrides=overrides,
        daily_limits=daily_limits,
        days_of_week=days_of_week,
        today_date_iso=today.isoformat(),
        current_year=current_year,
        doctor_documents=doctor_documents
    )


# --- Profile Update Route ---
@settings_bp.route('/profile', methods=['POST'])
@login_required
def update_profile():
    """Handles updates to the doctor's core profile information including department."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Session error.", "danger"); return redirect(url_for('auth.login'))

    conn = None; cursor = None

    # Get Data from form
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip() or None
    specialization_id_str = request.form.get('specialization_id', '').strip()
    department_id_str = request.form.get('department_id', '').strip() # Get department
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

    # --- Validation ---
    errors = []
    if not first_name: errors.append("First name is required.")
    if not last_name: errors.append("Last name is required.")
    if not email: errors.append("Email is required.")
    # Department is optional for profile update? Assume yes.
    # Specialization might depend on department, but basic validation first.
    if not specialization_id_str: errors.append("Specialization is required.")
    if not license_number: errors.append("License number is required.")
    if not license_state: errors.append("License state is required.")
    if not license_expiration_str: errors.append("License expiration date is required.")

    specialization_id = None
    if specialization_id_str:
        try: specialization_id = int(specialization_id_str)
        except ValueError: errors.append("Invalid specialization selected.")

    department_id = None # Allow department to be nullable
    if department_id_str:
        try: department_id = int(department_id_str)
        except ValueError: errors.append("Invalid department selected.")

    license_expiration_date = None
    if license_expiration_str:
        try: license_expiration_date = date.fromisoformat(license_expiration_str)
        except ValueError: errors.append("Invalid license expiration date format (YYYY-MM-DD).")

    graduation_year = None
    if graduation_year_str:
        try:
            graduation_year = int(graduation_year_str)
            if graduation_year < 1900 or graduation_year > datetime.now().year + 1:
                errors.append("Invalid graduation year.")
        except ValueError:
             errors.append("Graduation year must be a number.")

    if npi_number and (len(npi_number) != 10 or not npi_number.isdigit()):
         errors.append("NPI number must be 10 digits.")

    if errors:
        for error in errors: flash(error, 'danger')
        # Redirect back to form, preserving input might need more complex handling
        # or rely on browser cache for simple cases.
        return redirect(url_for('.view_settings') + '#profile')
    # --- End Validation ---

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction()
        cursor = conn.cursor()

        # Update users table
        sql_update_user = "UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s, updated_at = NOW() WHERE user_id = %s"
        cursor.execute(sql_update_user, (first_name, last_name, email, phone, doctor_id))

        # Update doctors table - now includes department_id
        sql_update_doctor = """
            UPDATE doctors SET
                specialization_id = %s, npi_number = %s, license_number = %s,
                license_state = %s, license_expiration = %s, medical_school = %s,
                graduation_year = %s, certifications = %s, biography = %s,
                accepting_new_patients = %s, clinic_address = %s,
                department_id = %s, -- Added department_id
                updated_at = NOW()
            WHERE user_id = %s
        """
        params_doctor = (
            specialization_id, npi_number, license_number, license_state,
            license_expiration_date, medical_school, graduation_year,
            certifications, biography, accepting_new, clinic_address,
            department_id, # Pass department_id (can be None)
            doctor_id
        )
        cursor.execute(sql_update_doctor, params_doctor)

        conn.commit()
        flash("Profile updated successfully.", "success")

    except mysql.connector.Error as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback() # Check for active transaction
        logger.error(f"DB Error updating profile for doctor {doctor_id}: {err}", exc_info=True)
        flash_msg = f"Database error updating profile: {err.msg}" if hasattr(err, 'msg') else "Database error."
        # Check specific error codes
        if err.errno == 1062: flash_msg = "Database error: A unique value conflict occurred (e.g., Email or NPI)."
        elif err.errno == 1452: flash_msg = "Database error: Invalid Specialization or Department selected."
        flash(flash_msg, "danger")
    except ConnectionError as ce:
        logger.error(f"DB Connection Error updating profile D:{doctor_id}: {ce}")
        flash("Database connection error.", "danger")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error updating profile D:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.view_settings') + '#profile')


# --- Password Update Route (No changes needed) ---
@settings_bp.route('/password', methods=['POST'])
@login_required
def update_password():
    # ... (Keep existing password update logic) ...
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)

    conn = None; cursor = None
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    errors = []
    if not all([current_password, new_password, confirm_password]): errors.append("All password fields are required.")
    elif new_password != confirm_password: errors.append("New password and confirmation do not match.")
    elif len(new_password) < 8: errors.append("New password must be at least 8 characters long.")

    if errors:
        for error in errors: flash(error, 'danger')
        return redirect(url_for('.view_settings') + '#security')

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE user_id = %s", (doctor_id,))
        user_data = cursor.fetchone()

        if not user_data or not check_password_hash(user_data.get('password', ''), current_password):
            flash("Incorrect current password.", "danger")
            return redirect(url_for('.view_settings') + '#security')

        new_password_hash = generate_password_hash(new_password)
        cursor.close()
        conn.start_transaction()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = %s, updated_at = NOW() WHERE user_id = %s", (new_password_hash, doctor_id))
        conn.commit()
        flash("Password updated successfully.", "success")
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Error updating password for doctor {doctor_id}: {err}")
        flash("Database error updating password.", "danger")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error updating password for doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.view_settings') + '#security')


# --- Profile Photo Routes (No changes needed) ---
@settings_bp.route('/profile_photo', methods=['POST'])
@login_required
def upload_profile_photo():
    # ... (Keep existing profile photo upload logic) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)
    conn = None; cursor = None; upload_path_full = None; old_photo_path_full = None

    if 'profile_photo' not in request.files or not request.files['profile_photo'].filename:
        flash('No file selected.', 'warning'); return redirect(url_for('.view_settings') + '#photo')
    file = request.files['profile_photo']

    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
    if file and allowed_file(file.filename, allowed_extensions):
        secure_name = generate_secure_filename(file.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER_PROFILE')
        if not upload_folder:
             logger.error("UPLOAD_FOLDER_PROFILE not configured.")
             flash("Server config error: Cannot upload.", "danger"); return redirect(url_for('.view_settings') + '#photo')

        upload_path_full = os.path.join(upload_folder, secure_name)
        # Store relative path for DB/URL generation
        # IMPORTANT: Adjust this db_path if your UPLOAD_FOLDER_PROFILE isn't directly under 'static'
        # Example: if UPLOAD_FOLDER_PROFILE = '/var/www/myapp/static/uploads/profile_pics'
        # and STATIC_URL_PATH = '/static', then db_path should be 'uploads/profile_pics/secure_name'
        # This assumes UPLOAD_FOLDER_PROFILE is configured correctly relative to STATIC_FOLDER
        db_path = os.path.relpath(upload_path_full, current_app.config.get('STATIC_FOLDER', 'static')).replace(os.path.sep, '/')

        try:
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
            doc_data = cursor.fetchone()
            old_photo_path_db = doc_data.get('profile_photo_url') if doc_data else None
            cursor.close()

            os.makedirs(upload_folder, exist_ok=True)
            file.save(upload_path_full)

            conn.start_transaction()
            cursor = conn.cursor()
            # The field name in doctors table seems to be profile_photo_url based on query
            cursor.execute("UPDATE doctors SET profile_photo_url = %s, updated_at = NOW() WHERE user_id = %s", (db_path, doctor_id))
            conn.commit()
            flash('Profile photo updated successfully.', 'success')

            if old_photo_path_db:
                try:
                    base_static_folder = current_app.config.get('STATIC_FOLDER', 'static')
                    # Construct full path based on static folder and DB relative path
                    old_photo_path_full = os.path.join(base_static_folder, old_photo_path_db)
                    # Check if the paths are different before deleting
                    if os.path.exists(old_photo_path_full) and old_photo_path_full != upload_path_full :
                         os.remove(old_photo_path_full)
                         logger.info(f"Deleted old profile photo: {old_photo_path_full}")
                except OSError as e:
                     logger.error(f"Error deleting old photo {old_photo_path_full}: {e}")

        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            logger.error(f"Error uploading photo D:{doctor_id}: {err}", exc_info=True)
            flash('An error occurred uploading photo.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full);
                except OSError: logger.error(f"Failed to cleanup photo on error: {upload_path_full}")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            logger.error(f"Unexpected error uploading photo D:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full);
                except OSError: logger.error(f"Failed to cleanup photo on error: {upload_path_full}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

    return redirect(url_for('.view_settings') + '#photo')


@settings_bp.route('/profile_photo/delete', methods=['POST'])
@login_required
def delete_profile_photo():
    # ... (Keep existing profile photo delete logic, ensure paths are correct) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)
    conn = None; cursor = None; photo_path_full = None

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        # Ensure field name matches DB schema
        cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
        doc_data = cursor.fetchone()
        photo_path_db = doc_data.get('profile_photo_url') if doc_data else None

        if not photo_path_db:
            flash("No profile photo to delete.", "info")
        else:
            cursor.close()
            conn.start_transaction()
            cursor = conn.cursor()
            # Ensure field name matches DB schema
            cursor.execute("UPDATE doctors SET profile_photo_url = NULL, updated_at = NOW() WHERE user_id = %s", (doctor_id,))
            conn.commit()

            message = 'Profile photo removed.'
            flash_category = 'success'
            try:
                base_static_folder = current_app.config.get('STATIC_FOLDER', 'static')
                photo_path_full = os.path.join(base_static_folder, photo_path_db)
                if os.path.exists(photo_path_full):
                    os.remove(photo_path_full)
                    logger.info(f"Deleted profile photo file: {photo_path_full}")
                else:
                    logger.warning(f"Profile photo file not found for deletion: {photo_path_full}")
                    message += ' (File not found on server)'
                    flash_category = 'warning'
            except OSError as e:
                logger.error(f"Error deleting photo file {photo_path_full}: {e}")
                message = 'Photo record updated, but failed to delete the file.'
                flash_category = 'warning'
            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Error removing photo D:{doctor_id}: {err}", exc_info=True)
        flash('Database error removing photo.', 'danger')
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error removing photo D:{doctor_id}: {e}", exc_info=True)
        flash('An unexpected error occurred.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.view_settings') + '#photo')


# --- Document Routes (No changes needed) ---
@settings_bp.route('/documents', methods=['POST'])
@login_required
def upload_document():
    # ... (Keep existing document upload logic) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)
    conn = None; cursor = None; upload_path_full = None

    doc_type = request.form.get('document_type')
    allowed_types = ['license', 'certification', 'identity', 'education', 'other']

    if 'document_file' not in request.files or not request.files['document_file'].filename:
        flash('No file selected.', 'warning'); return redirect(url_for('.view_settings') + '#documents')
    file = request.files['document_file']

    if not doc_type or doc_type not in allowed_types:
         flash(f'Invalid or missing document type.', 'danger'); return redirect(url_for('.view_settings') + '#documents')

    allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'})
    if file and allowed_file(file.filename, allowed_extensions):
        original_filename = secure_filename(file.filename)
        secure_name = generate_secure_filename(original_filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER_DOCS')
        if not upload_folder:
             logger.error("UPLOAD_FOLDER_DOCS not configured.")
             flash("Server config error: Cannot upload document.", "danger"); return redirect(url_for('.view_settings') + '#documents')

        upload_path_full = os.path.join(upload_folder, secure_name)
        # IMPORTANT: Adjust db_path based on UPLOAD_FOLDER_DOCS and STATIC_FOLDER config
        db_path = os.path.relpath(upload_path_full, current_app.config.get('STATIC_FOLDER', 'static')).replace(os.path.sep, '/')

        try:
            os.makedirs(upload_folder, exist_ok=True)
            file.save(upload_path_full)
            file_size = os.path.getsize(upload_path_full)

            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction()
            cursor = conn.cursor()
            query = """ INSERT INTO doctor_documents (doctor_id, document_type, file_name, file_path, file_size, upload_date) VALUES (%s, %s, %s, %s, %s, NOW()) """
            cursor.execute(query, (doctor_id, doc_type, original_filename, db_path, file_size))
            conn.commit()
            flash(f'{doc_type.capitalize()} document uploaded successfully.', 'success')

        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            logger.error(f"Error uploading document D:{doctor_id}: {err}", exc_info=True)
            flash('An error occurred uploading the document.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full);
                except OSError: logger.error(f"Failed to cleanup doc on error: {upload_path_full}")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            logger.error(f"Unexpected error uploading document D:{doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full):
                try: os.remove(upload_path_full);
                except OSError: logger.error(f"Failed to cleanup doc on error: {upload_path_full}")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

    return redirect(url_for('.view_settings') + '#documents')


@settings_bp.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    # ... (Keep existing document delete logic, ensure paths are correct) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)
    conn = None; cursor = None; doc_path_full = None

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT file_path FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
        doc_data = cursor.fetchone()

        if not doc_data:
            flash("Document not found or access denied.", 'warning')
        else:
            doc_path_db = doc_data.get('file_path')
            cursor.close()
            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            conn.commit()

            message = 'Document record deleted.'
            flash_category = 'success'
            if doc_path_db:
                try:
                    # Construct full path based on STATIC_FOLDER and relative DB path
                    base_static_folder = current_app.config.get('STATIC_FOLDER', 'static')
                    doc_path_full = os.path.join(base_static_folder, doc_path_db)

                    if os.path.exists(doc_path_full):
                        os.remove(doc_path_full)
                        logger.info(f"Deleted document file: {doc_path_full}")
                    else:
                         logger.warning(f"Document file not found for deletion: {doc_path_full} (DB path: {doc_path_db})")
                         message += ' (File not found on server)'
                         flash_category = 'warning'
                except OSError as e:
                    logger.error(f"Error deleting document file {doc_path_full}: {e}")
                    message = 'Record deleted, but failed to delete the file.'
                    flash_category = 'warning'
                except Exception as path_e:
                    logger.error(f"Error constructing deletion path for doc {document_id}: {path_e}")
                    message = 'Record deleted, but error occurred trying to locate file.'
                    flash_category='warning'

            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Error deleting document {document_id} D:{doctor_id}: {err}", exc_info=True)
        flash("Database error deleting document.", 'danger')
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error deleting document {document_id} D:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.view_settings') + '#documents')


# --- Securely Serve Uploaded Documents (No changes needed) ---
@settings_bp.route('/documents/view/<path:filename>')
@login_required
def view_uploaded_document(filename):
     # ... (Keep existing document view logic, ensure paths are correct) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: abort(401)

    # Construct expected DB path from filename (assumes structure)
    # Adjust 'uploads/doctor_docs' if your db_path structure is different
    expected_db_path = os.path.join('uploads', 'doctor_docs', filename).replace(os.path.sep, '/')
    conn = None; cursor = None
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT document_id FROM doctor_documents WHERE file_path = %s AND doctor_id = %s", (expected_db_path, doctor_id))
        doc_owner = cursor.fetchone()

        if not doc_owner:
            logger.warning(f"Unauthorized attempt to view document: User {doctor_id}, Path {expected_db_path}")
            flash("You do not have permission to view this document.", "danger")
            return redirect(url_for('.view_settings') + '#documents'), 403

        directory = current_app.config.get('UPLOAD_FOLDER_DOCS')
        if not directory:
             logger.error("UPLOAD_FOLDER_DOCS is not configured.")
             raise ValueError("Upload directory not configured")

        safe_filename = secure_filename(os.path.basename(filename))
        full_path = os.path.join(directory, safe_filename)

        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            logger.error(f"Document file requested but not found at: {full_path} (DB path: {expected_db_path})")
            raise FileNotFoundError("File not found on server.")

        return send_from_directory(directory, safe_filename, as_attachment=False)

    except FileNotFoundError:
        flash("The requested document file could not be found.", "danger")
        return redirect(url_for('.view_settings') + '#documents'), 404
    except (mysql.connector.Error, ConnectionError, ValueError) as err:
         logger.error(f"Error verifying/serving document access F:{filename} D:{doctor_id}: {err}", exc_info=True)
         flash("Error accessing document.", "danger")
         return redirect(url_for('.view_settings') + '#documents'), 500
    except Exception as e:
        logger.error(f"Unexpected error serving document F:{filename} D:{doctor_id}: {e}", exc_info=True)
        flash("Could not serve document due to an unexpected error.", "danger")
        return redirect(url_for('.view_settings') + '#documents'), 500
    finally:
       if cursor: cursor.close()
       if conn and conn.is_connected(): conn.close()