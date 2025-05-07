# your_project/routes/Doctor_Portal/disease_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection # Assuming this is your DB helper
from datetime import date, datetime
import math

# Adjust import based on your project structure for utils
from .utils import (
    check_doctor_authorization,
    get_provider_id,
    get_enum_values,
    get_all_simple # Assuming get_all_simple is correctly defined here or imported
)

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

# --- Helper Functions for File Handling ---

def custom_allowed_file(filename, allowed_extensions_key='ALLOWED_IMAGE_EXTENSIONS'):
    """Checks if a filename has an allowed extension based on app config."""
    allowed_extensions = current_app.config.get(allowed_extensions_key)
    if not allowed_extensions:
        current_app.logger.warning(
            f"'{allowed_extensions_key}' not found in app config. Defaulting to allow (potentially unsafe)."
        )
        return True
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_disease_image(file_storage_object):
    """
    Saves the uploaded image file for a disease/condition securely.
    Returns (path_for_db, error_message_or_None).
    path_for_db is relative to the 'static' folder.
    """
    upload_folder_abs = current_app.config.get('UPLOAD_FOLDER_CONDITIONS')
    if not upload_folder_abs:
        current_app.logger.error("UPLOAD_FOLDER_CONDITIONS not configured in Flask app.")
        return None, "Server configuration error: Upload folder not set."

    if not file_storage_object or not file_storage_object.filename:
        return None, "No file selected or filename is empty."

    if not custom_allowed_file(file_storage_object.filename, 'ALLOWED_IMAGE_EXTENSIONS'):
        allowed_ext_str = ", ".join(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'N/A'}))
        return None, f"File type not allowed. Allowed: {allowed_ext_str}."

    original_filename = secure_filename(file_storage_object.filename)
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base_name_part = original_filename.rsplit('.',1)[0][:50] if '.' in original_filename else original_filename[:50]
    unique_filename_stem = f"{timestamp}_{base_name_part}"
    unique_filename = f"{secure_filename(unique_filename_stem)}.{ext}" if ext else secure_filename(unique_filename_stem)
    filepath_abs = os.path.join(upload_folder_abs, unique_filename)

    try:
        os.makedirs(upload_folder_abs, exist_ok=True)
        file_storage_object.save(filepath_abs)
        static_folder_abs = current_app.config.get('STATIC_FOLDER')
        if not static_folder_abs: raise Exception("STATIC_FOLDER not configured.")
        if not os.path.abspath(filepath_abs).startswith(os.path.abspath(static_folder_abs)):
            raise Exception(f"Saved file '{filepath_abs}' not in static folder '{static_folder_abs}'.")
        db_path = os.path.relpath(filepath_abs, static_folder_abs).replace(os.path.sep, '/')
        current_app.logger.info(f"Saved image: {filepath_abs}, DB path: {db_path}")
        return db_path, None
    except Exception as e:
        current_app.logger.error(f"Save image failed {unique_filename}: {e}", exc_info=True)
        if os.path.exists(filepath_abs):
            try: os.remove(filepath_abs)
            except OSError: pass
        return None, f"Save failed: {str(e)}"

def delete_disease_image(filename_relative_to_static):
    """
    Deletes an image file using the path stored in DB (relative to static folder).
    Returns (boolean_success, message_string).
    """
    if not filename_relative_to_static: return False, "No filename."
    static_folder_abs = current_app.config.get('STATIC_FOLDER')
    if not static_folder_abs: return False, "Server config error."
    normalized_relative_path = os.path.normpath(filename_relative_to_static)
    if normalized_relative_path.startswith(os.pardir) or os.path.isabs(normalized_relative_path):
        return False, "Invalid path."
    filepath_abs = os.path.join(static_folder_abs, normalized_relative_path)
    if not os.path.abspath(filepath_abs).startswith(os.path.abspath(static_folder_abs)):
        return False, "Security path error."
    try:
        if os.path.exists(filepath_abs) and os.path.isfile(filepath_abs):
            os.remove(filepath_abs)
            current_app.logger.info(f"Deleted image: {filepath_abs}")
            return True, "Deleted."
        else: return False, "Not found."
    except Exception as e:
        current_app.logger.error(f"Delete image error {filename_relative_to_static}: {e}", exc_info=True)
        return False, f"Error: {str(e)}"

# --- Data Fetching Helpers ---
# Make sure these calls exactly match your DB column names for the NAME field
def get_all_departments(): return get_all_simple('departments', 'department_id', 'name')
def get_all_testing_types(): return get_all_simple('testing_types', 'testing_type_id', 'name')
def get_all_diagnosis_types(): return get_all_simple('diagnosis_types', 'diagnosis_type_id', 'name')
def get_all_symptoms(): return get_all_simple('symptoms', 'symptom_id', 'symptom_name')
def get_all_risk_factors(): return get_all_simple('risk_factors', 'factor_id', 'factor_name')
def get_all_protocols(): return get_all_simple('treatment_protocols', 'protocol_id', 'protocol_name')


def get_paginated_diseases(page=1, per_page=ITEMS_PER_PAGE, search_term=None,
                         sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION,
                         filters=None, doctor_department_id=None):
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page; valid_filters = filters or {}
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql_select = "SELECT SQL_CALC_FOUND_ROWS c.condition_id, c.condition_name, c.icd_code, c.condition_type, c.urgency_level, d.name as department_name, tt.name as testing_type_name, dt.name as diagnosis_type_name, c.condition_image_filename"
        sql_from = " FROM conditions c LEFT JOIN departments d ON c.department_id = d.department_id LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id"
        sql_where = " WHERE c.is_active = TRUE"; params = []
        if doctor_department_id is not None: sql_where += " AND c.department_id = %s"; params.append(doctor_department_id)
        if search_term: search_like = f"%{search_term}%"; sql_where += " AND (c.condition_name LIKE %s OR c.icd_code LIKE %s)"; params.extend([search_like]*2)
        if valid_filters.get('urgency'): sql_where += " AND c.urgency_level = %s"; params.append(valid_filters['urgency'])
        if valid_filters.get('type'): sql_where += " AND c.condition_type = %s"; params.append(valid_filters['type'])
        if valid_filters.get('testing_type_id'): sql_where += " AND c.testing_type_id = %s"; params.append(valid_filters['testing_type_id'])
        if valid_filters.get('diagnosis_type_id'): sql_where += " AND c.diagnosis_type_id = %s"; params.append(valid_filters['diagnosis_type_id'])
        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset]); cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); result['total'] = cursor.fetchone()['total']
    except Exception as err: current_app.logger.error(f"Error get_paginated_diseases: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_disease_details_full(condition_id):
    conn = None; cursor = None; details = {'condition': None, 'symptoms': [], 'risk_factors': [], 'protocols': [], 'associated_doctors': []}
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT c.*, tt.name as testing_type_name, dt.name as diagnosis_type_name, d.name as department_name FROM conditions c LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id LEFT JOIN departments d ON c.department_id = d.department_id WHERE c.condition_id = %s AND c.is_active = TRUE", (condition_id,))
        details['condition'] = cursor.fetchone()
        if not details['condition']: return None
        # Fetch associated items *with names* for detail view
        cursor.execute("SELECT s.symptom_id, s.symptom_name FROM symptoms s JOIN symptom_condition_map scm ON s.symptom_id = scm.symptom_id WHERE scm.condition_id = %s ORDER BY s.symptom_name", (condition_id,))
        details['symptoms'] = cursor.fetchall()
        cursor.execute("SELECT rf.factor_id, rf.factor_name FROM risk_factors rf JOIN condition_risk_factors crf ON rf.factor_id = crf.factor_id WHERE crf.condition_id = %s ORDER BY rf.factor_name", (condition_id,))
        details['risk_factors'] = cursor.fetchall()
        cursor.execute("SELECT tp.protocol_id, tp.protocol_name FROM treatment_protocols tp JOIN condition_protocols cp ON tp.protocol_id = cp.protocol_id WHERE cp.condition_id = %s ORDER BY cp.relevance, tp.protocol_name", (condition_id,))
        details['protocols'] = cursor.fetchall()
        department_id = details['condition'].get('department_id')
        if department_id:
            cursor.execute("SELECT doc.user_id as doctor_user_id, u.first_name, u.last_name, s.name as specialization_name FROM doctors doc JOIN users u ON doc.user_id = u.user_id LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id WHERE doc.department_id = %s AND u.user_type = 'doctor' AND u.account_status = 'active' ORDER BY u.last_name", (department_id,))
            details['associated_doctors'] = cursor.fetchall()
    except Exception as err: current_app.logger.error(f"Error get_disease_details_full ID {condition_id}: {err}", exc_info=True); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

def get_disease_details_basic(condition_id):
    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM conditions WHERE condition_id = %s AND is_active = TRUE", (condition_id,))
        return cursor.fetchone()
    except Exception as err: current_app.logger.error(f"Error get_disease_details_basic ID {condition_id}: {err}", exc_info=True); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_associated_ids(condition_id):
    conn = None; cursor = None; associated_ids = {'symptoms': [], 'factors': [], 'protocols': []}
    try:
        conn = get_db_connection(); cursor = conn.cursor(buffered=True)
        cursor.execute("SELECT symptom_id FROM symptom_condition_map WHERE condition_id = %s", (condition_id,)); associated_ids['symptoms'] = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT factor_id FROM condition_risk_factors WHERE condition_id = %s", (condition_id,)); associated_ids['factors'] = [r[0] for r in cursor.fetchall()]
        cursor.execute("SELECT protocol_id FROM condition_protocols WHERE condition_id = %s", (condition_id,)); associated_ids['protocols'] = [r[0] for r in cursor.fetchall()]
    except Exception as err: current_app.logger.error(f"Error get_associated_ids for condition {condition_id}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return associated_ids

def update_associations(cursor, condition_id, selected_ids, table_name, link_id_column):
    try:
        # Use backticks for table and column names if they might be reserved words or contain special chars
        cursor.execute(f"DELETE FROM `{table_name}` WHERE `condition_id` = %s", (condition_id,))
        if selected_ids:
            # Build insert statement dynamically (be careful with column names if they aren't fixed)
            columns = f"`condition_id`, `{link_id_column}`"
            placeholders = "%s, %s"
            default_params = ()

            if table_name == 'symptom_condition_map':
                columns += ", `weight`, `is_required`"
                placeholders += ", %s, %s"
                default_params = (1.0, False)
            elif table_name == 'condition_risk_factors':
                columns += ", `weight`"
                placeholders += ", %s"
                default_params = (1.0,)
            elif table_name == 'condition_protocols':
                columns += ", `relevance`"
                placeholders += ", %s"
                default_params = ('Recommended',)

            insert_sql = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
            insert_data = [(condition_id, item_id) + default_params for item_id in selected_ids]
            cursor.executemany(insert_sql, insert_data)
            current_app.logger.info(f"Updated associations for {table_name}, condition {condition_id}. Added {len(insert_data)} links.")
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error in update_associations for {table_name}, condition {condition_id}: {err}", exc_info=True)
        raise # Re-raise to trigger transaction rollback


# --- Routes ---

# your_project/routes/Doctor_Portal/disease_management.py

@disease_management_bp.route('/', methods=['GET'])
@login_required
def list_diseases():
    if not check_doctor_authorization(current_user):
        abort(403)

    doctor_department_id = None
    doctor_department_name = "All Departments" # Default display name

    # --- Fetch the logged-in doctor's department ID ---
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Assuming current_user.id holds the PK from the 'users' table,
        # and the 'doctors' table has a 'user_id' FK and 'department_id' FK.
        # Adjust the query if your schema is different.
        sql_get_doctor_dept = """
            SELECT doc.department_id, dep.name as department_name
            FROM doctors doc
            JOIN departments dep ON doc.department_id = dep.department_id
            WHERE doc.user_id = %s
        """
        cursor.execute(sql_get_doctor_dept, (current_user.id,))
        doctor_info = cursor.fetchone()

        if doctor_info:
            doctor_department_id = doctor_info.get('department_id')
            doctor_department_name = doctor_info.get('department_name', "Assigned Department")
            if not doctor_department_id:
                current_app.logger.warning(f"Doctor user_id {current_user.id} found but department_id is NULL.")
                doctor_department_name = "Department Not Assigned" # Or handle as error
        else:
            current_app.logger.warning(f"No doctor record found for user_id {current_user.id}. Showing all diseases.")
            # doctor_department_id remains None, doctor_department_name remains "All Departments"
            # Or, you could choose to show an error/no diseases if department is mandatory

    except mysql.connector.Error as err:
        current_app.logger.error(f"Database error fetching doctor's department: {err}", exc_info=True)
        flash("Error retrieving your department information. Showing all diseases.", "warning")
        # Keep doctor_department_id as None so all diseases are shown as a fallback
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching doctor's department: {e}", exc_info=True)
        flash("An unexpected error occurred. Showing all diseases.", "warning")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    # ---------------------------------------------------

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()

    filters = {k: request.args.get(f'filter_{k}') for k in ['urgency', 'type'] if request.args.get(f'filter_{k}')}
    for k_id in ['testing_type_id', 'diagnosis_type_id']:
        val = request.args.get(f'filter_{k_id}', type=int)
        filters[k_id] = val if val else filters.get(k_id)

    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']:
        sort_dir = DEFAULT_SORT_DIRECTION

    # Now doctor_department_id will be the actual ID or None (if not found/error)
    result = get_paginated_diseases(
        page=page,
        per_page=ITEMS_PER_PAGE,
        search_term=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=filters,
        doctor_department_id=doctor_department_id # Pass the fetched ID
    )

    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0

    filter_options = {
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
        'testing_types': get_all_testing_types(),
        'diagnosis_types': get_all_diagnosis_types(),
    }

    return render_template(
        'Doctor_Portal/Diseases/disease_list.html',
        diseases=result['items'],
        search_term=search,
        current_page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=filters,
        valid_sort_columns=VALID_SORT_COLUMNS,
        doctor_department_name=doctor_department_name, # Pass the name for display
        **filter_options
    )

@disease_management_bp.route('/<int:condition_id>', methods=['GET'])
@login_required
def view_disease(condition_id):
    # (Ensure get_disease_details_full returns names for associated items)
    if not check_doctor_authorization(current_user): abort(403)
    details = get_disease_details_full(condition_id) # This should fetch names
    if not details or not details['condition']: flash("Condition not found.", "warning"); return redirect(url_for('.list_diseases'))
    return render_template('Doctor_Portal/Diseases/disease_detail.html', details=details)


@disease_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_disease():
    if not check_doctor_authorization(current_user): abort(403)
    # Fetch all dropdown options ONCE for both GET and POST error re-render
    dropdown_options = {
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
        'gender_relevance_opts': get_enum_values('conditions', 'gender_relevance'),
        'departments': get_all_departments(),
        'testing_types': get_all_testing_types(),
        'diagnosis_types': get_all_diagnosis_types(),
        'all_symptoms': get_all_symptoms(),
        'all_risk_factors': get_all_risk_factors(),
        'all_protocols': get_all_protocols()
    }
    # Log the structure of fetched items for debugging the name issue
    # current_app.logger.debug(f"Symptoms for Add Form: {dropdown_options['all_symptoms'][:2]}")
    # current_app.logger.debug(f"Factors for Add Form: {dropdown_options['all_risk_factors'][:2]}")
    # current_app.logger.debug(f"Protocols for Add Form: {dropdown_options['all_protocols'][:2]}")

    if request.method == 'POST':
        conn = None; cursor = None; errors = []; db_path_for_image = None
        # Get selected IDs early for re-render context
        selected_symptom_ids = request.form.getlist('symptom_ids', type=int)
        selected_factor_ids = request.form.getlist('factor_ids', type=int)
        selected_protocol_ids = request.form.getlist('protocol_ids', type=int)
        try:
            form = request.form
            # --- Collect form data ---
            name = form.get('condition_name', '').strip()
            desc=form.get('description','').strip() or None; icd=form.get('icd_code','').strip() or None
            urgency=form.get('urgency_level'); cond_type=form.get('condition_type') or None
            age_rel=form.get('age_relevance','').strip() or None; gender_rel=form.get('gender_relevance')
            specialist=form.get('specialist_type','').strip() or None; self_treat=form.get('self_treatable')=='on'
            duration=form.get('typical_duration','').strip() or None; edu_content=form.get('educational_content','').strip() or None
            overview=form.get('overview','').strip() or None; symptoms_text=form.get('symptoms_text','').strip() or None
            causes_text=form.get('causes_text','').strip() or None; testing_details=form.get('testing_details','').strip() or None
            diagnosis_details=form.get('diagnosis_details','').strip() or None
            testing_type_id=form.get('testing_type_id',type=int) if form.get('testing_type_id') else None
            diagnosis_type_id=form.get('diagnosis_type_id',type=int) if form.get('diagnosis_type_id') else None
            department_id=form.get('department_id',type=int) if form.get('department_id') else None

            # --- Validation ---
            if not name: errors.append("Condition Name is required.")
            if not urgency or urgency not in dropdown_options['urgency_levels']: errors.append("Valid Urgency is required.")
            if not gender_rel or gender_rel not in dropdown_options['gender_relevance_opts']: errors.append("Valid Gender Relevance is required.")
            # Add more validation...

            # --- File Handling ---
            image_file = request.files.get('disease_image')
            if image_file and image_file.filename:
                db_path_for_image, file_error = save_disease_image(image_file)
                if file_error: errors.append(file_error)

            if errors: raise ValueError("Validation errors.")

            # --- DB Insert ---
            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_cond = """INSERT INTO conditions (condition_name, description, icd_code, urgency_level, condition_type, age_relevance, gender_relevance, specialist_type, self_treatable, typical_duration, educational_content, overview, symptoms_text, causes_text, testing_details, diagnosis_details, condition_image_filename, testing_type_id, diagnosis_type_id, department_id, is_active, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, NOW(), NOW())"""
            params_cond = (name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist, self_treat, duration, edu_content, overview, symptoms_text, causes_text, testing_details, diagnosis_details, db_path_for_image, testing_type_id, diagnosis_type_id, department_id)
            cursor.execute(sql_cond, params_cond); new_id = cursor.lastrowid
            if not new_id: raise mysql.connector.Error("Failed to get new condition ID.")

            update_associations(cursor, new_id, selected_symptom_ids, 'symptom_condition_map', 'symptom_id')
            update_associations(cursor, new_id, selected_factor_ids, 'condition_risk_factors', 'factor_id')
            update_associations(cursor, new_id, selected_protocol_ids, 'condition_protocols', 'protocol_id')
            conn.commit()
            flash(f"Condition '{name}' added.", "success")
            return redirect(url_for('.view_disease', condition_id=new_id))

        except ValueError: # Catches validation errors
            if db_path_for_image: delete_disease_image(db_path_for_image) # Clean up saved image if validation failed
            for e in errors: flash(e, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if db_path_for_image: delete_disease_image(db_path_for_image)
            current_app.logger.error(f"DB/IO Error Add Cond: {err}", exc_info=True); flash(f"DB/File error: {getattr(err, 'msg', str(err))}", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if db_path_for_image: delete_disease_image(db_path_for_image)
            current_app.logger.error(f"Unexpected Error Add Cond: {e}", exc_info=True); flash("Unexpected error.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on ANY error, passing dropdowns and selections
        return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.add_disease'),
                               form_title="Add New Disease", disease=request.form, errors=errors, **dropdown_options,
                               associated_symptom_ids=selected_symptom_ids, associated_factor_ids=selected_factor_ids,
                               associated_protocol_ids=selected_protocol_ids)
    # GET request
    return render_template('Doctor_Portal/Diseases/disease_form.html', form_action=url_for('.add_disease'),
                           form_title="Add New Disease", disease=None, **dropdown_options,
                           associated_symptom_ids=[], associated_factor_ids=[], associated_protocol_ids=[])


@disease_management_bp.route('/<int:condition_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_disease(condition_id):
    if not check_doctor_authorization(current_user): abort(403)
    dropdown_options = { # Fetch options for both GET and POST re-render
        'urgency_levels': get_enum_values('conditions', 'urgency_level'),
        'condition_types': get_enum_values('conditions', 'condition_type'),
        'gender_relevance_opts': get_enum_values('conditions', 'gender_relevance'),
        'departments': get_all_departments(),
        'testing_types': get_all_testing_types(),
        'diagnosis_types': get_all_diagnosis_types(),
        'all_symptoms': get_all_symptoms(),
        'all_risk_factors': get_all_risk_factors(),
        'all_protocols': get_all_protocols()
    }
    # *** Add logging to check the structure of dropdown_options here too ***
    # current_app.logger.debug(f"Dropdown options for edit {condition_id}: {dropdown_options}")

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        # Get submitted selections early
        selected_symptom_ids = request.form.getlist('symptom_ids', type=int)
        selected_factor_ids = request.form.getlist('factor_ids', type=int)
        selected_protocol_ids = request.form.getlist('protocol_ids', type=int)

        # Image handling setup
        current_image_db_path = request.form.get('current_disease_image_filename') # Original path from hidden field
        newly_saved_db_path = None # Track if a new image is saved in *this* request
        image_path_for_db_update = current_image_db_path # What will be saved to DB

        try:
            form = request.form
            name = form.get('condition_name', '').strip()
            # ... (collect all other form fields) ...
            desc=form.get('description','').strip() or None; icd=form.get('icd_code','').strip() or None
            urgency=form.get('urgency_level'); cond_type=form.get('condition_type') or None
            age_rel=form.get('age_relevance','').strip() or None; gender_rel=form.get('gender_relevance')
            specialist=form.get('specialist_type','').strip() or None; self_treat=form.get('self_treatable')=='on'
            duration=form.get('typical_duration','').strip() or None; edu_content=form.get('educational_content','').strip() or None
            overview=form.get('overview','').strip() or None; symptoms_text=form.get('symptoms_text','').strip() or None
            causes_text=form.get('causes_text','').strip() or None; testing_details=form.get('testing_details','').strip() or None
            diagnosis_details=form.get('diagnosis_details','').strip() or None
            testing_type_id=form.get('testing_type_id',type=int) if form.get('testing_type_id') else None
            diagnosis_type_id=form.get('diagnosis_type_id',type=int) if form.get('diagnosis_type_id') else None
            department_id=form.get('department_id',type=int) if form.get('department_id') else None


            # --- Revised File Handling ---
            image_file = request.files.get('disease_image')
            delete_current_image_flag = request.form.get('delete_image') == 'on'

            if delete_current_image_flag:
                if current_image_db_path:
                    deleted_ok, msg = delete_disease_image(current_image_db_path)
                    if deleted_ok: image_path_for_db_update = None
                    else: errors.append(f"Delete failed: {msg}")
                else: image_path_for_db_update = None
            elif image_file and image_file.filename:
                newly_saved_db_path, file_error = save_disease_image(image_file)
                if file_error: errors.append(f"Upload failed: {file_error}")
                else: # New image saved
                    # Delete old one *only if save was successful*
                    if current_image_db_path and current_image_db_path != newly_saved_db_path:
                        delete_disease_image(current_image_db_path)
                    image_path_for_db_update = newly_saved_db_path
            # else: Keep image_path_for_db_update as current_image_db_path

            # --- Validation ---
            if not name: errors.append("Name required.")
            # ... (other validations) ...

            if errors:
                # If errors occurred, and we had just saved a *new* image, delete the new one.
                if newly_saved_db_path:
                    delete_disease_image(newly_saved_db_path)
                raise ValueError("Validation errors.")

            # --- DB Update ---
            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_update = """UPDATE conditions SET condition_name=%s, description=%s, icd_code=%s, urgency_level=%s, condition_type=%s, age_relevance=%s, gender_relevance=%s, specialist_type=%s, self_treatable=%s, typical_duration=%s, educational_content=%s, overview=%s, symptoms_text=%s, causes_text=%s, testing_details=%s, diagnosis_details=%s, condition_image_filename=%s, testing_type_id=%s, diagnosis_type_id=%s, department_id=%s, updated_at=NOW() WHERE condition_id=%s AND is_active=TRUE"""
            params = (name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist, self_treat, duration, edu_content, overview, symptoms_text, causes_text, testing_details, diagnosis_details, image_path_for_db_update, testing_type_id, diagnosis_type_id, department_id, condition_id)
            cursor.execute(sql_update, params)
            if cursor.rowcount == 0:
                if newly_saved_db_path and newly_saved_db_path != current_image_db_path: delete_disease_image(newly_saved_db_path)
                conn.rollback(); flash("Not found or update failed.", "warning"); return redirect(url_for('.list_diseases'))

            update_associations(cursor, condition_id, selected_symptom_ids, 'symptom_condition_map', 'symptom_id')
            update_associations(cursor, condition_id, selected_factor_ids, 'condition_risk_factors', 'factor_id')
            update_associations(cursor, condition_id, selected_protocol_ids, 'condition_protocols', 'protocol_id')
            conn.commit()
            flash(f"Condition '{name}' updated.", "success")
            return redirect(url_for('.view_disease', condition_id=condition_id))

        except ValueError: # Catches validation errors
            # newly_saved_db_path would have been deleted above if set
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if newly_saved_db_path and newly_saved_db_path != current_image_db_path: delete_disease_image(newly_saved_db_path)
            current_app.logger.error(f"DB/IO Error Edit Cond {condition_id}: {err}", exc_info=True); flash("DB/File error.", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            if newly_saved_db_path and newly_saved_db_path != current_image_db_path: delete_disease_image(newly_saved_db_path)
            current_app.logger.error(f"Unexpected Error Edit Cond {condition_id}: {e}", exc_info=True); flash("Error.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # --- Re-render edit form on error ---
        # Pass back the submitted form data for repopulation
        form_data_on_err = request.form.to_dict()
        form_data_on_err['condition_id'] = condition_id
        # Show the image that existed *before* this failed attempt,
        # UNLESS the delete checkbox was successfully processed AND the intent was to remove it.
        form_data_on_err['condition_image_filename'] = image_path_for_db_update # Shows what *would* have been saved

        return render_template(
            'Doctor_Portal/Diseases/disease_form.html',
            form_action=url_for('.edit_disease', condition_id=condition_id),
            form_title=f"Edit Condition (ID: {condition_id}) - Error",
            disease=form_data_on_err, # Use submitted form data
            errors=errors,
            **dropdown_options, # Pass dropdown options again
            # Pass back the IDs the user *tried* to select
            associated_symptom_ids=selected_symptom_ids,
            associated_factor_ids=selected_factor_ids,
            associated_protocol_ids=selected_protocol_ids
        )

    # --- GET request for edit form ---
    disease_data_for_form = get_disease_details_basic(condition_id)
    if not disease_data_for_form:
        flash("Condition not found or is inactive.", "warning")
        return redirect(url_for('.list_diseases'))
    associated_ids = get_associated_ids(condition_id)
    # Log fetched associated IDs for debugging GET request
    # current_app.logger.debug(f"Associated IDs for GET Edit form {condition_id}: {associated_ids}")

    return render_template(
        'Doctor_Portal/Diseases/disease_form.html',
        form_action=url_for('.edit_disease', condition_id=condition_id),
        form_title=f"Edit Condition: {disease_data_for_form.get('condition_name', 'N/A')}",
        disease=disease_data_for_form, # Data from DB for pre-filling
        **dropdown_options, # Unpack all dropdown options
        associated_symptom_ids=associated_ids['symptoms'],
        associated_factor_ids=associated_ids['factors'],
        associated_protocol_ids=associated_ids['protocols']
    )


# ... (deactivate_disease and serve_condition_image routes remain the same) ...
@disease_management_bp.route('/<int:condition_id>/deactivate', methods=['POST'])
@login_required
def deactivate_disease(condition_id):
    if not check_doctor_authorization(current_user): abort(403)
    conn=None; cursor=None
    try:
        conn=get_db_connection(); conn.start_transaction(); cursor=conn.cursor()
        cursor.execute("UPDATE conditions SET is_active = FALSE, updated_at = NOW() WHERE condition_id = %s", (condition_id,))
        if cursor.rowcount == 0: flash("Not found/inactive.", "warning"); conn.rollback()
        else: conn.commit(); flash("Deactivated.", "success")
    except Exception as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        current_app.logger.error(f"Error Deactivating Cond {condition_id}: {err}", exc_info=True); flash("Error.", "danger")
    finally:
        if cursor:cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_diseases'))

@disease_management_bp.route('/images/<path:image_filename_in_db>')
def serve_condition_image(image_filename_in_db):
    static_dir_abs = current_app.config.get('STATIC_FOLDER')
    if not static_dir_abs: abort(404)
    if '..' in image_filename_in_db or image_filename_in_db.startswith('/'): abort(400)
    try:
        return send_from_directory(static_dir_abs, image_filename_in_db, as_attachment=False)
    except FileNotFoundError: abort(404)
    except Exception as e:
        current_app.logger.error(f"Error serving condition image {image_filename_in_db}: {e}", exc_info=True)
        abort(500)