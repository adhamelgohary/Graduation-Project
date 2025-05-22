# your_project/routes/Doctor_Portal/disease_management.py

import mysql.connector
import re
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection
from datetime import date, datetime
import math

# --- Internalized Utils (Keep as they are from your provided file) ---
# ... (check_doctor_authorization, get_enum_values, get_all_simple) ...
def check_doctor_authorization(user):
    return user.is_authenticated and getattr(user, 'user_type', None) == 'doctor'

def get_enum_values(table_name, column_name):
    conn = None; cursor = None; enum_values = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        safe_table_name = '`' + table_name.replace('`', '``') + '`'
        safe_column_name = column_name.replace("'", "''")
        query = f"SHOW COLUMNS FROM {safe_table_name} LIKE '{safe_column_name}'"
        cursor.execute(query); result = cursor.fetchone()
        if result and 'Type' in result:
            type_info = result['Type']
            match = re.match(r"enum\((.*)\)", type_info, re.IGNORECASE)
            if match:
                enum_values = [val.strip().strip("'") for val in match.group(1).split(',')]
    except Exception as e: current_app.logger.error(f"Error getting ENUM {table_name}.{column_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return enum_values

def get_all_simple(table_name, id_column, name_column, order_by_name=True):
    conn = None; cursor = None; results = []
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name) or \
       not re.match(r'^[a-zA-Z0-9_]+$', id_column) or \
       not re.match(r'^[a-zA-Z0-9_]+$', name_column):
        current_app.logger.error(f"Invalid table/col name in get_all_simple: {table_name}, {id_column}, {name_column}")
        return []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        safe_table, safe_id_col, safe_name_col = f"`{table_name}`", f"`{id_column}`", f"`{name_column}`"
        order_clause = f"ORDER BY {safe_name_col} ASC" if order_by_name else ""
        query = f"SELECT {safe_id_col}, {safe_name_col} FROM {safe_table} {order_clause}"
        cursor.execute(query); results = cursor.fetchall()
    except Exception as e: current_app.logger.error(f"Error in get_all_simple for {table_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return results


# --- Blueprint Definition ---
disease_management_bp = Blueprint(
    'disease_management',
    __name__,
    url_prefix='/doctor/diseases',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 15
VALID_SORT_COLUMNS = {
    'name': 'c.condition_name', 'code': 'c.icd_code', 'type': 'c.condition_type',
    'urgency': 'c.urgency_level', 'id': 'c.condition_id', 'dept': 'd.name',
    'test_type': 'tt.name', 'diag_type': 'dt.name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'


# --- Updated File Handling Helpers ---
def _allowed_file_generic(filename, config_extensions_key):
    """Generic file extension checker."""
    allowed_extensions = current_app.config.get(config_extensions_key)
    if not allowed_extensions:
        current_app.logger.warning(f"Config key {config_extensions_key} for allowed extensions not found.")
        return False # Or True if you want to allow all by default when not configured
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def _save_file_generic(file_storage_object, upload_folder_config_key, allowed_extensions_config_key, sub_folder_name=""):
    """Generic file saver, returns relative DB path and error message."""
    upload_folder_abs = current_app.config.get(upload_folder_config_key)
    if not upload_folder_abs:
        return None, f"Server config error: '{upload_folder_config_key}' not set."

    if not file_storage_object or not file_storage_object.filename:
        return None, "No file selected."

    if not _allowed_file_generic(file_storage_object.filename, allowed_extensions_config_key):
        allowed_ext_str = ", ".join(current_app.config.get(allowed_extensions_config_key, {'N/A'}))
        return None, f"File type not allowed. Allowed: {allowed_ext_str}."

    original_filename = secure_filename(file_storage_object.filename)
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base_name_part = original_filename.rsplit('.',1)[0][:50] if '.' in original_filename else original_filename[:50]
    unique_filename_stem = f"{timestamp}_{secure_filename(base_name_part)}" # Ensure base_name_part is also secured
    unique_filename = f"{unique_filename_stem}.{ext}" if ext else unique_filename_stem
    
    # Ensure sub_folder_name (like 'condition_images') exists within the static UPLOAD_FOLDER_BASE
    # The save_disease_image/video functions will handle the specific subfolder.
    # For this generic helper, we assume upload_folder_abs is the final destination.
    
    filepath_abs = os.path.join(upload_folder_abs, unique_filename)

    try:
        os.makedirs(upload_folder_abs, exist_ok=True)
        file_storage_object.save(filepath_abs)

        # Use the get_relative_upload_path helper from directory_configs
        # Assumes directory_configs is imported and available
        # from utils.directory_configs import get_relative_upload_path
        # For now, let's manually construct it based on knowing structure:
        # 'uploads' / sub_folder_name / unique_filename
        # The sub_folder_name is part of upload_folder_abs already if UPLOAD_FOLDER_CONDITIONS points to static/uploads/condition_images
        
        static_base_uploads = current_app.config.get('UPLOAD_FOLDER_BASE')
        if not static_base_uploads:
             raise Exception("UPLOAD_FOLDER_BASE not configured.")
        
        # Get path relative to UPLOAD_FOLDER_BASE
        relative_to_base = os.path.relpath(filepath_abs, static_base_uploads)
        # Prepend 'uploads/' to make it relative to 'static/'
        db_path = os.path.join('uploads', relative_to_base).replace(os.path.sep, '/')

        current_app.logger.info(f"File saved. Absolute: {filepath_abs}, DB_Path: {db_path}")
        return db_path, None
    except Exception as e:
        current_app.logger.error(f"File save failed for {unique_filename}: {e}", exc_info=True)
        if os.path.exists(filepath_abs):
            try: os.remove(filepath_abs)
            except OSError: pass
        return None, f"File save operation failed: {str(e)}"

def _delete_file_generic(db_path_relative_to_static):
    """Generic file deleter based on path relative to static folder."""
    if not db_path_relative_to_static: return False, "No filename provided."
    
    static_folder_abs = current_app.config.get('STATIC_FOLDER')
    if not static_folder_abs:
        current_app.logger.error("STATIC_FOLDER not configured for deletion.")
        return False, "Server configuration error (static path)."

    # Sanitize path: remove leading slashes, prevent traversal
    clean_relative_path = db_path_relative_to_static.lstrip('/').lstrip('\\')
    if '..' in clean_relative_path:
        current_app.logger.warning(f"Attempt to delete potentially unsafe path: {clean_relative_path}")
        return False, "Invalid file path."

    filepath_abs = os.path.join(static_folder_abs, clean_relative_path)
    
    # Security check: ensure the resolved path is still within the static folder
    if not os.path.abspath(filepath_abs).startswith(os.path.abspath(static_folder_abs)):
        current_app.logger.error(f"Path traversal attempt detected for deletion: {filepath_abs}")
        return False, "Security error: Path is outside designated static folder."

    try:
        if os.path.exists(filepath_abs) and os.path.isfile(filepath_abs):
            os.remove(filepath_abs)
            current_app.logger.info(f"File deleted: {filepath_abs}")
            return True, "File deleted successfully."
        else:
            current_app.logger.warning(f"File not found for deletion: {filepath_abs}")
            return False, "File not found on server."
    except Exception as e:
        current_app.logger.error(f"Error deleting file {filepath_abs}: {e}", exc_info=True)
        return False, f"Error during file deletion: {str(e)}"


# Specific wrappers for image and video
def save_condition_image(file_storage):
    return _save_file_generic(file_storage, 'UPLOAD_FOLDER_CONDITIONS', 'ALLOWED_IMAGE_EXTENSIONS')

def delete_condition_image(db_path):
    return _delete_file_generic(db_path)

def save_condition_video(file_storage):
    return _save_file_generic(file_storage, 'UPLOAD_FOLDER_CONDITION_VIDEOS', 'ALLOWED_VIDEO_EXTENSIONS')

def delete_condition_video(db_path):
    return _delete_file_generic(db_path)


# --- Data Fetching Helpers (Using internalized utils) ---
def get_all_departments(): return get_all_simple('departments', 'department_id', 'name')
def get_all_testing_types(): return get_all_simple('testing_types', 'testing_type_id', 'name')
def get_all_diagnosis_types(): return get_all_simple('diagnosis_types', 'diagnosis_type_id', 'name')

def get_paginated_diseases(page=1, per_page=ITEMS_PER_PAGE, search_term=None,
                         sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION,
                         filters=None, doctor_department_id=None):
    # ... (no changes from your provided code) ...
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page; valid_filters = filters or {}
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql_select = """SELECT SQL_CALC_FOUND_ROWS
                            c.condition_id, c.condition_name, c.icd_code,
                            c.condition_type, c.urgency_level, d.name as department_name,
                            c.condition_image_filename, c.condition_video_filename 
                        """ # Added video filename
        sql_from = """ FROM conditions c
                       LEFT JOIN departments d ON c.department_id = d.department_id
                       LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id
                       LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id
                   """
        sql_where = " WHERE c.is_active = TRUE"; params = []
        if doctor_department_id is not None:
            sql_where += " AND c.department_id = %s"; params.append(doctor_department_id)
        if search_term:
            search_like = f"%{search_term}%"
            sql_where += """ AND (c.condition_name LIKE %s OR c.icd_code LIKE %s OR c.description LIKE %s
                                  OR c.regular_symptoms_text LIKE %s OR c.emergency_symptoms_text LIKE %s
                                  OR c.overview LIKE %s OR c.causes_text LIKE %s OR c.complications_text LIKE %s) """
            params.extend([search_like] * 8)

        if valid_filters.get('urgency'): sql_where += " AND c.urgency_level = %s"; params.append(valid_filters['urgency'])
        if valid_filters.get('type'): sql_where += " AND c.condition_type = %s"; params.append(valid_filters['type'])

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset]); cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); result['total'] = cursor.fetchone()['total']
    except Exception as err: current_app.logger.error(f"Error in get_paginated_diseases: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result


def get_disease_details_full(condition_id):
    # ... (add condition_video_filename to SELECT) ...
    conn = None; cursor = None; details = {'condition': None, 'associated_doctors': []}
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """SELECT c.*, tt.name as testing_type_name, dt.name as diagnosis_type_name, d.name as department_name
                 FROM conditions c
                 LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id
                 LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id
                 LEFT JOIN departments d ON c.department_id = d.department_id
                 WHERE c.condition_id = %s AND c.is_active = TRUE""" # Ensure condition_video_filename is selected by c.*
        cursor.execute(sql, (condition_id,)); details['condition'] = cursor.fetchone()
        if not details['condition']: return None
        department_id = details['condition'].get('department_id')
        if department_id:
            sql_doctors = """SELECT doc.user_id as doctor_user_id, u.first_name, u.last_name, s.name as specialization_name
                             FROM doctors doc JOIN users u ON doc.user_id = u.user_id
                             LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
                             WHERE doc.department_id = %s AND u.user_type = 'doctor' AND u.account_status = 'active'
                             ORDER BY u.last_name"""
            cursor.execute(sql_doctors, (department_id,)); details['associated_doctors'] = cursor.fetchall()
    except Exception as err: current_app.logger.error(f"Error in get_disease_details_full ID {condition_id}: {err}", exc_info=True); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details


def get_disease_details_basic(condition_id): # Used for pre-filling edit form
    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        # Ensure all relevant fields, including video filename, are fetched
        cursor.execute("SELECT * FROM conditions WHERE condition_id = %s AND is_active = TRUE", (condition_id,))
        return cursor.fetchone()
    except Exception as err: current_app.logger.error(f"Error in get_disease_details_basic ID {condition_id}: {err}", exc_info=True); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return


# --- Routes ---
@disease_management_bp.route('/', methods=['GET'])
@login_required
def list_diseases():
    # ... (no changes from your provided code, ensure it passes request_args to template for pagination) ...
    if not check_doctor_authorization(current_user): abort(403)
    doctor_department_id = None; doctor_department_name = "All Departments"
    conn_dept = None; cursor_dept = None
    try:
        conn_dept = get_db_connection(); cursor_dept = conn_dept.cursor(dictionary=True)
        sql_get_doctor_dept = "SELECT doc.department_id, dep.name as department_name FROM doctors doc JOIN departments dep ON doc.department_id = dep.department_id WHERE doc.user_id = %s"
        cursor_dept.execute(sql_get_doctor_dept, (current_user.id,))
        doctor_info = cursor_dept.fetchone()
        if doctor_info:
            doctor_department_id = doctor_info.get('department_id')
            doctor_department_name = doctor_info.get('department_name', "Assigned Department")
            if not doctor_department_id: doctor_department_name = "Department Not Assigned"
        else: current_app.logger.warning(f"No doctor record for user_id {current_user.id}.")
    except Exception as e: current_app.logger.error(f"Error fetching department: {e}", exc_info=True); flash("Error retrieving department.", "warning")
    finally:
        if cursor_dept: cursor_dept.close()
        if conn_dept and conn_dept.is_connected(): conn_dept.close()

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    filters = {k: request.args.get(f'filter_{k}') for k in ['urgency', 'type'] if request.args.get(f'filter_{k}')}
    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION
    result = get_paginated_diseases(page=page, per_page=ITEMS_PER_PAGE, search_term=search, sort_by=sort_by, sort_dir=sort_dir, filters=filters, doctor_department_id=doctor_department_id)
    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and result['total'] > 0 else 0
    filter_options = {
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
    }
    return render_template('Doctor_Portal/Diseases/disease_list.html', diseases=result['items'], search_term=search, current_page=page, total_pages=total_pages, sort_by=sort_by, sort_dir=sort_dir, filters=filters, valid_sort_columns=VALID_SORT_COLUMNS, doctor_department_name=doctor_department_name, **filter_options, request_args=request.args)


@disease_management_bp.route('/<int:condition_id>', methods=['GET'])
@login_required
def view_disease(condition_id):
    # ... (no changes from your provided code) ...
    if not check_doctor_authorization(current_user): abort(403)
    details = get_disease_details_full(condition_id)
    if not details or not details['condition']: flash("Condition not found or is inactive.", "warning"); return redirect(url_for('.list_diseases'))
    return render_template('Doctor_Portal/Diseases/disease_detail.html', details=details)


@disease_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_disease():
    if not check_doctor_authorization(current_user): abort(403)
    dropdown_options = { # ... (no changes from your provided code) ...
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
        'gender_relevance_opts': get_enum_values('conditions', 'gender_relevance'),
        'departments': get_all_departments(),
        'testing_types': get_all_testing_types(),
        'diagnosis_types': get_all_diagnosis_types(),
    }
    if request.method == 'POST':
        conn = None; cursor = None; errors = []; 
        db_path_for_image = None
        db_path_for_video = None # <-- NEW for video
        try:
            form = request.form
            condition_name = form.get('condition_name', '').strip()
            # ... (collect all other form data as before) ...
            description = form.get('description','').strip() or None
            icd_code = form.get('icd_code','').strip() or None
            urgency_level = form.get('urgency_level') # String value from select
            condition_type = form.get('condition_type') or None # String or None if empty option selected
            age_relevance = form.get('age_relevance','').strip() or None
            gender_relevance = form.get('gender_relevance') # String value from select
            specialist_type = form.get('specialist_type','').strip() or None
            self_treatable = form.get('self_treatable') == 'on' # Boolean
            typical_duration = form.get('typical_duration','').strip() or None
            educational_content = form.get('educational_content','').strip() or None
            overview = form.get('overview','').strip() or None
            causes_text = form.get('causes_text','').strip() or None
            complications_text = form.get('complications_text','').strip() or None
            testing_details = form.get('testing_details','').strip() or None
            diagnosis_details = form.get('diagnosis_details','').strip() or None
            testing_type_id_str = form.get('testing_type_id', '')
            testing_type_id = int(testing_type_id_str) if testing_type_id_str.isdigit() else None
            diagnosis_type_id_str = form.get('diagnosis_type_id', '')
            diagnosis_type_id = int(diagnosis_type_id_str) if diagnosis_type_id_str.isdigit() else None
            department_id_str = form.get('department_id', '')
            department_id = int(department_id_str) if department_id_str.isdigit() else None
            regular_symptoms_text = form.get('regular_symptoms_text','').strip() or None
            emergency_symptoms_text = form.get('emergency_symptoms_text','').strip() or None
            risk_factors_text = form.get('risk_factors_text','').strip() or None
            treatment_protocols_text = form.get('treatment_protocols_text','').strip() or None

            # --- Validation (as before) ---
            if not condition_name: errors.append("Condition Name is required.")
            # ... (other validations) ...
            if not urgency_level or urgency_level not in dropdown_options.get('urgency_levels', []): errors.append("Valid Urgency Level required.")
            if not gender_relevance or gender_relevance not in dropdown_options.get('gender_relevance_opts', []): errors.append("Valid Gender Relevance required.")


            # --- File Handling for Image ---
            image_file = request.files.get('disease_image')
            if image_file and image_file.filename:
                db_path_for_image, file_error = save_condition_image(image_file) # Use specific saver
                if file_error: errors.append(f"Image Error: {file_error}")
            
            # --- NEW: File Handling for Video ---
            video_file = request.files.get('condition_video') # New input field name
            if video_file and video_file.filename:
                db_path_for_video, video_error = save_condition_video(video_file) # Use specific saver
                if video_error: errors.append(f"Video Error: {video_error}")

            if errors: raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_insert_condition = """
                INSERT INTO conditions (
                    condition_name, description, icd_code, urgency_level, condition_type,
                    age_relevance, gender_relevance, specialist_type, self_treatable,
                    typical_duration, educational_content, overview, causes_text, complications_text,
                    testing_details, diagnosis_details, 
                    condition_image_filename, condition_video_filename, -- Removed invalid comment
                    testing_type_id, diagnosis_type_id, department_id,
                    regular_symptoms_text, emergency_symptoms_text,
                    risk_factors_text, treatment_protocols_text,
                    is_active, created_at, updated_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s, %s, -- Placeholder for video filename
                    %s,%s,%s,%s,%s,%s,%s,TRUE,NOW(),NOW()
                )
            """
            params_condition = (
                condition_name, description, icd_code, urgency_level, condition_type,
                age_relevance, gender_relevance, specialist_type, self_treatable,
                typical_duration, educational_content, overview, causes_text, complications_text,
                testing_details, diagnosis_details, 
                db_path_for_image, db_path_for_video, # Values for image and video
                testing_type_id, diagnosis_type_id, department_id,
                regular_symptoms_text, emergency_symptoms_text,
                risk_factors_text, treatment_protocols_text
            )
            cursor.execute(sql_insert_condition, params_condition)
            new_condition_id = cursor.lastrowid
            if not new_condition_id: conn.rollback(); raise mysql.connector.Error("Failed to insert condition.")
            conn.commit(); flash(f"Condition '{condition_name}' added.", "success")
            return redirect(url_for('.view_disease', condition_id=new_condition_id))
        
        except ValueError: # Catches validation errors
            if db_path_for_image: delete_condition_image(db_path_for_image)
            if db_path_for_video: delete_condition_video(db_path_for_video) # Delete uploaded video on error
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if db_path_for_image: delete_condition_image(db_path_for_image)
            if db_path_for_video: delete_condition_video(db_path_for_video)
            current_app.logger.error(f"DB/IO Error Add Cond: {err}", exc_info=True); flash(f"DB/File error: {getattr(err, 'msg', str(err))}", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if db_path_for_image: delete_condition_image(db_path_for_image)
            if db_path_for_video: delete_condition_video(db_path_for_video)
            current_app.logger.error(f"Unexpected Error Add Cond: {e}", exc_info=True); flash("Unexpected error.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.add_disease'), form_title="Add New Condition", disease=request.form, errors=errors, **dropdown_options)
    
    return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.add_disease'), form_title="Add New Condition", disease=None, **dropdown_options)


@disease_management_bp.route('/<int:condition_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_disease(condition_id):
    if not check_doctor_authorization(current_user): abort(403)
    dropdown_options = { # ... (same as in add_disease) ...
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
        'gender_relevance_opts': get_enum_values('conditions', 'gender_relevance'),
        'departments': get_all_departments(),
        'testing_types': get_all_testing_types(),
        'diagnosis_types': get_all_diagnosis_types(),
    }
    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        # Get current file paths from hidden form fields
        current_image_db_path = request.form.get('current_condition_image_filename')
        current_video_db_path = request.form.get('current_condition_video_filename') # <-- NEW
        
        newly_saved_image_db_path = None
        newly_saved_video_db_path = None # <-- NEW

        # Start with current paths, update if new files are uploaded or old ones deleted
        image_path_for_db_update = current_image_db_path
        video_path_for_db_update = current_video_db_path # <-- NEW

        try:
            form = request.form
            condition_name = form.get('condition_name', '').strip()
            # ... (collect all other form data as before) ...
            description = form.get('description','').strip() or None
            icd_code = form.get('icd_code','').strip() or None
            urgency_level = form.get('urgency_level')
            condition_type = form.get('condition_type') or None
            age_relevance = form.get('age_relevance','').strip() or None
            gender_relevance = form.get('gender_relevance')
            specialist_type = form.get('specialist_type','').strip() or None
            self_treatable = form.get('self_treatable') == 'on'
            typical_duration = form.get('typical_duration','').strip() or None
            educational_content = form.get('educational_content','').strip() or None
            overview = form.get('overview','').strip() or None
            causes_text = form.get('causes_text','').strip() or None
            complications_text = form.get('complications_text','').strip() or None
            testing_details = form.get('testing_details','').strip() or None
            diagnosis_details = form.get('diagnosis_details','').strip() or None
            testing_type_id_str = form.get('testing_type_id', '')
            testing_type_id = int(testing_type_id_str) if testing_type_id_str.isdigit() else None
            diagnosis_type_id_str = form.get('diagnosis_type_id', '')
            diagnosis_type_id = int(diagnosis_type_id_str) if diagnosis_type_id_str.isdigit() else None
            department_id_str = form.get('department_id', '')
            department_id = int(department_id_str) if department_id_str.isdigit() else None
            regular_symptoms_text = form.get('regular_symptoms_text','').strip() or None
            emergency_symptoms_text = form.get('emergency_symptoms_text','').strip() or None
            risk_factors_text = form.get('risk_factors_text','').strip() or None
            treatment_protocols_text = form.get('treatment_protocols_text','').strip() or None


            # --- Image Handling ---
            image_file = request.files.get('disease_image')
            delete_current_image_flag = request.form.get('delete_image') == 'on'

            if delete_current_image_flag:
                if current_image_db_path:
                    deleted_ok, msg = delete_condition_image(current_image_db_path)
                    if deleted_ok: image_path_for_db_update = None
                    else: errors.append(f"Failed to delete current image: {msg}")
                else: image_path_for_db_update = None # Already no image
            elif image_file and image_file.filename: # New image uploaded
                newly_saved_image_db_path, file_error = save_condition_image(image_file)
                if file_error: errors.append(f"Image upload failed: {file_error}")
                else:
                    # If new image saved successfully, delete old one (if exists and different)
                    if current_image_db_path and current_image_db_path != newly_saved_image_db_path:
                        delete_condition_image(current_image_db_path)
                    image_path_for_db_update = newly_saved_image_db_path
            
            # --- NEW: Video Handling ---
            video_file = request.files.get('condition_video')
            delete_current_video_flag = request.form.get('delete_video') == 'on'

            if delete_current_video_flag:
                if current_video_db_path:
                    deleted_ok, msg = delete_condition_video(current_video_db_path)
                    if deleted_ok: video_path_for_db_update = None
                    else: errors.append(f"Failed to delete current video: {msg}")
                else: video_path_for_db_update = None # Already no video
            elif video_file and video_file.filename: # New video uploaded
                newly_saved_video_db_path, video_error = save_condition_video(video_file)
                if video_error: errors.append(f"Video upload failed: {video_error}")
                else:
                    if current_video_db_path and current_video_db_path != newly_saved_video_db_path:
                        delete_condition_video(current_video_db_path)
                    video_path_for_db_update = newly_saved_video_db_path
            
            # --- Validation ---
            if not condition_name: errors.append("Condition Name required.")
            # ... (other validations as before) ...
            if errors:
                # If new files were saved but validation failed, delete them
                if newly_saved_image_db_path: delete_condition_image(newly_saved_image_db_path)
                if newly_saved_video_db_path: delete_condition_video(newly_saved_video_db_path)
                raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_update_condition = """
                UPDATE conditions SET
                    condition_name=%s, description=%s, icd_code=%s, urgency_level=%s, condition_type=%s,
                    age_relevance=%s, gender_relevance=%s, specialist_type=%s, self_treatable=%s,
                    typical_duration=%s, educational_content=%s, overview=%s, causes_text=%s, complications_text=%s,
                    testing_details=%s, diagnosis_details=%s, 
                    condition_image_filename=%s, condition_video_filename=%s, -- Removed invalid comment
                    testing_type_id=%s, diagnosis_type_id=%s, department_id=%s,
                    regular_symptoms_text=%s, emergency_symptoms_text=%s,
                    risk_factors_text=%s, treatment_protocols_text=%s,
                    updated_at=NOW()
                WHERE condition_id=%s AND is_active=TRUE """
            params_condition = (
                condition_name, description, icd_code, urgency_level, condition_type,
                age_relevance, gender_relevance, specialist_type, self_treatable,
                typical_duration, educational_content, overview, causes_text, complications_text,
                testing_details, diagnosis_details, 
                image_path_for_db_update, video_path_for_db_update, # Values for image and video
                testing_type_id, diagnosis_type_id, department_id,
                regular_symptoms_text, emergency_symptoms_text,
                risk_factors_text, treatment_protocols_text,
                condition_id
            )
            cursor.execute(sql_update_condition, params_condition)
            conn.commit(); flash(f"Condition '{condition_name}' updated.", "success")
            return redirect(url_for('.view_disease', condition_id=condition_id))
        
        except ValueError: # Catches validation errors
             # No need to delete newly_saved files here as it's done before raising ValueError
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            # If DB error AFTER a new file was saved but BEFORE old one was meant to be deleted,
            # the new file might be orphaned. This logic is complex.
            # For simplicity, we only delete newly_saved_image/video_db_path if they are different from current.
            if newly_saved_image_db_path and newly_saved_image_db_path != current_image_db_path: delete_condition_image(newly_saved_image_db_path)
            if newly_saved_video_db_path and newly_saved_video_db_path != current_video_db_path: delete_condition_video(newly_saved_video_db_path)
            current_app.logger.error(f"DB/IO Error Edit Cond {condition_id}: {err}", exc_info=True); flash("DB/File error.", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if newly_saved_image_db_path and newly_saved_image_db_path != current_image_db_path: delete_condition_image(newly_saved_image_db_path)
            if newly_saved_video_db_path and newly_saved_video_db_path != current_video_db_path: delete_condition_video(newly_saved_video_db_path)
            current_app.logger.error(f"Unexpected Error Edit Cond {condition_id}: {e}", exc_info=True); flash("Error.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        
        # Repopulate form on error
        form_data_on_error = request.form.to_dict()
        form_data_on_error['condition_id'] = condition_id
        # Ensure current file paths are passed back correctly, considering potential deletions/new uploads
        form_data_on_error['condition_image_filename'] = image_path_for_db_update 
        form_data_on_error['condition_video_filename'] = video_path_for_db_update # <-- NEW
        return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.edit_disease', condition_id=condition_id), form_title=f"Edit Condition (ID: {condition_id})", disease=form_data_on_error, errors=errors, **dropdown_options)

    # GET request
    disease_data = get_disease_details_basic(condition_id)
    if not disease_data: flash("Condition not found or is inactive.", "warning"); return redirect(url_for('.list_diseases'))
    return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.edit_disease', condition_id=condition_id), form_title=f"Edit: {disease_data.get('condition_name', 'N/A')}", disease=disease_data, **dropdown_options)


@disease_management_bp.route('/<int:condition_id>/delete', methods=['POST']) # Changed to POST for semantic delete
@login_required
def delete_disease(condition_id): # Renamed from deactivate
    if not check_doctor_authorization(current_user): abort(403)
    conn = None; cursor = None
    try:
        # Fetch file paths before deactivating/deleting record to clean up files
        disease_data = get_disease_details_basic(condition_id) # Fetches active records
        if not disease_data:
            flash("Condition not found or already inactive/deleted.", "warning")
            return redirect(url_for('.list_diseases'))

        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        
        # Option 1: Soft Delete (set is_active = FALSE) - SAFER
        cursor.execute("UPDATE conditions SET is_active = FALSE, updated_at = NOW() WHERE condition_id = %s", (condition_id,))
        action_msg = "deactivated"
        
        # Option 2: Hard Delete (REMOVE FROM DB) - MORE RISKY, breaks FKs if not handled
        # cursor.execute("DELETE FROM conditions WHERE condition_id = %s", (condition_id,))
        # action_msg = "deleted"
        # if cursor.rowcount > 0:
        #     if disease_data.get('condition_image_filename'):
        #         delete_condition_image(disease_data['condition_image_filename'])
        #     if disease_data.get('condition_video_filename'): # <-- NEW
        #         delete_condition_video(disease_data['condition_video_filename'])

        if cursor.rowcount == 0:
            flash(f"Condition not found or could not be {action_msg}.", "warning")
            conn.rollback()
        else:
            conn.commit()
            flash(f"Condition successfully {action_msg}.", "success")
            
    except Exception as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        current_app.logger.error(f"Error {action_msg} condition {condition_id}: {err}", exc_info=True)
        flash(f"Error {action_msg} condition.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_diseases'))


# --- Route to serve condition images (as before) ---
@disease_management_bp.route('/images/<path:image_filename_in_db>')
def serve_condition_image(image_filename_in_db):
    # ... (no change from your provided code) ...
    static_dir_abs = current_app.config.get('STATIC_FOLDER')
    if not static_dir_abs: abort(500)
    if '..' in image_filename_in_db or image_filename_in_db.startswith(('/', '\\')): abort(400)
    try:
        return send_from_directory(static_dir_abs, image_filename_in_db, as_attachment=False)
    except FileNotFoundError: abort(404)
    except Exception as e: current_app.logger.error(f"Error serving image {image_filename_in_db}: {e}", exc_info=True); abort(500)


# --- NEW Route to serve condition videos ---
@disease_management_bp.route('/videos/<path:video_filename_in_db>')
def serve_condition_video(video_filename_in_db):
    """Serves video files stored relative to the STATIC_FOLDER."""
    static_dir_abs = current_app.config.get('STATIC_FOLDER')
    if not static_dir_abs:
        current_app.logger.error("STATIC_FOLDER not configured for serving videos.")
        abort(500)

    # Basic path sanitation
    if '..' in video_filename_in_db or video_filename_in_db.startswith(('/', '\\')):
        current_app.logger.warning(f"Attempt to access potentially unsafe video path: {video_filename_in_db}")
        abort(400)
    
    try:
        # send_from_directory expects path relative to its first argument (directory)
        # Since db_path_for_video is already 'uploads/condition_videos/filename.mp4' (relative to static)
        # we pass static_dir_abs as the directory and video_filename_in_db as the path within it.
        current_app.logger.info(f"Attempting to serve video: {video_filename_in_db} from {static_dir_abs}")
        return send_from_directory(static_dir_abs, video_filename_in_db, as_attachment=False)
    except FileNotFoundError:
        current_app.logger.error(f"Video file not found: {os.path.join(static_dir_abs, video_filename_in_db)}")
        abort(404)
    except Exception as e:
        current_app.logger.error(f"Error serving video {video_filename_in_db}: {e}", exc_info=True)
        abort(500)