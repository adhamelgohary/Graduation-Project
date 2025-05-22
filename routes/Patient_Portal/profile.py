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

# --- Helper Functions ---
def allowed_profile_pic(filename):
    # Ensure ALLOWED_IMAGE_EXTENSIONS is fetched from config correctly
    # Provide a default set if the config key is missing
    default_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', default_extensions)
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_profile_picture(file, user_id):
    upload_folder = current_app.config.get('UPLOAD_FOLDER_PROFILE') # e.g., 'instance/uploads/profile_pics'
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_PROFILE not configured in Flask app.")
        return None, "Server configuration error: Profile upload path not set."

    # Ensure the base upload folder exists (Flask doesn't create it automatically usually)
    # This should ideally be done at app startup using directory_configs.py
    # For robustness here, we can check/create, but it's better if configure_directories handles it.
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
        # Create a unique filename to avoid overwrites and use secure_filename
        unique_filename = secure_filename(f"user_{user_id}_profile_{int(datetime.now().timestamp())}.{ext}")
        
        filepath_absolute = os.path.join(upload_folder, unique_filename)
        
        try:
            file.save(filepath_absolute)
            current_app.logger.info(f"Profile picture saved to: {filepath_absolute}")

            # The path stored in DB should be relative to the 'static' folder
            # if UPLOAD_FOLDER_PROFILE is configured as 'app/static/uploads/profile_pics'
            # then relative_path = 'uploads/profile_pics/unique_filename.ext'
            # If UPLOAD_FOLDER_PROFILE is 'instance/uploads/profile_pics', you need a route to serve these.
            # For now, assuming it's relative to a base 'uploads' dir accessible via static.
            # This needs to align with your UPLOAD_FOLDER_PROFILE setting and static file serving.
            # Example: if UPLOAD_FOLDER_PROFILE is '.../project_root/app/static/uploads/profile_pics'
            # then the path to store in DB is 'uploads/profile_pics/filename.ext'
            
            # Let's assume UPLOAD_FOLDER_PROFILE is an absolute path.
            # We need to make it relative to the app's static folder or a designated uploads serving point.
            # A common pattern is to have UPLOAD_FOLDER_PROFILE be a subfolder of current_app.static_folder.
            # If so:
            if upload_folder.startswith(current_app.static_folder):
                relative_to_static = os.path.relpath(upload_folder, current_app.static_folder)
                relative_db_path = os.path.join(relative_to_static, unique_filename).replace(os.path.sep, '/')
            else:
                # If not under static, you likely need a dedicated route to serve these files.
                # Storing just the filename might be an option if the serving route knows the user_id.
                # For simplicity now, if not under static, we'll assume a conventional structure.
                # This is a critical part that needs to match your file serving strategy.
                # A common convention is 'uploads/subfolder/filename' relative to static.
                # If your UPLOAD_FOLDER_PROFILE is something like /var/www/my_app/instance/uploads/profile_pics
                # then this needs a dedicated serving route.
                # For now, let's assume a structure like 'uploads/profile_pics/' inside static.
                # If UPLOAD_FOLDER_PROFILE points to '.../static/uploads/profile_pics', this works:
                relative_db_path = os.path.join(os.path.basename(os.path.dirname(upload_folder)), os.path.basename(upload_folder), unique_filename).replace(os.path.sep, '/')
                # More robustly, if UPLOAD_FOLDER_PROFILE is ".../app/static/uploads/profile_pics"
                # and current_app.static_folder is ".../app/static"
                # then:
                # static_parent = os.path.dirname(current_app.static_folder) # .../app
                # common_path = os.path.commonpath([upload_folder, current_app.static_folder])
                # if common_path == current_app.static_folder:
                #    relative_db_path = os.path.relpath(filepath_absolute, current_app.static_folder).replace(os.path.sep, '/')
                # else assume a default structure if not directly under static
                # THIS IS COMPLEX AND DEPENDS ON YOUR `directory_configs.py`
                # A simpler, more direct assumption:
                # If UPLOAD_FOLDER_PROFILE is "app_root/static/uploads/profile_pics"
                # then store "uploads/profile_pics/filename.ext"
                # Find base "uploads" part from UPLOAD_FOLDER_PROFILE relative to static path
                
                # Assuming `UPLOAD_FOLDER_PROFILE` is configured like `os.path.join(app.static_folder, 'uploads', 'profile_pics')`
                # then this should work:
                base_uploads_dir = os.path.basename(os.path.dirname(upload_folder)) # e.g., 'uploads'
                profile_pics_subdir = os.path.basename(upload_folder) # e.g., 'profile_pics'
                relative_db_path = os.path.join(base_uploads_dir, profile_pics_subdir, unique_filename).replace(os.path.sep, '/')

            return relative_db_path, None
        except Exception as e:
            current_app.logger.error(f"Failed to save profile picture {unique_filename} to {filepath_absolute}: {e}", exc_info=True)
            if os.path.exists(filepath_absolute):
                try: os.remove(filepath_absolute)
                except OSError as e_rem: current_app.logger.error(f"Failed to remove orphaned file {filepath_absolute}: {e_rem}")
            return None, "Failed to save uploaded file."
    elif file: # File was provided but not allowed type
        allowed_ext_str = ", ".join(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', default_extensions))
        return None, f"Invalid file type. Allowed types: {allowed_ext_str}."
    else: # No file provided
        return None, "No file was provided for upload."


def delete_profile_picture(filename_db_path):
     if not filename_db_path: return False
     # filename_db_path is expected to be relative to the static folder,
     # e.g., "uploads/profile_pics/user_1_profile.jpg"
     try:
        base_static_folder = current_app.static_folder # e.g., /path/to/app/static
        
        # Security checks for path traversal
        if filename_db_path.startswith('/') or '..' in filename_db_path:
            current_app.logger.warning(f"Attempt to delete profile picture with invalid path: {filename_db_path}")
            return False
            
        filepath_absolute = os.path.join(base_static_folder, filename_db_path)
        
        # Final check to ensure the path is still within the static folder
        if not os.path.abspath(filepath_absolute).startswith(os.path.abspath(base_static_folder)):
            current_app.logger.warning(f"Path traversal attempt detected for profile picture deletion: {filepath_absolute}")
            return False

        if os.path.exists(filepath_absolute) and os.path.isfile(filepath_absolute):
            os.remove(filepath_absolute)
            current_app.logger.info(f"Deleted existing profile picture: {filepath_absolute}")
            return True
        else:
            current_app.logger.warning(f"Profile picture to delete not found at: {filepath_absolute} (DB path: {filename_db_path})")
            return False # File not found, but not necessarily an error for this function's purpose
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
    user_id = current_user.id # This is int
    conn = None; cursor = None
    insurance_providers = []
    
    # Fetch insurance providers for the form dropdown
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
        form_data = request.form.to_dict() # Get all form data at once
        try:
            # --- Personal/Contact Info (from users table) ---
            first_name = form_data.get('first_name', '').strip()
            last_name = form_data.get('last_name', '').strip()
            phone = form_data.get('phone', '').strip() or None # Keep as None if empty
            country = form_data.get('country', '').strip() or None # Keep as None if empty
            
            errors = []
            if not first_name: errors.append("First Name is required.")
            if not last_name: errors.append("Last Name is required.")
            # Add more validation for phone, country if needed (e.g., length, format)

            # --- Patient Specific Info (from patients table) ---
            dob_str = form_data.get('date_of_birth')
            gender = form_data.get('gender')
            # Default blood_type to 'Unknown' if not provided or empty, as DB column has this default
            blood_type = form_data.get('blood_type') if form_data.get('blood_type') else 'Unknown'
            height_cm_str = form_data.get('height_cm')
            weight_kg_str = form_data.get('weight_kg')
            marital_status = form_data.get('marital_status') if form_data.get('marital_status') else None # Allow empty to be NULL
            occupation = form_data.get('occupation', '').strip() or None

            # --- Insurance Info ---
            insurance_provider_id_str = form_data.get('insurance_provider_id')
            insurance_policy_number = form_data.get('insurance_policy_number', '').strip() or None
            insurance_group_number = form_data.get('insurance_group_number', '').strip() or None
            insurance_expiration_str = form_data.get('insurance_expiration')

            # --- Form Data Validation and Conversion ---
            if not dob_str:
                errors.append("Date of Birth is required.")
                dob = None # Must be provided for patients table
            else:
                try: dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                except ValueError: errors.append("Invalid Date of Birth format. Use YYYY-MM-DD."); dob = None
            
            if not gender: # Gender is NOT NULL with default 'unknown'
                gender = 'unknown' # Default if not submitted, or validate against ENUMs
            # TODO: Validate gender, blood_type, marital_status against ENUM values fetched from DB

            height_val = None
            if height_cm_str:
                try: height_val = float(height_cm_str)
                except ValueError: errors.append("Height must be a valid number (e.g., 175.5).")
            
            weight_val = None
            if weight_kg_str:
                try: weight_val = float(weight_kg_str)
                except ValueError: errors.append("Weight must be a valid number (e.g., 70.2).")

            insurance_provider_id_val = None
            if insurance_provider_id_str and insurance_provider_id_str.isdigit():
                insurance_provider_id_val = int(insurance_provider_id_str)
            elif insurance_provider_id_str: # If it's not empty string but not a digit
                errors.append("Invalid Insurance Provider selected.")

            insurance_expiration_val = None
            if insurance_expiration_str:
                try: insurance_expiration_val = datetime.strptime(insurance_expiration_str, '%Y-%m-%d').date()
                except ValueError: errors.append("Invalid Insurance Expiration Date format. Use YYYY-MM-DD.")
            
            if errors:
                for err_msg in errors: flash(err_msg, "danger")
                # To ensure submitted data is repopulated correctly:
                # The data_for_template_on_error block later will handle merging.
                # No need to raise ValueError here if we want to fall through to template rendering.
            else: # Proceed to DB update only if no validation errors
                conn = get_db_connection()
                if not conn: raise mysql.connector.Error("Database connection failed for profile update.")
                conn.start_transaction()
                cursor = conn.cursor()
                
                sql_user = "UPDATE users SET first_name=%s, last_name=%s, phone=%s, country=%s, updated_at=NOW() WHERE user_id=%s"
                cursor.execute(sql_user, (first_name, last_name, phone, country, user_id))

                patient_data_tuple_for_update = (
                    dob, gender, blood_type, height_val, weight_val, 
                    insurance_provider_id_val, insurance_policy_number, insurance_group_number, 
                    insurance_expiration_val, marital_status, occupation, user_id
                )
                sql_patient_update = """UPDATE patients SET 
                                   date_of_birth=%s, gender=%s, blood_type=%s, height_cm=%s,
                                   weight_kg=%s, insurance_provider_id=%s, insurance_policy_number=%s,
                                   insurance_group_number=%s, insurance_expiration=%s, marital_status=%s,
                                   occupation=%s 
                                   WHERE user_id=%s"""
                cursor.execute(sql_patient_update, patient_data_tuple_for_update)
                
                if cursor.rowcount == 0:
                     current_app.logger.warning(f"Patient record for user_id {user_id} not found for UPDATE. Attempting INSERT.")
                     sql_patient_insert = """INSERT INTO patients 
                                         (user_id, date_of_birth, gender, blood_type, height_cm,
                                         weight_kg, insurance_provider_id, insurance_policy_number,
                                         insurance_group_number, insurance_expiration, marital_status,
                                         occupation)
                                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                     insert_params_patients = (user_id,) + patient_data_tuple_for_update[:-1] # user_id first, then rest except last user_id
                     cursor.execute(sql_patient_insert, insert_params_patients)
                     current_app.logger.info(f"Successfully inserted new patient record for user {user_id}.")

                conn.commit()
                flash("Profile updated successfully!", "success")
                return redirect(url_for('.manage_profile'))

        except mysql.connector.Error as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"DB error updating profile for user {user_id}: {err}")
            flash("Database error updating profile. Please check your input or try again later.", "danger")
        except Exception as e: # Catch other errors like ValueError from bad float/int conversions if not caught by prior checks
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"Unexpected error updating profile for user {user_id}: {e}", exc_info=True)
            if not errors: # If error list is empty, it means this exception was not a validation one we explicitly added
                flash(f"An error occurred: {str(e)}", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # --- On POST Error (if errors list is populated or other exception occurred): Prepare data for re-rendering template ---
        # Fetch original profile data to ensure all fields (even not in form) are available
        original_profile_data_for_error = {}
        try:
            conn_get = get_db_connection(); 
            if not conn_get: raise mysql.connector.Error("DB Connection failed for GET on error")
            cursor_get = conn_get.cursor(dictionary=True)
            query_get = "SELECT u.*, p.* FROM users u LEFT JOIN patients p ON u.user_id = p.user_id WHERE u.user_id = %s"
            cursor_get.execute(query_get, (user_id,)) # user_id is int
            original_profile_data_for_error = cursor_get.fetchone() or {}
        except Exception as e_fetch:
            current_app.logger.error(f"Error fetching original profile data on POST error for user {user_id}: {e_fetch}")
        finally:
            if 'cursor_get' in locals() and cursor_get: cursor_get.close()
            if 'conn_get' in locals() and conn_get and conn_get.is_connected(): conn_get.close()
        
        # Merge original data with submitted form data (form data takes precedence for repopulation)
        data_for_template_on_error = original_profile_data_for_error.copy() # Start with DB data
        data_for_template_on_error.update(form_data) # Override with what user submitted

        return render_template('Patient_Portal/Profile/manage_profile.html',
                               profile_data=data_for_template_on_error,
                               insurance_providers=insurance_providers,
                               form_had_errors=True) # Flag for template

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
        cursor.execute(query, (user_id,)) # user_id is int
        profile_data_get = cursor.fetchone()
        
        if not profile_data_get:
            current_app.logger.error(f"CRITICAL: No user record found for logged-in patient ID {user_id}.")
            flash("Could not load your profile data. Please contact support.", "danger")
            # Potentially redirect to logout or an error page if user record itself is missing
            # For now, template will handle profile_data_get being None
        elif profile_data_get.get('date_of_birth') is None and profile_data_get.get('gender') is None:
             # This indicates that the patients table row might be missing or incomplete.
             # The POST handler will attempt to create/complete it on next save.
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

    conn = None; cursor = None
    try:
         conn = get_db_connection()
         if not conn: raise mysql.connector.Error("DB connection failed for photo upload.")
         cursor = conn.cursor(dictionary=True) # Use dictionary for fetching old pic
         
         # Fetch old picture path to delete it from filesystem
         cursor.execute("SELECT profile_picture FROM users WHERE user_id = %s", (user_id,))
         old_pic_data = cursor.fetchone()
         
         # Update user record with new path (even if old_pic_data is None)
         cursor.execute("UPDATE users SET profile_picture = %s, updated_at=NOW() WHERE user_id = %s", (relative_path_db, user_id))
         conn.commit()

         # Delete old picture file AFTER successful DB commit
         if old_pic_data and old_pic_data.get('profile_picture'):
            # Make sure the old path isn't the same as the new one if filenames could be identical but content changed
            if old_pic_data['profile_picture'] != relative_path_db:
                 delete_profile_picture(old_pic_data['profile_picture'])
            elif file.content_length > 0: # If names are same but a new file was uploaded, delete the old one (which is now overwritten by new)
                current_app.logger.info(f"New profile picture uploaded with same relative path as old for user {user_id}. Old file overwritten.")


         flash("Profile picture updated successfully.", "success")
    except mysql.connector.Error as db_err:
         if conn and conn.is_connected() and conn.in_transaction : conn.rollback()
         current_app.logger.error(f"DB error updating profile picture for user {user_id}: {db_err}")
         flash("Database error updating profile picture.", "danger")
         # If DB update fails, try to delete the newly uploaded file to prevent orphans
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

@patient_profile_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def manage_notifications():
    if not check_patient_authorization(current_user): abort(403)
    # user_id = current_user.id # Not used yet
    if request.method == 'POST':
        # TODO:
        # 1. Get notification preferences from request.form (e.g., email_reminders, sms_updates)
        # 2. Validate these preferences.
        # 3. Store them in the database. This might involve:
        #    - Adding new columns to the 'users' or 'patients' table (e.g., allow_email_reminders BOOLEAN).
        #    - Creating a new table 'user_notification_settings (user_id, setting_key, setting_value)'.
        #    - Storing as a JSON object in a TEXT column in 'users' or 'patients'.
        flash("Notification preferences updated (Functionality Not Implemented Yet).", "info")
        return redirect(url_for('.manage_notifications'))

    # GET Request
    # TODO:
    # 1. Fetch current notification settings for current_user.id from the database.
    current_settings = { # Placeholder data
        'email_appointment_reminders': True,
        'sms_prescription_updates': False,
        'newsletter_opt_in': True
    }
    return render_template('Patient_Portal/Profile/manage_notifications.html', settings=current_settings)