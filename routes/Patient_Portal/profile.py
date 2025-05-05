# routes/Patient_Portal/profile.py

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
    template_folder='../../templates' # Adjust if needed
)

# --- Helper Functions (Example - adapt from your existing ones if applicable) ---

def allowed_profile_pic(filename):
    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_profile_picture(file, user_id):
    upload_folder = current_app.config.get('UPLOAD_FOLDER_PROFILE')
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_PROFILE not configured.")
        return None, "Server configuration error."
    if file and allowed_profile_pic(file.filename):
        original_filename = secure_filename(file.filename)
        ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg' # default ext
        # Use user_id for filename predictability (or add timestamp for uniqueness)
        unique_filename = secure_filename(f"user_{user_id}_profile.{ext}")
        filepath = os.path.join(upload_folder, unique_filename)
        try:
            # Consider resizing the image here using Pillow before saving
            file.save(filepath)
            # Return the relative path for the database
            relative_path = os.path.join('uploads', 'profile_pics', unique_filename).replace(os.path.sep, '/')
            return relative_path, None
        except Exception as e:
            current_app.logger.error(f"Failed to save profile picture {unique_filename}: {e}")
            # Clean up if save failed
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError: pass
            return None, "Failed to save file."
    elif file:
        return None, "File type not allowed."
    else:
        return None, "No file provided."

def delete_profile_picture(filename_relative_path):
     # Similar logic to your delete_disease_image, using UPLOAD_FOLDER_PROFILE
     if not filename_relative_path: return False
     try:
        base_static_folder = current_app.static_folder
        if filename_relative_path.startswith('/') or '..' in filename_relative_path: return False
        filepath = os.path.join(base_static_folder, filename_relative_path)
        if not os.path.abspath(filepath).startswith(os.path.abspath(base_static_folder)): return False
        if os.path.exists(filepath) and os.path.isfile(filepath):
            os.remove(filepath)
            return True
     except Exception as e:
        current_app.logger.error(f"Error deleting profile picture {filename_relative_path}: {e}")
     return False

# --- Routes ---

@patient_profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def manage_profile():
    """View and Update Patient Profile (Personal, Contact, Insurance)."""
    if not check_patient_authorization(current_user): abort(403)
    user_id = current_user.id
    conn = None; cursor = None

    # Fetch Insurance Providers for dropdown
    insurance_providers = []
    try:
        # Simplified fetch - adapt as needed
        conn_ins = get_db_connection(); cursor_ins = conn_ins.cursor(dictionary=True)
        cursor_ins.execute("SELECT id, provider_name FROM insurance_providers WHERE is_active = TRUE ORDER BY provider_name")
        insurance_providers = cursor_ins.fetchall()
        if cursor_ins: cursor_ins.close()
        if conn_ins and conn_ins.is_connected(): conn_ins.close()
    except Exception as e:
         current_app.logger.error(f"Failed to fetch insurance providers for profile form: {e}")
         flash("Error loading insurance provider options.", "warning")


    if request.method == 'POST':
        # --- Process Form Data ---
        try:
            # Personal/Contact Info (from users table)
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            phone = request.form.get('phone', '').strip() or None
            country = request.form.get('country', '').strip() or None
            # Basic validation
            if not first_name or not last_name:
                flash("First and Last Name are required.", "danger")
                raise ValueError("Missing required name fields")

            # Patient Specific Info (from patients table)
            dob_str = request.form.get('date_of_birth')
            gender = request.form.get('gender')
            blood_type = request.form.get('blood_type')
            height_cm = request.form.get('height_cm') or None
            weight_kg = request.form.get('weight_kg') or None
            marital_status = request.form.get('marital_status') or None
            occupation = request.form.get('occupation', '').strip() or None

            # Insurance Info
            insurance_provider_id = request.form.get('insurance_provider_id')
            insurance_policy_number = request.form.get('insurance_policy_number', '').strip() or None
            insurance_group_number = request.form.get('insurance_group_number', '').strip() or None
            insurance_expiration_str = request.form.get('insurance_expiration')

            # Convert/Validate numerics and dates
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
            # Add validation for gender/blood_type/marital_status against ENUMs if needed
            height_val = float(height_cm) if height_cm else None
            weight_val = float(weight_kg) if weight_kg else None
            insurance_provider_id_val = int(insurance_provider_id) if insurance_provider_id else None
            insurance_expiration_val = datetime.strptime(insurance_expiration_str, '%Y-%m-%d').date() if insurance_expiration_str else None


            # --- Database Update ---
            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()

            # Update users table
            sql_user = "UPDATE users SET first_name=%s, last_name=%s, phone=%s, country=%s, updated_at=NOW() WHERE user_id=%s"
            cursor.execute(sql_user, (first_name, last_name, phone, country, user_id))

            # Update patients table (handle potential NULLs)
            sql_patient = """UPDATE patients SET date_of_birth=%s, gender=%s, blood_type=%s, height_cm=%s,
                               weight_kg=%s, insurance_provider_id=%s, insurance_policy_number=%s,
                               insurance_group_number=%s, insurance_expiration=%s, marital_status=%s,
                               occupation=%s WHERE user_id=%s"""
            cursor.execute(sql_patient, (
                dob, gender, blood_type, height_val, weight_val, insurance_provider_id_val,
                insurance_policy_number, insurance_group_number, insurance_expiration_val,
                marital_status, occupation, user_id
            ))
            # Check if patient record existed, if not, insert (should exist via trigger ideally)
            if cursor.rowcount == 0:
                 # This might indicate an issue if the patient record wasn't created previously
                 current_app.logger.warning(f"No existing patient record found for user {user_id} during profile update. Attempting insert.")
                 # You might need default values if inserting here
                 # sql_insert_patient = "INSERT INTO patients (user_id, date_of_birth, gender, ...) VALUES (%s, %s, %s, ...)"
                 # cursor.execute(sql_insert_patient, (user_id, dob, gender, ...)) # Add all required fields

            conn.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for('.manage_profile'))

        except ValueError as ve:
            # Already flashed specific error
            pass # Keep going to render form
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error updating profile for user {user_id}: {err}")
            flash("Database error updating profile.", "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Unexpected error updating profile for user {user_id}: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form with errors (pass submitted data back)
        profile_data = request.form.to_dict() # Get submitted data
        return render_template('Patient_Portal/Profile/manage_profile.html',
                               profile_data=profile_data, # Pass submitted data
                               insurance_providers=insurance_providers)


    # --- GET Request ---
    profile_data = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Query combining users and patients table
        query = """
            SELECT u.*, p.*
            FROM users u
            LEFT JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_id = %s
        """
        cursor.execute(query, (user_id,))
        profile_data = cursor.fetchone()
        if not profile_data:
            flash("Could not load profile data.", "warning")
            # Handle case where user exists but patient doesn't?
            # For now, just pass None or partial data
    except Exception as e:
        current_app.logger.error(f"Error fetching profile for user {user_id}: {e}")
        flash("Error loading profile data.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Patient_Portal/Profile/manage_profile.html',
                           profile_data=profile_data,
                           insurance_providers=insurance_providers)

@patient_profile_bp.route('/photo', methods=['POST'])
@login_required
def upload_photo():
    """Handles profile photo upload."""
    if not check_patient_authorization(current_user): abort(403)
    user_id = current_user.id

    if 'profile_picture' not in request.files:
        flash('No file part in request.', 'warning')
        return redirect(url_for('.manage_profile'))
    file = request.files['profile_picture']
    if file.filename == '':
        flash('No selected file.', 'warning')
        return redirect(url_for('.manage_profile'))

    # Save the file
    relative_path, error_msg = save_profile_picture(file, user_id)

    if error_msg:
        flash(f"Photo upload failed: {error_msg}", "danger")
        return redirect(url_for('.manage_profile'))

    # Update database
    conn = None; cursor = None
    try:
         # Delete old picture first if it exists
         conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
         cursor.execute("SELECT profile_picture FROM users WHERE user_id = %s", (user_id,))
         old_pic = cursor.fetchone()
         if old_pic and old_pic.get('profile_picture'):
              delete_profile_picture(old_pic['profile_picture']) # Attempt deletion

         # Update user record with new path
         cursor.execute("UPDATE users SET profile_picture = %s WHERE user_id = %s", (relative_path, user_id))
         conn.commit()
         flash("Profile picture updated successfully.", "success")
    except Exception as e:
         if conn: conn.rollback()
         current_app.logger.error(f"DB error updating profile picture for user {user_id}: {e}")
         flash("Database error updating profile picture.", "danger")
         # If DB update fails, try to delete the newly uploaded file
         if relative_path: delete_profile_picture(relative_path)
    finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_profile'))

@patient_profile_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def manage_notifications():
    """Manage Notification Preferences."""
    if not check_patient_authorization(current_user): abort(403)
    user_id = current_user.id

    if request.method == 'POST':
        # TODO: Get notification preferences from form
        # Example: email_appt_reminders = request.form.get('email_appt_reminders') == 'on'
        # TODO: Update user settings in the database (might need a dedicated settings table or JSON field)
        flash("Notification preferences updated (Not implemented).", "info")
        return redirect(url_for('.manage_notifications'))

    # GET Request
    # TODO: Fetch current notification settings from DB
    current_settings = {} # Placeholder
    return render_template('Patient_Portal/Profile/manage_notifications.html', settings=current_settings)