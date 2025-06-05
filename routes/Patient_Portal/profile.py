# routes/Patient_Portal/profile.py
from datetime import datetime, date # Ensure date is imported

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection
from utils.auth_helpers import check_patient_authorization # Import the helper
import mysql.connector

# Define Blueprint
patient_profile_bp = Blueprint(
    'patient_profile',
    __name__,
    url_prefix='/patient/profile',
    template_folder='../../templates' # Adjust if templates are two levels up
)

# --- Helper Functions (save_profile_picture, delete_profile_picture, allowed_profile_pic) remain the same ---
def allowed_profile_pic(filename):
    default_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', default_extensions)
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_profile_picture(file, user_id):
    upload_folder = current_app.config.get('UPLOAD_FOLDER_PROFILE')
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_PROFILE not configured in Flask app.")
        return None, "Server configuration error: Profile upload path not set."

    if not os.path.exists(upload_folder):
        try:
            os.makedirs(upload_folder, exist_ok=True)
            current_app.logger.info(f"Created profile upload folder: {upload_folder}")
        except OSError as e:
            current_app.logger.error(f"Could not create profile upload folder {upload_folder}: {e}")
            return None, "Server error: Cannot create upload directory."

    if file and allowed_profile_pic(file.filename):
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        unique_filename = secure_filename(f"user_{user_id}_profile_{int(datetime.now().timestamp())}.{ext}")
        filepath_absolute = os.path.join(upload_folder, unique_filename)
        
        try:
            file.save(filepath_absolute)
            current_app.logger.info(f"Profile picture saved to: {filepath_absolute}")

            relative_db_path = None
            if upload_folder.startswith(current_app.static_folder):
                relative_to_static = os.path.relpath(upload_folder, current_app.static_folder)
                relative_db_path = os.path.join(relative_to_static, unique_filename).replace(os.path.sep, '/')
            else:
                # Fallback or error if not under static_folder as url_for('static', ...) might not work
                current_app.logger.warning(
                    f"UPLOAD_FOLDER_PROFILE '{upload_folder}' is not configured under static_folder '{current_app.static_folder}'. "
                    f"Images may not be served correctly by url_for('static', ...). Consider a dedicated serving route."
                )
                # Assuming a conventional structure like 'uploads/profile_pics/filename.ext'
                # This part needs to be robust and align with how files are served if not in static_folder.
                # For now, let's construct a path assuming 'uploads/profile_pics' is the intended relative structure.
                # This is a simplification and might need adjustment based on your actual serving setup.
                path_parts = upload_folder.split(os.sep)
                try:
                    # Try to find common 'uploads' directory or similar structure if possible
                    static_marker = 'static' # Or a more specific part of your upload path
                    if static_marker in path_parts:
                        relevant_path_parts = path_parts[path_parts.index(static_marker) + 1:]
                        relative_db_path = os.path.join(*relevant_path_parts, unique_filename).replace(os.path.sep, '/')
                    else: # Default to a common structure if marker not found
                         base_uploads_dir = os.path.basename(os.path.dirname(upload_folder)) 
                         profile_pics_subdir = os.path.basename(upload_folder) 
                         relative_db_path = os.path.join(base_uploads_dir, profile_pics_subdir, unique_filename).replace(os.path.sep, '/')
                except ValueError: # if static_marker not found
                     base_uploads_dir = os.path.basename(os.path.dirname(upload_folder)) 
                     profile_pics_subdir = os.path.basename(upload_folder) 
                     relative_db_path = os.path.join(base_uploads_dir, profile_pics_subdir, unique_filename).replace(os.path.sep, '/')


            if not relative_db_path: # Should not happen if path construction is okay
                 return None, "Failed to determine relative database path for the uploaded file."

            return relative_db_path, None
        except Exception as e:
            current_app.logger.error(f"Failed to save profile picture {unique_filename} to {filepath_absolute}: {e}", exc_info=True)
            if os.path.exists(filepath_absolute):
                try: os.remove(filepath_absolute)
                except OSError as e_rem: current_app.logger.error(f"Failed to remove orphaned file {filepath_absolute}: {e_rem}")
            return None, "Failed to save uploaded file."
    elif file:
        default_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        allowed_ext_str = ", ".join(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', default_extensions))
        return None, f"Invalid file type. Allowed types: {allowed_ext_str}."
    else:
        return None, "No file was provided for upload."

def delete_profile_picture(filename_db_path):
     if not filename_db_path: return False
     try:
        base_static_folder = current_app.static_folder
        if filename_db_path.startswith('/') or '..' in filename_db_path:
            current_app.logger.warning(f"Attempt to delete profile picture with invalid path: {filename_db_path}")
            return False
        filepath_absolute = os.path.join(base_static_folder, filename_db_path)
        if not os.path.abspath(filepath_absolute).startswith(os.path.abspath(base_static_folder)):
            current_app.logger.warning(f"Path traversal attempt detected for profile picture deletion: {filepath_absolute}")
            return False
        if os.path.exists(filepath_absolute) and os.path.isfile(filepath_absolute):
            os.remove(filepath_absolute)
            current_app.logger.info(f"Deleted existing profile picture: {filepath_absolute}")
            return True
        else:
            current_app.logger.warning(f"Profile picture to delete not found at: {filepath_absolute} (DB path: {filename_db_path})")
            return False
     except Exception as e:
        current_app.logger.error(f"Error deleting profile picture {filename_db_path}: {e}", exc_info=True)
     return False


# --- Routes ---

@patient_profile_bp.route('/dashboard')
@login_required
def my_account_dashboard():
    if not check_patient_authorization(current_user):
        abort(403)
    return render_template('Patient_Portal/my_account.html')

@patient_profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def manage_profile():
    if not check_patient_authorization(current_user): abort(403)
    user_id = current_user.id
    conn = None; cursor = None
    insurance_providers = []
    
    try:
        conn_ins = get_db_connection()
        if not conn_ins : raise mysql.connector.Error("DB connection failed for insurance providers")
        cursor_ins = conn_ins.cursor(dictionary=True)
        cursor_ins.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
        insurance_providers = cursor_ins.fetchall()
    except Exception as e:
         current_app.logger.error(f"Failed to fetch insurance providers for profile form: {e}")
         flash("Error loading insurance provider options. Please try again later.", "warning")
    finally:
        if 'cursor_ins' in locals() and cursor_ins: cursor_ins.close()
        if 'conn_ins' in locals() and conn_ins and conn_ins.is_connected(): conn_ins.close()

    if request.method == 'POST':
        form_data = request.form.to_dict()
        try:
            first_name = form_data.get('first_name', '').strip()
            last_name = form_data.get('last_name', '').strip()
            phone = form_data.get('phone', '').strip() or None
            country = form_data.get('country', '').strip() or None
            
            errors = []
            if not first_name: errors.append("First Name is required.")
            if not last_name: errors.append("Last Name is required.")

            dob_str = form_data.get('date_of_birth')
            gender = form_data.get('gender') or 'unknown' # Default if not submitted
            blood_type = form_data.get('blood_type') or 'Unknown'
            height_cm_str = form_data.get('height_cm')
            weight_kg_str = form_data.get('weight_kg')
            marital_status = form_data.get('marital_status') or None
            occupation = form_data.get('occupation', '').strip() or None

            insurance_provider_id_str = form_data.get('insurance_provider_id')
            insurance_policy_number = form_data.get('insurance_policy_number', '').strip() or None
            insurance_group_number = form_data.get('insurance_group_number', '').strip() or None
            insurance_expiration_str = form_data.get('insurance_expiration')

            if not dob_str:
                errors.append("Date of Birth is required.")
                dob = None
            else:
                try: dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError: errors.append("Invalid Date of Birth format. Use YYYY-MM-DD."); dob = None
            
            # TODO: Validate gender, blood_type, marital_status against ENUMs

            height_val = None
            if height_cm_str:
                try: height_val = float(height_cm_str) if height_cm_str else None
                except ValueError: errors.append("Height must be a valid number (e.g., 175.5).")
            
            weight_val = None
            if weight_kg_str:
                try: weight_val = float(weight_kg_str) if weight_kg_str else None
                except ValueError: errors.append("Weight must be a valid number (e.g., 70.2).")

            insurance_provider_id_val = None
            if insurance_provider_id_str and insurance_provider_id_str.isdigit():
                insurance_provider_id_val = int(insurance_provider_id_str)
            elif insurance_provider_id_str and insurance_provider_id_str != "": # Non-empty string that's not a digit
                errors.append("Invalid Insurance Provider selected.")

            insurance_expiration_val = None
            if insurance_expiration_str:
                try: insurance_expiration_val = datetime.strptime(insurance_expiration_str, '%Y-%m-%d').date()
                except ValueError: errors.append("Invalid Insurance Expiration Date format. Use YYYY-MM-DD.")
            
            if errors:
                for err_msg in errors: flash(err_msg, "danger")
            else:
                conn = get_db_connection()
                if not conn: raise mysql.connector.Error("Database connection failed for profile update.")
                conn.start_transaction()
                cursor = conn.cursor()
                
                sql_user = "UPDATE users SET first_name=%s, last_name=%s, phone=%s, country=%s, updated_at=NOW() WHERE user_id=%s"
                cursor.execute(sql_user, (first_name, last_name, phone, country, user_id))

                # *** MODIFIED SECTION FOR PATIENTS TABLE ***
                sql_patient_upsert = """
                    INSERT INTO patients (
                        user_id, date_of_birth, gender, blood_type, height_cm,
                        weight_kg, insurance_provider_id, insurance_policy_number,
                        insurance_group_number, insurance_expiration, marital_status,
                        occupation
                    ) VALUES (
                        %(user_id)s, %(dob)s, %(gender)s, %(blood_type)s, %(height_cm)s,
                        %(weight_kg)s, %(insurance_provider_id)s, %(insurance_policy_number)s,
                        %(insurance_group_number)s, %(insurance_expiration)s, %(marital_status)s,
                        %(occupation)s
                    )
                    ON DUPLICATE KEY UPDATE
                        date_of_birth = VALUES(date_of_birth),
                        gender = VALUES(gender),
                        blood_type = VALUES(blood_type),
                        height_cm = VALUES(height_cm),
                        weight_kg = VALUES(weight_kg),
                        insurance_provider_id = VALUES(insurance_provider_id),
                        insurance_policy_number = VALUES(insurance_policy_number),
                        insurance_group_number = VALUES(insurance_group_number),
                        insurance_expiration = VALUES(insurance_expiration),
                        marital_status = VALUES(marital_status),
                        occupation = VALUES(occupation)
                """
                patient_params_for_upsert = {
                    'user_id': user_id, 'dob': dob, 'gender': gender, 'blood_type': blood_type, 
                    'height_cm': height_val, 'weight_kg': weight_val, 
                    'insurance_provider_id': insurance_provider_id_val, 
                    'insurance_policy_number': insurance_policy_number, 
                    'insurance_group_number': insurance_group_number, 
                    'insurance_expiration': insurance_expiration_val, 
                    'marital_status': marital_status, 'occupation': occupation
                }
                cursor.execute(sql_patient_upsert, patient_params_for_upsert)
                
                # cursor.rowcount for INSERT ... ON DUPLICATE KEY UPDATE:
                # 0: No change (existing row matched, values were identical)
                # 1: New row inserted
                # 2: Existing row updated
                if cursor.rowcount == 0:
                    current_app.logger.info(f"Patient data for user_id {user_id} processed. No actual changes made to the database (values were identical).")
                elif cursor.rowcount == 1:
                    current_app.logger.info(f"Patient data for user_id {user_id} inserted successfully.")
                elif cursor.rowcount >= 2: # Can be 2 if updated, or more with triggers.
                    current_app.logger.info(f"Patient data for user_id {user_id} updated successfully.")
                # *** END OF MODIFIED SECTION ***

                conn.commit()
                flash("Profile updated successfully!", "success")
                return redirect(url_for('.manage_profile'))

        except mysql.connector.Error as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"DB error updating profile for user {user_id}: {err}")
            # Check for specific duplicate entry error related to other unique keys if any
            if err.errno == 1062: # Duplicate entry
                 # Determine if it's the primary key or another unique key.
                 # The original error was for 'PRIMARY', which is user_id.
                 # The ON DUPLICATE KEY UPDATE should handle this.
                 # If it's another unique key, the message should be more specific.
                 flash(f"Database error: A record with some of this information already exists and could not be updated. ({err.msg})", "danger")
            else:
                flash("Database error updating profile. Please check your input or try again later.", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"Unexpected error updating profile for user {user_id}: {e}", exc_info=True)
            if not errors:
                flash(f"An error occurred: {str(e)}", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        original_profile_data_for_error = {}
        try:
            conn_get = get_db_connection(); 
            if not conn_get: raise mysql.connector.Error("DB Connection failed for GET on error")
            cursor_get = conn_get.cursor(dictionary=True)
            query_get = "SELECT u.*, p.* FROM users u LEFT JOIN patients p ON u.user_id = p.user_id WHERE u.user_id = %s"
            cursor_get.execute(query_get, (user_id,))
            original_profile_data_for_error = cursor_get.fetchone() or {}
        except Exception as e_fetch:
            current_app.logger.error(f"Error fetching original profile data on POST error for user {user_id}: {e_fetch}")
        finally:
            if 'cursor_get' in locals() and cursor_get: cursor_get.close()
            if 'conn_get' in locals() and conn_get and conn_get.is_connected(): conn_get.close()
        
        data_for_template_on_error = original_profile_data_for_error.copy()
        data_for_template_on_error.update(form_data)

        return render_template('Patient_Portal/Profile/manage_profile.html',
                               profile_data=data_for_template_on_error,
                               insurance_providers=insurance_providers,
                               form_had_errors=True)

    # --- GET Request ---
    profile_data_get = None
    try:
        conn = get_db_connection()
        if not conn : raise mysql.connector.Error("DB connection failed for GET profile")
        cursor = conn.cursor(dictionary=True)
        query = """SELECT u.user_id, u.username, u.email, u.first_name, u.last_name, u.phone, u.country, u.profile_picture,
                          p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
                          p.insurance_provider_id, p.insurance_policy_number, p.insurance_group_number,
                          p.insurance_expiration, p.marital_status, p.occupation
                   FROM users u
                   LEFT JOIN patients p ON u.user_id = p.user_id
                   WHERE u.user_id = %s AND u.user_type = 'patient'"""
        cursor.execute(query, (user_id,))
        profile_data_get = cursor.fetchone()
        
        if not profile_data_get:
            current_app.logger.error(f"CRITICAL: No user record found for logged-in patient ID {user_id}.")
            flash("Could not load your profile data. Please contact support.", "danger")
        elif profile_data_get.get('date_of_birth') is None and profile_data_get.get('gender') is None:
             flash("Please complete your profile information by filling out and saving the form.", "info")

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error fetching profile for user {user_id} (GET): {db_err}")
        flash("Error loading your profile data. Please try refreshing.", "danger")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching profile for user {user_id} (GET): {e}", exc_info=True)
        flash("An unexpected error occurred while loading your profile.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Patient_Portal/Profile/manage_profile.html',
                           profile_data=profile_data_get,
                           insurance_providers=insurance_providers)


@patient_profile_bp.route('/photo', methods=['POST'])
@login_required
def upload_photo():
    if not check_patient_authorization(current_user): abort(403)
    user_id = current_user.id

    if 'profile_picture' not in request.files:
        flash('No file part selected for upload.', 'warning')
        return redirect(url_for('.manage_profile'))
    file = request.files['profile_picture']
    if file.filename == '':
        flash('No file selected for upload.', 'warning')
        return redirect(url_for('.manage_profile'))

    relative_path_db, error_msg = save_profile_picture(file, user_id)

    if error_msg:
        flash(f"Photo upload failed: {error_msg}", "danger")
        return redirect(url_for('.manage_profile'))
    if not relative_path_db: # Should be caught by error_msg but as a safeguard
        flash(f"Photo upload failed: Could not determine file path.", "danger")
        return redirect(url_for('.manage_profile'))


    conn = None; cursor = None
    try:
         conn = get_db_connection()
         if not conn: raise mysql.connector.Error("DB connection failed for photo upload.")
         cursor = conn.cursor(dictionary=True)
         
         cursor.execute("SELECT profile_picture FROM users WHERE user_id = %s", (user_id,))
         old_pic_data = cursor.fetchone()
         
         cursor.execute("UPDATE users SET profile_picture = %s, updated_at=NOW() WHERE user_id = %s", (relative_path_db, user_id))
         conn.commit()

         if old_pic_data and old_pic_data.get('profile_picture'):
            if old_pic_data['profile_picture'] != relative_path_db:
                 delete_profile_picture(old_pic_data['profile_picture'])
            elif file.content_length > 0:
                current_app.logger.info(f"New profile picture uploaded with same relative path as old for user {user_id}. Old file overwritten/managed by save.")

         flash("Profile picture updated successfully.", "success")
    except mysql.connector.Error as db_err:
         if conn and conn.is_connected() and conn.in_transaction : conn.rollback()
         current_app.logger.error(f"DB error updating profile picture for user {user_id}: {db_err}")
         flash("Database error updating profile picture.", "danger")
         if relative_path_db: delete_profile_picture(relative_path_db)
    except Exception as e:
         if conn and conn.is_connected() and conn.in_transaction : conn.rollback()
         current_app.logger.error(f"Unexpected error during photo upload DB op for user {user_id}: {e}", exc_info=True)
         flash("An unexpected error occurred while saving profile picture information.", "danger")
         if relative_path_db: delete_profile_picture(relative_path_db)
    finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.manage_profile'))