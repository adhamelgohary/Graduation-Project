# routes/Website/doctor.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, jsonify
)
from flask_login import current_user
import mysql.connector
from db import get_db_connection
# from math import ceil # Only if you implement pagination directly here

# Define the blueprint
doctor_bp = Blueprint(
    'doctor',
    __name__,
    template_folder='../../templates/Website', # Relative to this file's location
    url_prefix='/doctors'
)

# --- Helper Functions ---

def get_all_departments_for_filter():
    """Fetches ID and Name for all active departments for filters."""
    conn = None; cursor = None; departments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT department_id, name 
            FROM departments 
            WHERE name NOT IN ('Other/Unspecified', 'PENDING_VERIFICATION_DEPT') 
            ORDER BY name ASC
        """
        cursor.execute(query)
        departments = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching departments list for filter: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return departments

def get_specializations_by_department_for_filter(department_id=None):
    """
    Fetches ID and Name for specializations.
    If department_id is provided, fetches specializations only for that department.
    Otherwise, fetches all relevant specializations (excluding placeholders).
    """
    conn = None; cursor = None; specializations = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        params = []
        query = """
            SELECT specialization_id, name 
            FROM specializations 
            WHERE name NOT IN ('Unknown', 'Other', 'PENDING_VERIFICATION') 
        """

        if department_id and department_id != 0: # Assuming 0 means "all" or "no specific department"
            query += " AND department_id = %s"
            params.append(department_id)
        
        query += " ORDER BY name ASC"
        cursor.execute(query, tuple(params))
        specializations = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching specializations list (dept: {department_id}): {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specializations


def get_filtered_doctors(search_name=None, specialization_id=None, department_id=None, accepting_new=None):
    """ 
    Fetches approved doctors based on filter criteria.
    """
    doctors_list = []
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT
                u.user_id, 
                u.first_name, 
                u.last_name,
                d.profile_photo_url,
                s.name AS specialization_name,
                dept.name AS department_name,
                d.accepting_new_patients
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            WHERE u.user_type = 'doctor'
              AND u.account_status = 'active'
              AND d.verification_status = 'approved' 
        """
        params = []

        if search_name:
            query += """ AND (
                            LOWER(u.first_name) LIKE LOWER(%s) OR 
                            LOWER(u.last_name) LIKE LOWER(%s) OR
                            LOWER(CONCAT(u.first_name, ' ', u.last_name)) LIKE LOWER(%s)
                        )"""
            like_term = f"%{search_name}%"
            params.extend([like_term, like_term, like_term])
        
        if department_id:
            query += " AND d.department_id = %s"
            params.append(department_id)
            # Only filter by specialization if a department is also selected,
            # and the specialization belongs to that department (implicitly handled by frontend logic)
            if specialization_id: 
                query += " AND d.specialization_id = %s"
                params.append(specialization_id)
        elif specialization_id: # If no department is selected, filter by specialization across all departments
            query += " AND d.specialization_id = %s"
            params.append(specialization_id)

        if accepting_new is not None:
            query += " AND d.accepting_new_patients = %s"
            params.append(bool(int(accepting_new))) # Ensure it's 0 or 1

        query += " ORDER BY u.last_name ASC, u.first_name ASC"
        
        cursor.execute(query, tuple(params))
        doctors_list = cursor.fetchall()

        default_pic_path = 'images/default_doctor.png' # Relative to static folder
        for doc in doctors_list:
            raw_path = doc.get('profile_photo_url')
            # Assuming profile_photo_url stores path like 'doctor_photos/filename.jpg'
            # and your static files are configured correctly so url_for can build it.
            if raw_path and not raw_path.startswith('/') and not raw_path.startswith(('http://', 'https://')):
                doc['profile_picture_processed_url'] = raw_path 
            else:
                if raw_path and (raw_path.startswith('/') or raw_path.startswith(('http://', 'https://'))):
                     current_app.logger.warning(f"Doctor {doc['user_id']} has an absolute or external profile_photo_url: {raw_path}. Using default.")
                doc['profile_picture_processed_url'] = default_pic_path
    
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching filtered doctors: {db_err}", exc_info=True)
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching filtered doctors: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctors_list

def get_full_doctor_profile(doctor_id):
    """Fetches detailed profile information for a single approved, active doctor, including documents."""
    conn = None; cursor = None; doctor_profile = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT
                u.user_id, 
                u.first_name, 
                u.last_name, 
                u.email,
                u.phone,
                d.profile_photo_url,
                d.biography,
                d.accepting_new_patients,
                dl.address AS clinic_address, 
                dl.city AS clinic_city,
                dl.state AS clinic_state,
                dl.zip_code AS clinic_zip_code,
                dl.phone_number AS clinic_phone,
                d.certifications,
                d.medical_school,
                d.graduation_year,
                s.name AS specialization_name,
                s.description AS specialization_description,
                dept.name AS department_name,
                dept.description AS department_description
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            LEFT JOIN doctor_locations dl ON d.user_id = dl.doctor_id AND dl.is_primary = 1 AND dl.is_active = 1
            WHERE u.user_id = %s
              AND u.user_type = 'doctor'
              AND u.account_status = 'active'
              AND d.verification_status = 'approved'
        """
        cursor.execute(query, (doctor_id,))
        doctor_profile = cursor.fetchone()

        if doctor_profile:
            raw_path = doctor_profile.get('profile_photo_url')
            default_pic_path = 'images/default_doctor.png'
            if raw_path and not raw_path.startswith('/') and not raw_path.startswith(('http://', 'https://')):
                doctor_profile['profile_picture_processed_url'] = raw_path
            else:
                if raw_path and (raw_path.startswith('/') or raw_path.startswith(('http://', 'https://'))):
                     current_app.logger.warning(f"Doctor {doctor_profile['user_id']} (profile view) has an absolute or external profile_photo_url: {raw_path}. Using default.")
                doctor_profile['profile_picture_processed_url'] = default_pic_path
            
            cursor.execute("""
                SELECT document_id, document_type, file_name, file_path, upload_date
                FROM doctor_documents
                WHERE doctor_id = %s
                ORDER BY document_type ASC, upload_date DESC
            """, (doctor_id,))
            documents = cursor.fetchall()
            doctor_profile['documents'] = []
            for doc in documents:
                # Construct a downloadable URL if files are served from static and path is relative
                # This is a placeholder; actual implementation depends on your file serving strategy
                # If UPLOAD_FOLDER_DOCS is 'static/doctor_uploads' and file_path is 'doc_id/filename.pdf'
                # doc['downloadable_url'] = url_for('static', filename=f'doctor_uploads/{doc["file_path"]}')
                # For now, just pass the raw file_path and handle display/linking in template
                # A secure download route is often better.
                doc['downloadable_url'] = "#" # Placeholder
                doctor_profile['documents'].append(doc)


    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching full doctor profile for ID {doctor_id}: {db_err}", exc_info=True)
        doctor_profile = None 
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching full doctor profile for ID {doctor_id}: {e}", exc_info=True)
        doctor_profile = None 
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_profile


# --- Routes ---
@doctor_bp.route('/')
@doctor_bp.route('/list')
def list_doctors():
    search_name = request.args.get('search_name', '').strip()
    department_id_str = request.args.get('department_id', '')
    specialization_id_str = request.args.get('specialization_id', '')
    accepting_new_str = request.args.get('accepting_new', '')

    department_id = int(department_id_str) if department_id_str.isdigit() else None
    specialization_id = int(specialization_id_str) if specialization_id_str.isdigit() else None
    
    accepting_new_filter = None
    if accepting_new_str == '1': accepting_new_filter = True
    elif accepting_new_str == '0': accepting_new_filter = False

    all_departments = get_all_departments_for_filter()
    
    specializations_for_dropdown = []
    if department_id:
        specializations_for_dropdown = get_specializations_by_department_for_filter(department_id)
    # If no department is selected, the JS will handle the "Select Department First" state

    doctors = get_filtered_doctors(
        search_name=search_name, 
        department_id=department_id,
        specialization_id=specialization_id,
        accepting_new=accepting_new_filter
    )

    is_logged_in = current_user.is_authenticated

    return render_template(
        'doctor_list.html',
        doctors=doctors,
        departments=all_departments,
        specializations_dropdown_data=specializations_for_dropdown,
        selected_name=search_name,
        selected_dept_id=department_id,
        selected_spec_id=specialization_id,
        selected_accepting_new=accepting_new_str,
        is_logged_in=is_logged_in
    )

@doctor_bp.route('/get-specializations/<int:department_id>')
def get_specializations_for_department_ajax(department_id):
    # Handle case where "All Departments" (value 0 or empty) might be passed
    if department_id == 0: # Assuming frontend sends 0 for "All Departments" in some contexts for specializations
        specs = get_specializations_by_department_for_filter(None) # Get all relevant specializations
    else:
        specs = get_specializations_by_department_for_filter(department_id)
    return jsonify([{'id': s['specialization_id'], 'name': s['name']} for s in specs])

@doctor_bp.route('/profile/<int:doctor_id>')
def view_doctor_profile(doctor_id):
    doctor = get_full_doctor_profile(doctor_id)
    if not doctor:
        flash("Doctor profile not found or unavailable.", "warning")
        return redirect(url_for('.list_doctors'))
    is_logged_in = current_user.is_authenticated
    return render_template(
        'doctor_profile.html',
        doctor=doctor,
        is_logged_in=is_logged_in
        )

# Example for a secure document download route (implement if needed)
# @doctor_bp.route('/download-document/<int:document_id>')
# @login_required # Or other permission check
# def download_document(document_id):
#     # 1. Fetch document record from DB to get file_path and original file_name
#     # 2. Perform permission checks (e.g., is current_user allowed to see this doc?)
#     # 3. Construct full path to the file using UPLOAD_FOLDER_DOCS
#     # 4. Use send_from_directory(directory, path, as_attachment=True, download_name=original_file_name)
#     # Example:
#     # conn = get_db_connection()
#     # cursor = conn.cursor(dictionary=True)
#     # cursor.execute("SELECT file_path, file_name FROM doctor_documents WHERE document_id = %s", (document_id,))
#     # doc_record = cursor.fetchone()
#     # cursor.close()
#     # conn.close()
#     # if not doc_record:
#     #     abort(404)
#     # docs_base_path = current_app.config.get('UPLOAD_FOLDER_DOCS') # e.g., 'instance/uploads/doctor_documents'
#     # return send_from_directory(docs_base_path, doc_record['file_path'], as_attachment=True, download_name=doc_record['file_name'])
#     flash("Document download not yet implemented.", "info")
#     return redirect(request.referrer or url_for('.list_doctors'))