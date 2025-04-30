# routes/Doctor_Portal/settings_management.py

import mysql.connector
import os
import uuid
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, session, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from db import get_db_connection
from datetime import time, date, datetime, timedelta

# --- Helper Functions ---

def check_doctor_authorization(user):
    """Checks if the logged-in user is authenticated and is a doctor."""
    if not user or not user.is_authenticated: return False
    return getattr(user, 'user_type', None) == 'doctor'

# *** Import or define get_specializations ***
# Option 1: Import if it's in a shared utility file
# from ..utils import get_specializations # Example path

# Option 2: Define it here or copy from register.py if needed only here
def get_specializations():
    """Fetches active specializations for the dropdown."""
    specializations = []
    connection = None; cursor = None
    try:
        connection = get_db_connection()
        if connection and connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            # Select ID and Name, order by Name
            cursor.execute("SELECT specialization_id, name FROM specializations ORDER BY name ASC")
            specializations = cursor.fetchall()
        else: current_app.logger.error('get_specializations: DB connection failed.')
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching specializations: {err}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return specializations
# --- End get_specializations definition ---


def get_doctor_details(doctor_user_id):
    """Fetches comprehensive doctor details for the settings page."""
    conn = None; cursor = None; doctor_info = None
    try:
        conn = get_db_connection()
        if conn is None:
            current_app.logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id})")
            return None
        cursor = conn.cursor(dictionary=True)
        # *** QUERY UPDATED (Same as Dashboard.py) ***
        query = """
            SELECT
                u.user_id, u.username, u.email, u.first_name, u.last_name,
                u.phone, u.country, u.account_status,
                d.user_id as doctor_user_id,
                d.specialization_id,           -- Get the ID
                s.name AS specialization_name, -- Get the Name via JOIN
                d.license_number, d.license_state, d.license_expiration,
                d.npi_number, d.medical_school, d.graduation_year, d.certifications,
                d.accepting_new_patients, d.biography, d.profile_photo_url,
                d.clinic_address, d.verification_status,
                d.department_id,               -- Get the ID
                dep.name AS department_name    -- Get the Name via JOIN
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone()

        # Convert date/time fields if necessary (example for license_expiration)
        if doctor_info and doctor_info.get('license_expiration') and isinstance(doctor_info['license_expiration'], date):
             doctor_info['license_expiration_str'] = doctor_info['license_expiration'].isoformat()

    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error fetching doctor details for user_id {doctor_user_id}: {err}")
        return None
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching doctor details for user_id {doctor_user_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_info

# --- Availability Management Imports/Placeholders ---
# (Keep as is, assuming they work or are handled elsewhere)
try:
    from .availability_management import get_weekly_slots, get_overrides
except ImportError:
    current_app.logger.warning("Availability management functions not found, using placeholders.")
    def get_weekly_slots(doctor_id): return []
    def get_overrides(doctor_id, start_date_str=None, end_date_str=None): return []

# --- File Upload Helpers ---
# (Keep existing allowed_file, generate_secure_filename)
def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_secure_filename(filename):
    ext = ''
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
    # Limit prefix length if original filename is used
    secure_base = uuid.uuid4().hex
    secure_name = f"{secure_base}.{ext}" if ext else secure_base
    return secure_name

# --- Get Doctor Documents ---
# (Keep existing - seems okay with schema)
def get_doctor_documents(doctor_id):
    conn = None; cursor = None
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
        # Attempt to parse date for display if needed
        for doc in documents:
            if doc.get('upload_date'):
                if isinstance(doc['upload_date'], datetime): continue # Already datetime
                try: doc['upload_date'] = datetime.fromisoformat(str(doc['upload_date']))
                except (ValueError, TypeError): doc['upload_date'] = None # Handle parse failure
        return documents
    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error getting documents for doctor {doctor_id}: {err}")
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Blueprint Definition ---
settings_bp = Blueprint(
    'settings',
    __name__,
    url_prefix='/doctor/settings',
    template_folder='../../templates'
)

# --- Settings Routes ---

@settings_bp.route('/', methods=['GET'])
@login_required
def view_settings():
    """Displays the main settings page."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('login.login_route')) # Verify route

    doctor_id = current_user.id
    doctor_info = get_doctor_details(doctor_id) # Uses updated function
    if not doctor_info:
        flash("Could not load your profile information. Please contact support.", "danger")
        return redirect(url_for('doctor_main.dashboard')) # Verify route

    # *** Fetch specializations for the dropdown ***
    available_specializations = get_specializations()

    # Fetch Availability Data (logic seems okay)
    weekly_slots = get_weekly_slots(doctor_id)
    today = date.today()
    end_range = today + timedelta(days=60)
    overrides = get_overrides(doctor_id, today.isoformat(), end_range.isoformat())
    schedule = {i: [] for i in range(7)}
    for slot in weekly_slots:
         day_index = slot.get('day_of_week')
         if day_index is not None and 0 <= day_index <= 6:
              # Convert time if needed
              if isinstance(slot.get('start_time'), timedelta): slot['start_time'] = (datetime.min + slot['start_time']).time()
              if isinstance(slot.get('end_time'), timedelta): slot['end_time'] = (datetime.min + slot['end_time']).time()
              schedule[day_index].append(slot)
    days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # Fetch Documents
    doctor_documents = get_doctor_documents(doctor_id)
    current_year = datetime.now().year

    # *** Pass specializations to template ***
    return render_template(
        'Doctor_Portal/settings.html',
        doctor_info=doctor_info,
        available_specializations=available_specializations, # Pass list
        schedule=schedule,
        overrides=overrides,
        days_of_week=days_of_week,
        today_date=today,
        current_year=current_year,
        doctor_documents=doctor_documents
    )


@settings_bp.route('/profile', methods=['POST'])
@login_required
def update_profile():
    """Handles updates to the doctor's profile information."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('login.login_route')) # Verify route

    doctor_id = current_user.id
    conn = None; cursor = None

    # Get Data
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip() or None
    # *** UPDATED: Get specialization_id ***
    specialization_id_str = request.form.get('specialization_id', '').strip()
    npi_number = request.form.get('npi_number', '').strip() or None
    license_number = request.form.get('license_number', '').strip()
    license_state = request.form.get('license_state', '').strip()
    license_expiration_str = request.form.get('license_expiration', '').strip()
    medical_school = request.form.get('medical_school', '').strip() or None
    graduation_year_str = request.form.get('graduation_year', '').strip()
    certifications = request.form.get('certifications', '').strip() or None
    biography = request.form.get('biography', '').strip() or None
    accepting_new = request.form.get('accepting_new_patients') == 'on'
    clinic_address = request.form.get('clinic_address', '').strip() or None
    # Assuming department_id might also be updatable on this form
    department_id_str = request.form.get('department_id', '').strip()


    # --- Validation ---
    errors = []
    if not first_name: errors.append("First name is required.")
    if not last_name: errors.append("Last name is required.")
    if not email: errors.append("Email is required.") # Add format validation if needed

    # *** Validate specialization_id ***
    specialization_id = None
    if not specialization_id_str:
        errors.append("Specialization is required.")
    else:
        try:
            specialization_id = int(specialization_id_str)
            # Optional: Check if this ID actually exists in the specializations table
        except ValueError:
            errors.append("Invalid specialization selected.")

    # *** Validate department_id (if present and required/integer) ***
    department_id = None
    if department_id_str: # If a value is provided
        try:
             department_id = int(department_id_str)
             # Optional: Check if ID exists in departments table
        except ValueError:
             errors.append("Invalid department selected.")
    # Add error if department is mandatory but not provided:
    # elif department_is_mandatory: errors.append("Department is required.")


    if not license_number: errors.append("License number is required.")
    if not license_state: errors.append("License state is required.")

    license_expiration_date = None
    if not license_expiration_str:
        errors.append("License expiration date is required.")
    else:
        try:
            license_expiration_date = date.fromisoformat(license_expiration_str)
        except ValueError:
            errors.append("Invalid license expiration date format (YYYY-MM-DD).")

    if npi_number and (not npi_number.isdigit() or len(npi_number) != 10):
        errors.append("NPI number must be 10 digits.")

    graduation_year = None
    if graduation_year_str:
        try:
            year_val = int(graduation_year_str)
            current_year = datetime.now().year
            if 1900 <= year_val <= current_year + 1:
                graduation_year = year_val
            else:
                errors.append(f"Graduation year must be between 1900 and {current_year + 1}.")
        except ValueError:
            errors.append("Graduation year must be a number.")

    if errors:
        for error in errors: flash(error, 'danger')
        return redirect(url_for('settings.view_settings')) # Redirect back on error
    # --- End Validation ---

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction() # Use transaction
        cursor = conn.cursor()

        # Update users table (seems okay)
        sql_update_user = "UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s, updated_at = NOW() WHERE user_id = %s"
        cursor.execute(sql_update_user, (first_name, last_name, email, phone, doctor_id))

        # *** UPDATED: Update doctors table with specialization_id and department_id ***
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
            department_id, # Pass department_id
            doctor_id
        )
        cursor.execute(sql_update_doctor, params_doctor)

        conn.commit() # Commit transaction
        flash("Profile updated successfully.", "success")

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"DB Error updating profile for doctor {doctor_id}: {err}")
        flash_msg = f"Database error updating profile: {err.msg}" if err.msg else "Database error."
        # Check for specific errors like unique constraints (e.g., email, NPI)
        if err.errno == 1062: # Duplicate entry
             if 'email' in err.msg: flash_msg = "Database error: Email address already in use."
             elif 'npi_number' in err.msg: flash_msg = "Database error: NPI Number already in use."
             else: flash_msg = "Database error: A unique value conflict occurred."
        elif err.errno == 1452: # Foreign key constraint fails
             if 'fk_doctor_specialization' in err.msg: flash_msg = "Database error: Invalid Specialization selected."
             elif 'fk_doctor_department' in err.msg: flash_msg = "Database error: Invalid Department selected."
             else: flash_msg = "Database error: Invalid selection for a related field."
        flash(flash_msg, "danger")
    except ConnectionError as ce:
        current_app.logger.error(f"{ce} updating profile for doctor {doctor_id}")
        flash("Database connection error.", "danger")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Unexpected error updating profile for doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('settings.view_settings'))


@settings_bp.route('/password', methods=['POST'])
@login_required
def update_password():
    """Handles password change requests."""
    # (Logic seems okay with schema - operates on users table)
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('login.login_route')) # Verify route

    doctor_id = current_user.id
    conn = None; cursor = None
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    errors = []
    if not all([current_password, new_password, confirm_password]): errors.append("All password fields are required.")
    elif new_password != confirm_password: errors.append("New password and confirmation do not match.")
    elif len(new_password) < 8: errors.append("New password must be at least 8 characters long.") # Example policy
    if errors:
        for error in errors: flash(error, 'danger')
        return redirect(url_for('settings.view_settings') + '#security')

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True) # Use dict cursor to fetch password

        cursor.execute("SELECT password FROM users WHERE user_id = %s", (doctor_id,))
        user_data = cursor.fetchone()

        if not user_data or not check_password_hash(user_data.get('password', ''), current_password):
            flash("Incorrect current password.", "danger")
            return redirect(url_for('settings.view_settings') + '#security')

        # Valid current password, proceed
        new_password_hash = generate_password_hash(new_password)
        cursor.close() # Close dict cursor
        conn.start_transaction() # Start transaction
        cursor = conn.cursor() # Standard cursor for update

        cursor.execute("UPDATE users SET password = %s, updated_at = NOW() WHERE user_id = %s", (new_password_hash, doctor_id))
        conn.commit() # Commit transaction
        flash("Password updated successfully.", "success")

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error updating password for doctor {doctor_id}: {err}")
        flash("Database error updating password.", "danger")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Unexpected error updating password for doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('settings.view_settings') + '#security')


# --- Profile Photo Routes ---
# (Logic seems okay with schema - operates on doctors.profile_photo_url)
@settings_bp.route('/profile_photo', methods=['POST'])
@login_required
def upload_profile_photo():
    if not check_doctor_authorization(current_user): return redirect(url_for('login.login_route'))
    doctor_id = current_user.id
    conn = None; cursor = None; upload_path_full = None; old_photo_path_full = None

    if 'profile_photo' not in request.files or not request.files['profile_photo'].filename:
        flash('No file selected.', 'warning'); return redirect(url_for('settings.view_settings') + '#profile-photo')
    file = request.files['profile_photo']

    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})
    if file and allowed_file(file.filename, allowed_extensions):
        secure_name = generate_secure_filename(file.filename) # Generate unique name
        upload_folder = current_app.config.get('UPLOAD_FOLDER_PROFILE')
        if not upload_folder:
             current_app.logger.error("UPLOAD_FOLDER_PROFILE not configured.")
             flash("Server configuration error preventing file upload.", "danger")
             return redirect(url_for('settings.view_settings') + '#profile-photo')

        upload_path_full = os.path.join(upload_folder, secure_name)
        # Path relative to static folder root for DB storage
        db_path = os.path.join('uploads', 'profile_pics', secure_name).replace(os.path.sep, '/')

        try:
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
            doc_data = cursor.fetchone()
            old_photo_path_db = doc_data.get('profile_photo_url') if doc_data else None
            cursor.close() # Close read cursor

            # Save file first
            os.makedirs(upload_folder, exist_ok=True) # Ensure directory exists
            file.save(upload_path_full)

            # Update DB
            conn.start_transaction()
            cursor = conn.cursor()
            cursor.execute("UPDATE doctors SET profile_photo_url = %s, updated_at = NOW() WHERE user_id = %s", (db_path, doctor_id))
            conn.commit()
            flash('Profile photo updated successfully.', 'success')

            # Delete old file AFTER successful DB update
            if old_photo_path_db:
                try:
                    old_photo_path_full = os.path.join(current_app.static_folder, old_photo_path_db)
                    if os.path.exists(old_photo_path_full) and old_photo_path_full != upload_path_full:
                        os.remove(old_photo_path_full)
                        current_app.logger.info(f"Deleted old profile photo: {old_photo_path_full}")
                except OSError as e:
                     current_app.logger.error(f"Error deleting old profile photo {old_photo_path_full}: {e}")
                     # Don't fail the whole request, just log the error

        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Error uploading profile photo for doctor {doctor_id}: {err}")
            flash('An error occurred uploading photo.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup saved file on error
                try: os.remove(upload_path_full)
                except OSError: pass
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Unexpected error uploading profile photo for doctor {doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup
                try: os.remove(upload_path_full)
                except OSError: pass
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

    return redirect(url_for('settings.view_settings') + '#profile-photo')

@settings_bp.route('/profile_photo/delete', methods=['POST'])
@login_required
def delete_profile_photo():
    # (Logic seems okay with schema - operates on doctors.profile_photo_url)
    if not check_doctor_authorization(current_user): return redirect(url_for('login.login_route'))
    doctor_id = current_user.id
    conn = None; cursor = None; photo_path_full = None

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT profile_photo_url FROM doctors WHERE user_id = %s", (doctor_id,))
        doc_data = cursor.fetchone()
        photo_path_db = doc_data.get('profile_photo_url') if doc_data else None

        if not photo_path_db:
            flash("No profile photo to delete.", "info")
        else:
            cursor.close() # Close read cursor
            conn.start_transaction() # Start transaction
            cursor = conn.cursor() # Standard cursor for update/delete
            cursor.execute("UPDATE doctors SET profile_photo_url = NULL, updated_at = NOW() WHERE user_id = %s", (doctor_id,))
            conn.commit() # Commit DB change first

            message = 'Profile photo removed.'
            flash_category = 'success'
            # Attempt to delete the file AFTER successful DB update
            try:
                photo_path_full = os.path.join(current_app.static_folder, photo_path_db)
                if os.path.exists(photo_path_full):
                    os.remove(photo_path_full)
                    current_app.logger.info(f"Deleted profile photo file: {photo_path_full}")
                else:
                    current_app.logger.warning(f"Profile photo file not found for deletion: {photo_path_full}")
                    message += ' (File not found on server)'
                    flash_category = 'warning' # Downgrade flash type
            except OSError as e:
                current_app.logger.error(f"Error deleting profile photo file {photo_path_full}: {e}")
                message = 'Photo record updated, but failed to delete the file.'
                flash_category = 'warning'
            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error deleting profile photo for doctor {doctor_id}: {err}")
        flash('Database error removing photo.', 'danger')
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Unexpected error deleting profile photo for doctor {doctor_id}: {e}", exc_info=True)
        flash('An unexpected error occurred.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('settings.view_settings') + '#profile-photo')


# --- Document Routes ---
# (Logic seems okay with schema - operates on doctor_documents)
@settings_bp.route('/documents', methods=['POST'])
@login_required
def upload_document():
    if not check_doctor_authorization(current_user): return redirect(url_for('login.login_route'))
    doctor_id = current_user.id
    conn = None; cursor = None; upload_path_full = None

    doc_type = request.form.get('document_type')
    allowed_types = ['license', 'certification', 'identity', 'education', 'other'] # Match ENUM

    if 'document_file' not in request.files or not request.files['document_file'].filename:
        flash('No file selected.', 'warning'); return redirect(url_for('settings.view_settings') + '#documents')
    file = request.files['document_file']

    if not doc_type or doc_type not in allowed_types:
         flash(f'Invalid or missing document type. Must be one of: {", ".join(allowed_types)}', 'danger'); return redirect(url_for('settings.view_settings') + '#documents')

    allowed_extensions = current_app.config.get('ALLOWED_DOC_EXTENSIONS', {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'})
    if file and allowed_file(file.filename, allowed_extensions):
        secure_name = generate_secure_filename(file.filename) # Unique name
        upload_folder = current_app.config.get('UPLOAD_FOLDER_DOCS')
        if not upload_folder:
             current_app.logger.error("UPLOAD_FOLDER_DOCS not configured.")
             flash("Server configuration error preventing file upload.", "danger")
             return redirect(url_for('settings.view_settings') + '#documents')

        upload_path_full = os.path.join(upload_folder, secure_name)
        db_path = os.path.join('uploads', 'doctor_docs', secure_name).replace(os.path.sep, '/')

        try:
            # Save file first
            os.makedirs(upload_folder, exist_ok=True)
            file.save(upload_path_full)
            file_size = os.path.getsize(upload_path_full)

            # Insert into DB
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction()
            cursor = conn.cursor()
            # Assuming file_name stores original name, file_path stores secured relative path
            query = """ INSERT INTO doctor_documents (doctor_id, document_type, file_name, file_path, file_size, upload_date) VALUES (%s, %s, %s, %s, %s, NOW()) """
            cursor.execute(query, (doctor_id, doc_type, secure_filename(file.filename), db_path, file_size)) # Use original secured name for file_name
            conn.commit()
            flash(f'{doc_type.capitalize()} document uploaded successfully.', 'success')

        except (mysql.connector.Error, ConnectionError, OSError, IOError) as err:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Error uploading document for doctor {doctor_id}: {err}")
            flash('An error occurred uploading the document.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup
                try: os.remove(upload_path_full)
                except OSError: pass
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Unexpected error uploading document for doctor {doctor_id}: {e}", exc_info=True)
            flash('An unexpected error occurred.', 'danger')
            if upload_path_full and os.path.exists(upload_path_full): # Cleanup
                try: os.remove(upload_path_full)
                except OSError: pass
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        flash('Invalid file type. Allowed: {}.'.format(', '.join(allowed_extensions)), 'danger')

    return redirect(url_for('settings.view_settings') + '#documents')


@settings_bp.route('/documents/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    # (Logic seems okay with schema - operates on doctor_documents)
    if not check_doctor_authorization(current_user): return redirect(url_for('login.login_route'))
    doctor_id = current_user.id
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
            doc_path_db = doc_data.get('file_path') # Relative path from static
            cursor.close() # Close read cursor
            conn.start_transaction() # Start transaction
            cursor = conn.cursor() # Standard cursor
            cursor.execute("DELETE FROM doctor_documents WHERE document_id = %s AND doctor_id = %s", (document_id, doctor_id))
            conn.commit() # Commit DB delete first

            message = 'Document record deleted.'
            flash_category = 'success'
            # Attempt to delete file AFTER DB commit
            if doc_path_db:
                try:
                    doc_path_full = os.path.join(current_app.static_folder, doc_path_db)
                    if os.path.exists(doc_path_full):
                        os.remove(doc_path_full)
                        current_app.logger.info(f"Deleted document file: {doc_path_full}")
                    else:
                         current_app.logger.warning(f"Document file not found for deletion: {doc_path_full}")
                         message += ' (File not found on server)'
                         flash_category = 'warning'
                except OSError as e:
                    current_app.logger.error(f"Error deleting document file {doc_path_full}: {e}")
                    message = 'Record deleted, but failed to delete the file.'
                    flash_category = 'warning'
            flash(message, flash_category)

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Error deleting document {document_id} for doctor {doctor_id}: {err}")
        flash("Database error deleting document.", 'danger')
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"Unexpected error deleting document {document_id} for doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", 'danger')
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('settings.view_settings') + '#documents')


# --- Securely Serve Uploaded Documents ---
# (Logic seems okay - verifies ownership based on file_path and user_id)
@settings_bp.route('/documents/view/<path:filename>')
@login_required
def view_uploaded_document(filename):
     if not check_doctor_authorization(current_user):
         flash("Access denied.", "warning"); return redirect(url_for('login.login_route'))

     # Construct expected relative path (important: needs to match what's stored)
     expected_db_path = os.path.join('uploads', 'doctor_docs', filename).replace(os.path.sep, '/')

     conn = None; cursor = None
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor(dictionary=True)
         # Verify current user owns this document *using the stored relative path*
         cursor.execute("""
             SELECT document_id FROM doctor_documents
             WHERE file_path = %s AND doctor_id = %s
         """, (expected_db_path, current_user.id))
         doc_owner = cursor.fetchone()

         if not doc_owner:
             # TODO: Implement admin access check if required
             flash("You do not have permission to view this document.", "danger")
             return redirect(url_for('settings.view_settings') + '#documents'), 403

         # If owner check passes:
         directory = current_app.config.get('UPLOAD_FOLDER_DOCS')
         if not directory: raise ValueError("Upload directory not configured")
         # Use secure_filename on the final component for safety
         safe_filename = secure_filename(os.path.basename(filename))
         # Construct full path to check existence before sending
         full_path = os.path.join(directory, safe_filename)
         if not os.path.exists(full_path):
             current_app.logger.error(f"Document file requested but not found at: {full_path} (DB path: {expected_db_path})")
             raise FileNotFoundError

         return send_from_directory(directory, safe_filename, as_attachment=False) # Display inline

     except FileNotFoundError:
         flash("Document file not found on server.", "danger")
         return redirect(url_for('settings.view_settings') + '#documents'), 404
     except (mysql.connector.Error, ConnectionError, ValueError) as err:
          current_app.logger.error(f"Error verifying/serving document access for {filename}: {err}")
          flash("Error verifying document access or configuration issue.", "danger")
          return redirect(url_for('settings.view_settings') + '#documents'), 500
     except Exception as e:
         current_app.logger.error(f"Error serving document {filename}: {e}", exc_info=True)
         flash("Could not serve document due to an unexpected error.", "danger")
         return redirect(url_for('settings.view_settings') + '#documents'), 500
     finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()