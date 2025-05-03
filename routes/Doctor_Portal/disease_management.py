# --- START OF FILE disease_management.py ---

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename # For secure file uploads
import os # For file operations
from db import get_db_connection
from datetime import date, datetime
import math # For pagination calculations

# --- Authorization Helper ---
def check_doctor_authorization(user):
    if not user or not user.is_authenticated: return False
    return getattr(user, 'user_type', None) == 'doctor'

# --- Blueprint Definition ---
disease_management_bp = Blueprint(
    'disease_management',
    __name__,
    url_prefix='/doctor/diseases',
    template_folder='../../templates' # Adjusted path
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 15
VALID_SORT_COLUMNS = {
    'name': 'c.condition_name', 'code': 'c.icd_code',
    'type': 'c.condition_type', 'urgency': 'c.urgency_level',
    'id': 'c.condition_id', 'dept': 'd.name',
    'test_type': 'tt.name', 'diag_type': 'dt.name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE = {} # Simple cache for ENUM values

# --- Helper Functions ---

def allowed_file(filename):
    """Checks if the filename has an allowed extension."""
    ALLOWED_EXTENSIONS = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_disease_image(file):
    """Saves the uploaded image file securely."""
    upload_folder = current_app.config.get('UPLOAD_FOLDER_DISEASE_IMAGES') # Use a specific folder if desired
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_DISEASE_IMAGES not configured.")
        return None

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        ext = ''
        if '.' in original_filename:
            ext = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename[:50]}.{ext}" if ext else f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename[:50]}")

        filepath = os.path.join(upload_folder, unique_filename)
        try:
            os.makedirs(upload_folder, exist_ok=True) # Ensure directory exists
            file.save(filepath)
            # Return filename relative to static folder root for web access
            relative_path = os.path.join('uploads', 'disease_images', unique_filename).replace(os.path.sep, '/')
            return relative_path # Return the relative path for DB storage
        except Exception as e:
            current_app.logger.error(f"Failed to save image {unique_filename}: {e}")
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError: pass
            return None
    return None

def delete_disease_image(filename_relative_path):
    """Deletes an image file if it exists using the relative path stored in DB."""
    if not filename_relative_path: return False
    try:
        base_static_folder = current_app.static_folder
        # Basic path safety checks
        if filename_relative_path.startswith('/') or '..' in filename_relative_path:
             current_app.logger.warning(f"Attempt to delete potentially unsafe path: {filename_relative_path}")
             return False
        filepath = os.path.join(base_static_folder, filename_relative_path)
        # Ensure path stays within static folder
        if not os.path.abspath(filepath).startswith(os.path.abspath(base_static_folder)):
             current_app.logger.warning(f"Attempt to delete file outside static folder: {filepath}")
             return False
        if os.path.exists(filepath) and os.path.isfile(filepath):
            os.remove(filepath)
            current_app.logger.info(f"Deleted image file: {filepath}")
            return True
        else:
            current_app.logger.warning(f"Image file not found for deletion: {filepath}")
            return False
    except Exception as e:
        current_app.logger.error(f"Error deleting image file {filename_relative_path}: {e}")
    return False

def get_enum_values(table_name, column_name):
    """ Helper to get ENUM values from DB schema. Caches results. """
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE:
        return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor()
        db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0];
            if isinstance(enum_str, bytes): enum_str = enum_str.decode('utf-8')
            if enum_str.startswith('enum(') and enum_str.endswith(')'):
                 raw_values = enum_str[len('enum('):-1].split(',')
                 values = [val.strip().strip("'") for val in raw_values]
            else: current_app.logger.warning(f"Column {table_name}.{column_name} format unexpected: {enum_str}")
        else: current_app.logger.warning(f"Could not retrieve ENUM definition for {table_name}.{column_name}")
        ENUM_CACHE[cache_key] = values
        return values
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_col, name_col, order_col=None):
    """ Generic helper to fetch ID/Name pairs from simple tables """
    conn = None; cursor = None; items = []
    order_by = order_col if order_col else name_col
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        # Column names are assumed safe as they come from code, not user input
        query = f"SELECT `{id_col}`, `{name_col}` FROM `{table_name}` ORDER BY `{order_by}` ASC"
        cursor.execute(query)
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching from {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

# Specific Fetchers using the generic helper
def get_all_departments(): return get_all_simple('departments', 'department_id', 'name')
def get_all_testing_types(): return get_all_simple('testing_types', 'testing_type_id', 'name')
def get_all_diagnosis_types(): return get_all_simple('diagnosis_types', 'diagnosis_type_id', 'name')
def get_all_symptoms(): return get_all_simple('symptoms', 'symptom_id', 'symptom_name')
def get_all_risk_factors(): return get_all_simple('risk_factors', 'factor_id', 'factor_name')
def get_all_protocols(): return get_all_simple('treatment_protocols', 'protocol_id', 'protocol_name')

# --- Data Fetching Helpers ---

def get_paginated_diseases(page=1, per_page=ITEMS_PER_PAGE, search_term=None,
                         sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION,
                         filters=None, doctor_department_id=None): # <-- ADDED doctor_department_id
    """
    Fetches paginated, filtered, and sorted conditions.
    If doctor_department_id is provided, filters conditions by that department.
    """
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        sql_select = """
            SELECT SQL_CALC_FOUND_ROWS
                c.condition_id, c.condition_name, c.icd_code,
                c.condition_type, c.urgency_level,
                d.name as department_name,
                tt.name as testing_type_name,
                dt.name as diagnosis_type_name,
                c.condition_image_filename
        """
        sql_from = """
            FROM conditions c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id
            LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id
        """
        sql_where = " WHERE c.is_active = TRUE"
        params = []

        # --- APPLY DOCTOR'S DEPARTMENT FILTER ---
        if doctor_department_id is not None:
            sql_where += " AND c.department_id = %s"
            params.append(doctor_department_id)
        # --- END DOCTOR FILTER ---

        # Search logic
        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (c.condition_name LIKE %s OR c.description LIKE %s OR c.icd_code LIKE %s OR c.overview LIKE %s OR c.symptoms_text LIKE %s OR c.causes_text LIKE %s)"
            params.extend([search_like] * 6)

        # Other Filter logic
        if valid_filters.get('urgency'):
            sql_where += " AND c.urgency_level = %s"; params.append(valid_filters['urgency'])
        if valid_filters.get('type'):
            sql_where += " AND c.condition_type = %s"; params.append(valid_filters['type'])
        # Removed Department Filter Logic
        if valid_filters.get('testing_type_id'):
             sql_where += " AND c.testing_type_id = %s"; params.append(valid_filters['testing_type_id'])
        if valid_filters.get('diagnosis_type_id'):
             sql_where += " AND c.diagnosis_type_id = %s"; params.append(valid_filters['diagnosis_type_id'])

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        cursor.execute("SELECT FOUND_ROWS() as total")
        total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching paginated diseases: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_disease_details_full(condition_id):
    """Fetches full details including associations, text fields, image, types, and doctors."""
    conn = None; cursor = None;
    details = {
        'condition': None, 'symptoms': [], 'risk_factors': [],
        'protocols': [], 'associated_doctors': []
    }
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        # 1. Get Condition Details
        query_cond = """
            SELECT c.*, tt.name as testing_type_name, dt.name as diagnosis_type_name, d.name as department_name
            FROM conditions c
            LEFT JOIN testing_types tt ON c.testing_type_id = tt.testing_type_id
            LEFT JOIN diagnosis_types dt ON c.diagnosis_type_id = dt.diagnosis_type_id
            LEFT JOIN departments d ON c.department_id = d.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query_cond, (condition_id,))
        details['condition'] = cursor.fetchone()
        if not details['condition']: return None

        # 2. Get Associated Symptoms
        query_sym = """SELECT s.symptom_id, s.symptom_name, scm.weight, scm.is_required FROM symptoms s JOIN symptom_condition_map scm ON s.symptom_id = scm.symptom_id WHERE scm.condition_id = %s ORDER BY s.symptom_name"""
        cursor.execute(query_sym, (condition_id,))
        details['symptoms'] = cursor.fetchall()

        # 3. Get Associated Risk Factors
        query_rf = """SELECT rf.factor_id, rf.factor_name, rf.factor_type, crf.weight FROM risk_factors rf JOIN condition_risk_factors crf ON rf.factor_id = crf.factor_id WHERE crf.condition_id = %s ORDER BY rf.factor_name"""
        cursor.execute(query_rf, (condition_id,))
        details['risk_factors'] = cursor.fetchall()

        # 4. Get Associated Protocols
        query_pro = """SELECT tp.protocol_id, tp.protocol_name, tp.guideline_url, cp.relevance FROM treatment_protocols tp JOIN condition_protocols cp ON tp.protocol_id = cp.protocol_id WHERE cp.condition_id = %s ORDER BY cp.relevance, tp.protocol_name"""
        cursor.execute(query_pro, (condition_id,))
        details['protocols'] = cursor.fetchall()

        # 5. Get Associated Doctors (Based on condition's department_id)
        department_id = details['condition'].get('department_id')
        if department_id:
            query_docs = """
                SELECT doc.user_id as doctor_user_id, u.first_name, u.last_name, u.email, u.profile_picture, s.name as specialization_name
                FROM doctors doc
                JOIN users u ON doc.user_id = u.user_id
                LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
                WHERE doc.department_id = %s AND u.user_type = 'doctor' AND u.account_status = 'active'
                ORDER BY u.last_name, u.first_name
            """
            cursor.execute(query_docs, (department_id,))
            details['associated_doctors'] = cursor.fetchall()

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching full disease details for ID {condition_id}: {err}")
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

def get_disease_details_basic(condition_id):
     """Fetches just the condition's own data, used for edit form."""
     conn = None; cursor = None;
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor(dictionary=True)
         cursor.execute("SELECT * FROM conditions WHERE condition_id = %s AND is_active = TRUE", (condition_id,))
         return cursor.fetchone()
     except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching basic disease details for ID {condition_id}: {err}")
        return None
     finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_associated_ids(condition_id):
    """Fetches IDs of currently associated items for pre-selection in forms."""
    conn = None; cursor = None
    associated_ids = {'symptoms': [], 'factors': [], 'protocols': []}
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()

        cursor.execute("SELECT symptom_id FROM symptom_condition_map WHERE condition_id = %s", (condition_id,))
        associated_ids['symptoms'] = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT factor_id FROM condition_risk_factors WHERE condition_id = %s", (condition_id,))
        associated_ids['factors'] = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT protocol_id FROM condition_protocols WHERE condition_id = %s", (condition_id,))
        associated_ids['protocols'] = [row[0] for row in cursor.fetchall()]

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching associated IDs for condition {condition_id}: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return associated_ids

def update_associations(cursor, condition_id, selected_ids, table_name, link_id_column):
    """Deletes existing and inserts new associations for a given type within a transaction."""
    try:
        # Delete existing links
        delete_sql = f"DELETE FROM {table_name} WHERE condition_id = %s"
        cursor.execute(delete_sql, (condition_id,))

        if selected_ids:
            insert_sql_base = f"INSERT INTO {table_name} (condition_id, {link_id_column}"
            values_placeholder_base = "(%s, %s"
            default_params = ()

            if table_name == 'symptom_condition_map':
                insert_sql_base += ", weight, is_required)"; values_placeholder_base += ", %s, %s)"; default_params = (1.0, False)
            elif table_name == 'condition_risk_factors':
                insert_sql_base += ", weight)"; values_placeholder_base += ", %s)"; default_params = (1.0,)
            elif table_name == 'condition_protocols':
                insert_sql_base += ", relevance)"; values_placeholder_base += ", %s)"; default_params = ('Recommended',)
            else:
                 insert_sql_base += ")"; values_placeholder_base += ")"

            insert_sql = f"{insert_sql_base} VALUES {values_placeholder_base}"
            insert_data = [(condition_id, item_id) + default_params for item_id in selected_ids]
            cursor.executemany(insert_sql, insert_data)

    except mysql.connector.Error as err:
        current_app.logger.error(f"Error updating associations in {table_name} for condition {condition_id}: {err}")
        raise # Re-raise to trigger rollback in calling function

# --- Routes ---

@disease_management_bp.route('/', methods=['GET'])
@login_required
def list_diseases():
    """
    Displays the paginated list of diseases, automatically filtered
    by the logged-in doctor's department.
    """
    if not check_doctor_authorization(current_user): abort(403)

    # Get Doctor's Department ID and Name
    doctor_department_id = None
    doctor_department_name = "All"
    conn_doc = None; cursor_doc = None
    try:
        user_id = getattr(current_user, 'user_id', None) or getattr(current_user, 'id', None)
        if not user_id: raise ValueError("Could not determine current user ID.")
        conn_doc = get_db_connection();
        if not conn_doc: raise ConnectionError("DB Connection failed for doctor info")
        cursor_doc = conn_doc.cursor(dictionary=True)
        cursor_doc.execute("SELECT doc.department_id, d.name as department_name FROM doctors doc LEFT JOIN departments d ON doc.department_id = d.department_id WHERE doc.user_id = %s", (user_id,))
        doctor_info = cursor_doc.fetchone()
        if doctor_info:
            doctor_department_id = doctor_info.get('department_id')
            doctor_department_name = doctor_info.get('department_name') or ("Your Assigned Department" if doctor_department_id else "Unassigned Department")
        else:
             current_app.logger.warning(f"No doctor record found for user_id {user_id} when listing diseases.")
             doctor_department_name = "Unknown (No Doctor Record)"
    except (mysql.connector.Error, ConnectionError, ValueError) as e:
        current_app.logger.error(f"Failed to fetch doctor department for user {user_id}: {e}")
        doctor_department_id = None; doctor_department_name = "All (Error Fetching Department)"
    finally:
        if cursor_doc: cursor_doc.close()
        if conn_doc and conn_doc.is_connected(): conn_doc.close()

    # Get other request args
    page = request.args.get('page', 1, type=int); search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower(); sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    filter_urgency = request.args.get('filter_urgency', ''); filter_type = request.args.get('filter_type', '')
    filter_testing_type = request.args.get('filter_testing_type', type=int); filter_diagnosis_type = request.args.get('filter_diagnosis_type', type=int)

    # Validate sort params
    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    # Build filters dict (excluding department)
    filters = {};
    if filter_urgency: filters['urgency'] = filter_urgency;
    if filter_type: filters['type'] = filter_type
    if filter_testing_type: filters['testing_type_id'] = filter_testing_type
    if filter_diagnosis_type: filters['diagnosis_type_id'] = filter_diagnosis_type

    # Fetch data using the doctor's department ID
    result = get_paginated_diseases(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters, doctor_department_id)
    diseases = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0

    # Get Enum/Dropdown values for *remaining* filters
    urgency_levels = get_enum_values('conditions', 'urgency_level')
    condition_types = get_enum_values('conditions', 'condition_type')
    testing_types = get_all_testing_types()
    diagnosis_types = get_all_diagnosis_types()

    return render_template(
        'Doctor_Portal/Diseases/disease_list.html',
        diseases=diseases, search_term=search_term, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters, urgency_levels=urgency_levels,
        condition_types=condition_types, testing_types=testing_types, diagnosis_types=diagnosis_types,
        valid_sort_columns=VALID_SORT_COLUMNS, doctor_department_name=doctor_department_name
    )

@disease_management_bp.route('/<int:condition_id>', methods=['GET'])
@login_required
def view_disease(condition_id):
    """Displays the details of a single condition."""
    if not check_doctor_authorization(current_user): abort(403)
    disease_details = get_disease_details_full(condition_id)
    if not disease_details or not disease_details['condition']:
        flash("Condition not found or inactive.", "warning")
        return redirect(url_for('disease_management.list_diseases'))
    return render_template('Doctor_Portal/Diseases/disease_detail.html', details=disease_details)

@disease_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_disease():
    """Handles adding a new disease including associations."""
    if not check_doctor_authorization(current_user): abort(403)

    # Fetch options for dropdowns/selects
    urgency_levels = get_enum_values('conditions', 'urgency_level')
    condition_types = get_enum_values('conditions', 'condition_type')
    gender_relevance_opts = get_enum_values('conditions', 'gender_relevance')
    departments = get_all_departments()
    testing_types = get_all_testing_types()
    diagnosis_types = get_all_diagnosis_types()
    all_symptoms = get_all_symptoms()
    all_risk_factors = get_all_risk_factors()
    all_protocols = get_all_protocols()

    if request.method == 'POST':
        conn = None; cursor = None; errors = []; saved_filename_relative = None; new_condition_id = None
        # Initialize lists to hold potentially selected IDs even if validation fails
        selected_symptom_ids = []; selected_factor_ids = []; selected_protocol_ids = []
        try:
            # --- Get form data (main condition) ---
            name = request.form.get('condition_name', '').strip()
            desc = request.form.get('description', '').strip() or None; icd = request.form.get('icd_code', '').strip() or None
            urgency = request.form.get('urgency_level'); cond_type = request.form.get('condition_type') or None
            age_rel = request.form.get('age_relevance', '').strip() or None; gender_rel = request.form.get('gender_relevance')
            specialist = request.form.get('specialist_type', '').strip() or None; self_treat = request.form.get('self_treatable') == 'on'
            duration = request.form.get('typical_duration', '').strip() or None; edu_content = request.form.get('educational_content', '').strip() or None
            overview = request.form.get('overview', '').strip() or None; symptoms_text = request.form.get('symptoms_text', '').strip() or None
            causes_text = request.form.get('causes_text', '').strip() or None; testing_details = request.form.get('testing_details', '').strip() or None
            diagnosis_details = request.form.get('diagnosis_details', '').strip() or None
            testing_type_id = request.form.get('testing_type_id', type=int) if request.form.get('testing_type_id') else None
            diagnosis_type_id = request.form.get('diagnosis_type_id', type=int) if request.form.get('diagnosis_type_id') else None
            department_id = request.form.get('department_id', type=int) if request.form.get('department_id') else None

            # --- Get selected association IDs ---
            selected_symptom_ids = request.form.getlist('symptom_ids', type=int)
            selected_factor_ids = request.form.getlist('factor_ids', type=int)
            selected_protocol_ids = request.form.getlist('protocol_ids', type=int)

            # --- Validation ---
            if not name: errors.append("Condition Name is required.")
            if not urgency or urgency not in urgency_levels: errors.append("Valid Urgency Level is required.")
            if cond_type and cond_type not in condition_types: errors.append("Invalid Condition Type selected.")
            if not gender_rel or gender_rel not in gender_relevance_opts: errors.append("Valid Gender Relevance is required.")
            # Add more validation as needed

            # --- Handle File Upload ---
            image_file = request.files.get('disease_image')
            if image_file and image_file.filename != '':
                saved_filename_relative = save_disease_image(image_file)
                if not saved_filename_relative: errors.append("Failed to save disease image.")

            if errors: raise ValueError("Validation errors occurred.")

            # --- Database Insert (Transaction) ---
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction()
            cursor = conn.cursor()

            # 1. Insert main condition
            sql_cond = """
                INSERT INTO conditions (condition_name, description, icd_code, urgency_level, condition_type,
                    age_relevance, gender_relevance, specialist_type, self_treatable, typical_duration,
                    educational_content, overview, symptoms_text, causes_text, testing_details,
                    diagnosis_details, disease_image_filename, testing_type_id, diagnosis_type_id,
                    department_id, is_active, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, TRUE, NOW(), NOW())
            """
            params_cond = ( name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist, self_treat, duration,
                            edu_content, overview, symptoms_text, causes_text, testing_details, diagnosis_details,
                            saved_filename_relative, testing_type_id, diagnosis_type_id, department_id )
            cursor.execute(sql_cond, params_cond);
            new_condition_id = cursor.lastrowid
            if not new_condition_id: raise mysql.connector.Error("Failed to retrieve new condition ID.")

            # 2. Update associations
            update_associations(cursor, new_condition_id, selected_symptom_ids, 'symptom_condition_map', 'symptom_id')
            update_associations(cursor, new_condition_id, selected_factor_ids, 'condition_risk_factors', 'factor_id')
            update_associations(cursor, new_condition_id, selected_protocol_ids, 'condition_protocols', 'protocol_id')

            conn.commit()
            flash(f"Condition '{name}' added successfully.", "success")
            return redirect(url_for('disease_management.view_disease', condition_id=new_condition_id))

        except ValueError:
            if saved_filename_relative: delete_disease_image(saved_filename_relative)
            for err_msg in errors: flash(err_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative: delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"DB/Connection/IO Error Adding Condition: {err}", exc_info=True)
            flash_msg = f"Database/File error: {err}";
            if isinstance(err, mysql.connector.Error) and err.errno == 1062: flash_msg = "Database error: Condition name or ICD code might already exist."
            flash(flash_msg, "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative: delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"Unexpected Error Adding Condition: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error, passing back submitted values and selected IDs
        return render_template(
            'Doctor_Portal/Diseases/disease_form.html', form_action=url_for('disease_management.add_disease'),
            form_title="Add New Disease/Condition", disease=request.form, errors=errors,
            urgency_levels=urgency_levels, condition_types=condition_types, gender_relevance_opts=gender_relevance_opts,
            departments=departments, testing_types=testing_types, diagnosis_types=diagnosis_types,
            all_symptoms=all_symptoms, all_risk_factors=all_risk_factors, all_protocols=all_protocols,
            associated_symptom_ids=selected_symptom_ids, # Pass lists captured in try block
            associated_factor_ids=selected_factor_ids,
            associated_protocol_ids=selected_protocol_ids
        )

    # GET request
    return render_template(
        'Doctor_Portal/Diseases/disease_form.html', form_action=url_for('disease_management.add_disease'),
        form_title="Add New Disease/Condition", disease=None, urgency_levels=urgency_levels,
        condition_types=condition_types, gender_relevance_opts=gender_relevance_opts, departments=departments,
        testing_types=testing_types, diagnosis_types=diagnosis_types, all_symptoms=all_symptoms,
        all_risk_factors=all_risk_factors, all_protocols=all_protocols,
        associated_symptom_ids=[], associated_factor_ids=[], associated_protocol_ids=[]
    )

@disease_management_bp.route('/<int:condition_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_disease(condition_id):
    """Handles editing an existing disease including associations."""
    if not check_doctor_authorization(current_user): abort(403)

    # Fetch options for dropdowns/selects
    urgency_levels = get_enum_values('conditions', 'urgency_level'); condition_types = get_enum_values('conditions', 'condition_type')
    gender_relevance_opts = get_enum_values('conditions', 'gender_relevance'); departments = get_all_departments()
    testing_types = get_all_testing_types(); diagnosis_types = get_all_diagnosis_types()
    all_symptoms = get_all_symptoms(); all_risk_factors = get_all_risk_factors(); all_protocols = get_all_protocols()

    conn = None; cursor = None;
    if request.method == 'POST':
        errors = []; saved_filename_relative = None
        # Initialize lists to hold potentially selected IDs even if validation fails
        selected_symptom_ids = []; selected_factor_ids = []; selected_protocol_ids = []
        previous_filename_relative = request.form.get('current_disease_image_filename')
        try:
            # --- Get form data (main condition) ---
            name = request.form.get('condition_name', '').strip()
            desc = request.form.get('description', '').strip() or None; icd = request.form.get('icd_code', '').strip() or None
            urgency = request.form.get('urgency_level'); cond_type = request.form.get('condition_type') or None
            age_rel = request.form.get('age_relevance', '').strip() or None; gender_rel = request.form.get('gender_relevance')
            specialist = request.form.get('specialist_type', '').strip() or None; self_treat = request.form.get('self_treatable') == 'on'
            duration = request.form.get('typical_duration', '').strip() or None; edu_content = request.form.get('educational_content', '').strip() or None
            overview = request.form.get('overview', '').strip() or None; symptoms_text = request.form.get('symptoms_text', '').strip() or None
            causes_text = request.form.get('causes_text', '').strip() or None; testing_details = request.form.get('testing_details', '').strip() or None
            diagnosis_details = request.form.get('diagnosis_details', '').strip() or None
            testing_type_id = request.form.get('testing_type_id', type=int) if request.form.get('testing_type_id') else None
            diagnosis_type_id = request.form.get('diagnosis_type_id', type=int) if request.form.get('diagnosis_type_id') else None
            department_id = request.form.get('department_id', type=int) if request.form.get('department_id') else None

            # --- Get selected association IDs ---
            selected_symptom_ids = request.form.getlist('symptom_ids', type=int)
            selected_factor_ids = request.form.getlist('factor_ids', type=int)
            selected_protocol_ids = request.form.getlist('protocol_ids', type=int)

            # --- Validation ---
            if not name: errors.append("Condition Name is required.")
            if not urgency or urgency not in urgency_levels: errors.append("Valid Urgency Level is required.")
            # Add more validation...

            # --- Handle File Upload & Deletion ---
            image_file = request.files.get('disease_image')
            delete_current_image = request.form.get('delete_image') == 'on'
            final_filename_relative = previous_filename_relative
            if delete_current_image:
                if previous_filename_relative:
                    if delete_disease_image(previous_filename_relative): final_filename_relative = None
                    else: errors.append("Failed to delete the current image file.")
                else: final_filename_relative = None
            elif image_file and image_file.filename != '':
                saved_filename_relative = save_disease_image(image_file)
                if saved_filename_relative:
                    if previous_filename_relative: delete_disease_image(previous_filename_relative)
                    final_filename_relative = saved_filename_relative
                else:
                    errors.append("Failed to save the new disease image."); final_filename_relative = previous_filename_relative
            if errors: raise ValueError("Validation or file handling errors occurred.")

            # --- Database Update (Transaction) ---
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction()
            cursor = conn.cursor()

            # 1. Update main condition details
            sql_update_cond = """
                UPDATE conditions SET condition_name=%s, description=%s, icd_code=%s, urgency_level=%s, condition_type=%s,
                    age_relevance=%s, gender_relevance=%s, specialist_type=%s, self_treatable=%s, typical_duration=%s,
                    educational_content=%s, overview=%s, symptoms_text=%s, causes_text=%s, testing_details=%s,
                    diagnosis_details=%s, disease_image_filename=%s, testing_type_id=%s, diagnosis_type_id=%s,
                    department_id=%s, updated_at=NOW()
                WHERE condition_id=%s AND is_active = TRUE
            """
            params_update_cond = (
                name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist, self_treat, duration, edu_content,
                overview, symptoms_text, causes_text, testing_details, diagnosis_details, final_filename_relative,
                testing_type_id, diagnosis_type_id, department_id, condition_id
            )
            cursor.execute(sql_update_cond, params_update_cond);
            if cursor.rowcount == 0:
                conn.rollback(); flash("Condition not found or is inactive, update failed.", "warning")
                if saved_filename_relative and saved_filename_relative != previous_filename_relative: delete_disease_image(saved_filename_relative)
                return redirect(url_for('disease_management.list_diseases'))

            # 2. Update associations
            update_associations(cursor, condition_id, selected_symptom_ids, 'symptom_condition_map', 'symptom_id')
            update_associations(cursor, condition_id, selected_factor_ids, 'condition_risk_factors', 'factor_id')
            update_associations(cursor, condition_id, selected_protocol_ids, 'condition_protocols', 'protocol_id')

            conn.commit()
            flash(f"Condition '{name}' updated successfully.", "success")
            return redirect(url_for('disease_management.view_disease', condition_id=condition_id))

        except ValueError:
            if saved_filename_relative and saved_filename_relative != previous_filename_relative: delete_disease_image(saved_filename_relative)
            for err_msg in errors: flash(err_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err:
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative and saved_filename_relative != previous_filename_relative: delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"DB/Connection/IO Error Editing Condition {condition_id}: {err}", exc_info=True)
            flash("Database or file error updating condition.", "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative and saved_filename_relative != previous_filename_relative: delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"Unexpected Error Editing Condition {condition_id}: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render edit form on error
        form_data = request.form.to_dict(); form_data['condition_id'] = condition_id
        form_data['disease_image_filename'] = previous_filename_relative
        return render_template(
            'Doctor_Portal/Diseases/disease_form.html', form_action=url_for('disease_management.edit_disease', condition_id=condition_id),
            form_title=f"Edit Condition (ID: {condition_id})", disease=form_data, errors=errors,
            urgency_levels=urgency_levels, condition_types=condition_types, gender_relevance_opts=gender_relevance_opts,
            departments=departments, testing_types=testing_types, diagnosis_types=diagnosis_types,
            all_symptoms=all_symptoms, all_risk_factors=all_risk_factors, all_protocols=all_protocols,
            associated_symptom_ids=selected_symptom_ids, # Use lists captured in try block
            associated_factor_ids=selected_factor_ids,
            associated_protocol_ids=selected_protocol_ids
        )

    # --- GET request ---
    disease = get_disease_details_basic(condition_id)
    if not disease:
        flash("Condition not found or is inactive.", "warning")
        return redirect(url_for('disease_management.list_diseases'))
    associated_ids = get_associated_ids(condition_id) # Fetch currently associated IDs

    return render_template(
        'Doctor_Portal/Diseases/disease_form.html', form_action=url_for('disease_management.edit_disease', condition_id=condition_id),
        form_title=f"Edit Condition: {disease.get('condition_name', 'N/A')}", disease=disease,
        urgency_levels=urgency_levels, condition_types=condition_types, gender_relevance_opts=gender_relevance_opts,
        departments=departments, testing_types=testing_types, diagnosis_types=diagnosis_types,
        all_symptoms=all_symptoms, all_risk_factors=all_risk_factors, all_protocols=all_protocols,
        associated_symptom_ids=associated_ids['symptoms'], # Pass lists fetched from DB
        associated_factor_ids=associated_ids['factors'],
        associated_protocol_ids=associated_ids['protocols']
    )

@disease_management_bp.route('/<int:condition_id>/deactivate', methods=['POST'])
@login_required
def deactivate_disease(condition_id):
    """Soft deletes (deactivates) a condition."""
    if not check_doctor_authorization(current_user): abort(403)
    conn = None; cursor = None;
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction()
        cursor = conn.cursor()
        sql = "UPDATE conditions SET is_active = FALSE, updated_at = NOW() WHERE condition_id = %s"
        cursor.execute(sql, (condition_id,))
        if cursor.rowcount == 0: flash("Condition not found or already inactive.", "warning"); conn.rollback()
        else: conn.commit(); flash("Condition deactivated successfully.", "success")
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback();
        current_app.logger.error(f"DB/Connection Error Deactivating Condition {condition_id}: {err}")
        flash("Database error deactivating condition.", "danger")
    except Exception as e:
         if conn and conn.is_connected(): conn.rollback();
         current_app.logger.error(f"Unexpected Error Deactivating Condition {condition_id}: {e}", exc_info=True)
         flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('disease_management.list_diseases'))

# --- Route for serving uploaded images ---
@disease_management_bp.route('/images/<path:filename>')
def uploaded_disease_image(filename):
    """Serves uploaded disease images."""
    directory = current_app.config.get('UPLOAD_FOLDER_DISEASE_IMAGES')
    if not directory:
        current_app.logger.error("UPLOAD_FOLDER_DISEASE_IMAGES not configured for serving.")
        abort(404)
    try:
        return send_from_directory(directory, filename)
    except FileNotFoundError:
         current_app.logger.warning(f"Requested image not found: {filename} in {directory}")
         abort(404)

# --- END OF disease_management.py ---