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
# *** UPDATED VALID_SORT_COLUMNS to include new related table names ***
VALID_SORT_COLUMNS = {
    'name': 'pc.condition_name', 'code': 'pc.icd_code',
    'type': 'pc.condition_type', 'urgency': 'pc.urgency_level',
    'id': 'pc.condition_id', 'dept': 'd.name',
    'test_type': 'tt.name', 'diag_type': 'dt.name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE = {} # Simple cache for ENUM values

# --- Helper Functions ---

def allowed_file(filename):
    """Checks if the filename has an allowed extension."""
    # Ensure UPLOAD_FOLDER is configured in Flask app config
    ALLOWED_EXTENSIONS = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_disease_image(file):
    """Saves the uploaded image file securely."""
    # Ensure UPLOAD_FOLDER is configured in Flask app config
    upload_folder = current_app.config.get('UPLOAD_FOLDER_DISEASE_IMAGES') # Use a specific folder if desired
    if not upload_folder:
        current_app.logger.error("UPLOAD_FOLDER_DISEASE_IMAGES not configured.")
        return None

    if file and allowed_file(file.filename):
        # Generate a unique filename to prevent collisions and secure original name
        original_filename = secure_filename(file.filename)
        ext = ''
        if '.' in original_filename:
            ext = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename[:50]}.{ext}" if ext else f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename[:50]}"
        unique_filename = secure_filename(unique_filename) # Secure the generated name too

        filepath = os.path.join(upload_folder, unique_filename)
        try:
            os.makedirs(upload_folder, exist_ok=True) # Ensure directory exists
            file.save(filepath)
            # Return filename relative to static folder for web access
            relative_path = os.path.join('uploads', 'disease_images', unique_filename).replace(os.path.sep, '/')
            return relative_path # Return the relative path for DB storage
        except Exception as e:
            current_app.logger.error(f"Failed to save image {unique_filename}: {e}")
            # Attempt cleanup if save fails partially
            if os.path.exists(filepath):
                try: os.remove(filepath)
                except OSError: pass
            return None
    return None

def delete_disease_image(filename_relative_path):
    """Deletes an image file if it exists using the relative path stored in DB."""
    if not filename_relative_path: return False
    # Construct full path from static folder root + relative path
    filepath = os.path.join(current_app.static_folder, filename_relative_path)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            current_app.logger.info(f"Deleted image file: {filepath}")
            return True
        else:
            current_app.logger.warning(f"Image file not found for deletion: {filepath}")
            return False
    except Exception as e:
        current_app.logger.error(f"Error deleting image file {filepath}: {e}")
    return False


def get_enum_values(table_name, column_name):
    """ Helper to get ENUM values from DB schema. Caches results. """
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE:
        return ENUM_CACHE[cache_key]

    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor()
        db_name = conn.database
        query = f"""
            SELECT COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]: # Check if result and column_type are not None
            enum_str = result[0]
            # Handle potential bytes response from db
            if isinstance(enum_str, bytes):
                enum_str = enum_str.decode('utf-8')

            if enum_str.startswith('enum(') and enum_str.endswith(')'):
                 # More robust parsing for single quotes and potential spaces
                 raw_values = enum_str[len('enum('):-1].split(',')
                 values = [val.strip().strip("'") for val in raw_values]
            else:
                 current_app.logger.warning(f"Column {table_name}.{column_name} is not an ENUM or format unexpected: {enum_str}")
        else:
             current_app.logger.warning(f"Could not retrieve ENUM definition for {table_name}.{column_name}")

        ENUM_CACHE[cache_key] = values
        return values
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}")
        return [] # Return empty list on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Data Fetching Helpers ---

def get_all_simple(table_name, id_col, name_col, order_col=None):
    """ Generic helper to fetch ID/Name pairs from simple tables, allowing custom order column """
    conn = None; cursor = None; items = []
    order_by = order_col if order_col else name_col # Default order by name_col if not specified
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        # Basic security check for column names if dynamic (not strictly needed here as they are hardcoded in calls)
        safe_id_col = id_col # Assume safe as it's from code
        safe_name_col = name_col # Assume safe
        safe_order_col = order_by # Assume safe
        safe_table_name = table_name # Assume safe

        query = f"SELECT `{safe_id_col}`, `{safe_name_col}` FROM `{safe_table_name}` ORDER BY `{safe_order_col}` ASC"
        cursor.execute(query)
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching from {safe_table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

# *** ADDED Helpers for new lookup tables ***
def get_all_departments():
    return get_all_simple('departments', 'department_id', 'name')

def get_all_testing_types():
    return get_all_simple('testing_types', 'testing_type_id', 'name')

def get_all_diagnosis_types():
    return get_all_simple('diagnosis_types', 'diagnosis_type_id', 'name')


def get_paginated_diseases(page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
    """Fetches paginated, filtered, and sorted potential conditions including related type names."""
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        # *** QUERY UPDATED with JOINs for new FKs ***
        sql_select = """
            SELECT SQL_CALC_FOUND_ROWS
                pc.condition_id, pc.condition_name, pc.icd_code,
                pc.condition_type, pc.urgency_level,
                d.name as department_name,
                tt.name as testing_type_name,
                dt.name as diagnosis_type_name,
                pc.disease_image_filename -- Include image for potential thumbnail
        """
        sql_from = """
            FROM potential_conditions pc
            LEFT JOIN departments d ON pc.department_id = d.department_id
            LEFT JOIN testing_types tt ON pc.testing_type_id = tt.testing_type_id
            LEFT JOIN diagnosis_types dt ON pc.diagnosis_type_id = dt.diagnosis_type_id
        """
        sql_where = " WHERE pc.is_active = TRUE"
        params = []

        # Search logic (seems okay)
        if search_term:
            search_like = f"%{search_term}%"
            sql_where += """
                AND (pc.condition_name LIKE %s OR pc.description LIKE %s OR pc.icd_code LIKE %s
                     OR pc.overview LIKE %s OR pc.symptoms_text LIKE %s OR pc.causes_text LIKE %s)
            """
            params.extend([search_like] * 6)

        # Filter logic (updated for department_id)
        if valid_filters.get('urgency'):
            sql_where += " AND pc.urgency_level = %s"
            params.append(valid_filters['urgency'])
        if valid_filters.get('type'):
            sql_where += " AND pc.condition_type = %s"
            params.append(valid_filters['type'])
        if valid_filters.get('department_id'):
            sql_where += " AND pc.department_id = %s"
            params.append(valid_filters['department_id'])
        # *** ADD filters for testing/diagnosis types if needed on list view ***
        if valid_filters.get('testing_type_id'):
             sql_where += " AND pc.testing_type_id = %s"
             params.append(valid_filters['testing_type_id'])
        if valid_filters.get('diagnosis_type_id'):
             sql_where += " AND pc.diagnosis_type_id = %s"
             params.append(valid_filters['diagnosis_type_id'])


        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        # Get total count (seems okay)
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

        # 1. Get Condition Details (including new fields and joined names)
        # *** QUERY UPDATED with JOINs for new FKs ***
        query_cond = """
            SELECT
                pc.*,
                tt.name as testing_type_name,
                dt.name as diagnosis_type_name,
                d.name as department_name
            FROM potential_conditions pc
            LEFT JOIN testing_types tt ON pc.testing_type_id = tt.testing_type_id
            LEFT JOIN diagnosis_types dt ON pc.diagnosis_type_id = dt.diagnosis_type_id
            LEFT JOIN departments d ON pc.department_id = d.department_id
            WHERE pc.condition_id = %s AND pc.is_active = TRUE
        """
        cursor.execute(query_cond, (condition_id,))
        details['condition'] = cursor.fetchone()
        if not details['condition']: return None # Not found or inactive

        # 2. Get Associated Symptoms (No change needed here)
        query_sym = """SELECT s.symptom_id, s.symptom_name, scm.weight, scm.is_required FROM symptoms s JOIN symptom_condition_map scm ON s.symptom_id = scm.symptom_id WHERE scm.condition_id = %s ORDER BY s.symptom_name"""
        cursor.execute(query_sym, (condition_id,))
        details['symptoms'] = cursor.fetchall()

        # 3. Get Associated Risk Factors (No change needed here)
        query_rf = """SELECT rf.factor_id, rf.factor_name, rf.factor_type, crf.weight FROM risk_factors rf JOIN condition_risk_factors crf ON rf.factor_id = crf.factor_id WHERE crf.condition_id = %s ORDER BY rf.factor_name"""
        cursor.execute(query_rf, (condition_id,))
        details['risk_factors'] = cursor.fetchall()

        # 4. Get Associated Protocols (No change needed here)
        query_pro = """SELECT tp.protocol_id, tp.protocol_name, tp.guideline_url, cp.relevance FROM treatment_protocols tp JOIN condition_protocols cp ON tp.protocol_id = cp.protocol_id WHERE cp.condition_id = %s ORDER BY cp.relevance, tp.protocol_name"""
        cursor.execute(query_pro, (condition_id,))
        details['protocols'] = cursor.fetchall()

        # 5. Get Associated Doctors (Based on condition's department_id)
        department_id = details['condition'].get('department_id')
        if department_id:
            # *** QUERY UPDATED to join users and select relevant user fields ***
            query_docs = """
                SELECT
                    doc.user_id as doctor_user_id, u.first_name, u.last_name, u.email,
                    u.profile_picture, s.name as specialization_name -- Added specialization name
                FROM doctors doc
                JOIN users u ON doc.user_id = u.user_id
                LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id -- Added join for specialization
                WHERE doc.department_id = %s
                  AND u.user_type = 'doctor' AND u.account_status = 'active'
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

# Simplified get_disease_details for edit form pre-population (seems okay)
def get_disease_details_basic(condition_id):
     conn = None; cursor = None;
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor(dictionary=True)
         # Select all columns needed for the form, including the new FK IDs
         cursor.execute("SELECT * FROM potential_conditions WHERE condition_id = %s AND is_active = TRUE", (condition_id,))
         return cursor.fetchone()
     except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching basic disease details for ID {condition_id}: {err}")
        return None
     finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# --- Routes ---

@disease_management_bp.route('/', methods=['GET'])
@login_required
def list_diseases():
    """Displays the paginated, filterable, sortable list of diseases."""
    if not check_doctor_authorization(current_user): abort(403)

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    filter_urgency = request.args.get('filter_urgency', '')
    filter_type = request.args.get('filter_type', '')
    filter_department = request.args.get('filter_department', type=int) # Changed to int
    filter_testing_type = request.args.get('filter_testing_type', type=int) # Added
    filter_diagnosis_type = request.args.get('filter_diagnosis_type', type=int) # Added


    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    filters = {}
    if filter_urgency: filters['urgency'] = filter_urgency
    if filter_type: filters['type'] = filter_type
    if filter_department: filters['department_id'] = filter_department
    if filter_testing_type: filters['testing_type_id'] = filter_testing_type # Added
    if filter_diagnosis_type: filters['diagnosis_type_id'] = filter_diagnosis_type # Added


    result = get_paginated_diseases(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    diseases = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0

    # Get Enum/Dropdown values for filters
    urgency_levels = get_enum_values('potential_conditions', 'urgency_level')
    condition_types = get_enum_values('potential_conditions', 'condition_type')
    departments = get_all_departments() # Fetch departments for filter dropdown
    testing_types = get_all_testing_types() # Added
    diagnosis_types = get_all_diagnosis_types() # Added


    return render_template(
        'Doctor_Portal/Diseases/disease_list.html', # Adjusted path
        diseases=diseases,
        search_term=search_term,
        current_page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=filters,
        urgency_levels=urgency_levels,
        condition_types=condition_types,
        departments=departments,
        testing_types=testing_types, # Pass testing types
        diagnosis_types=diagnosis_types, # Pass diagnosis types
        valid_sort_columns=VALID_SORT_COLUMNS
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

    # Fetch lists for the Add dropdowns on this page (seems okay)
    all_symptoms = get_all_simple('symptoms', 'symptom_id', 'symptom_name')
    all_risk_factors = get_all_simple('risk_factors', 'factor_id', 'factor_name')
    all_protocols = get_all_simple('treatment_protocols', 'protocol_id', 'protocol_name')

    return render_template(
        'Doctor_Portal/Diseases/disease_detail.html', # Adjusted path
        details=disease_details,
        all_symptoms=all_symptoms,
        all_risk_factors=all_risk_factors,
        all_protocols=all_protocols
        )

@disease_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_disease():
    """Handles adding a new disease/condition."""
    if not check_doctor_authorization(current_user): abort(403)

    # Fetch options for dropdowns (including new ones)
    urgency_levels = get_enum_values('potential_conditions', 'urgency_level')
    condition_types = get_enum_values('potential_conditions', 'condition_type')
    gender_relevance_opts = get_enum_values('potential_conditions', 'gender_relevance')
    departments = get_all_departments()
    testing_types = get_all_testing_types()
    diagnosis_types = get_all_diagnosis_types()

    if request.method == 'POST':
        conn = None; cursor = None; errors = []; saved_filename_relative = None
        try:
            # --- Get form data (including new IDs) ---
            name = request.form.get('condition_name', '').strip()
            desc = request.form.get('description', '').strip() or None
            icd = request.form.get('icd_code', '').strip() or None
            urgency = request.form.get('urgency_level')
            cond_type = request.form.get('condition_type') or None # Allow empty/None
            age_rel = request.form.get('age_relevance', '').strip() or None
            gender_rel = request.form.get('gender_relevance')
            specialist = request.form.get('specialist_type', '').strip() or None
            self_treat = request.form.get('self_treatable') == 'on'
            duration = request.form.get('typical_duration', '').strip() or None
            edu_content = request.form.get('educational_content', '').strip() or None
            overview = request.form.get('overview', '').strip() or None
            symptoms_text = request.form.get('symptoms_text', '').strip() or None
            causes_text = request.form.get('causes_text', '').strip() or None
            testing_details = request.form.get('testing_details', '').strip() or None
            diagnosis_details = request.form.get('diagnosis_details', '').strip() or None
            # *** Get new IDs, defaulting to None if empty or invalid ***
            testing_type_id = request.form.get('testing_type_id', type=int) if request.form.get('testing_type_id') else None
            diagnosis_type_id = request.form.get('diagnosis_type_id', type=int) if request.form.get('diagnosis_type_id') else None
            department_id = request.form.get('department_id', type=int) if request.form.get('department_id') else None

            # --- Validation ---
            if not name: errors.append("Condition Name is required.")
            if not urgency or urgency not in urgency_levels: errors.append("Valid Urgency Level is required.")
            if cond_type and cond_type not in condition_types: errors.append("Invalid Condition Type selected.") # Check if provided but invalid
            if not gender_rel or gender_rel not in gender_relevance_opts: errors.append("Valid Gender Relevance is required.")
            # Note: department, testing/diagnosis types might be optional (schema allows NULL)
            # Add validation if they *are* required by business logic

            # --- Handle File Upload ---
            image_file = request.files.get('disease_image')
            if image_file and image_file.filename != '':
                saved_filename_relative = save_disease_image(image_file)
                if not saved_filename_relative:
                    errors.append("Failed to save disease image.")

            if errors: raise ValueError("Validation errors occurred.") # Simplified raise

            # --- Database Insert (with new IDs) ---
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction() # Use transaction
            cursor = conn.cursor()
            sql = """
                INSERT INTO potential_conditions (
                    condition_name, description, icd_code, urgency_level, condition_type,
                    age_relevance, gender_relevance, specialist_type, self_treatable,
                    typical_duration, educational_content, overview, symptoms_text,
                    causes_text, testing_details, diagnosis_details, disease_image_filename,
                    testing_type_id, diagnosis_type_id, department_id, is_active,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, TRUE, NOW(), NOW()
                )
            """
            params = (
                name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist,
                self_treat, duration, edu_content, overview, symptoms_text, causes_text,
                testing_details, diagnosis_details, saved_filename_relative,
                testing_type_id, diagnosis_type_id, department_id # Pass new IDs
            )
            cursor.execute(sql, params);
            conn.commit() # Commit transaction
            flash(f"Condition '{name}' added successfully.", "success")
            return redirect(url_for('disease_management.list_diseases'))

        except ValueError: # Catch validation errors specifically
            if saved_filename_relative: delete_disease_image(saved_filename_relative) # Cleanup file if validation fails
            for err_msg in errors: flash(err_msg, 'danger') # Flash individual errors
        except (mysql.connector.Error, ConnectionError, IOError) as err: # Catch DB, connection, file errors
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative: delete_disease_image(saved_filename_relative) # Cleanup file on DB/IO error
            current_app.logger.error(f"DB/Connection/IO Error Adding Condition: {err}")
            flash_msg = f"Database/File error: {err}"
            if isinstance(err, mysql.connector.Error) and err.errno == 1062:
                flash_msg = "Database error: Condition name or ICD code might already exist."
            flash(flash_msg, "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            if saved_filename_relative: delete_disease_image(saved_filename_relative) # Cleanup file on unexpected error
            current_app.logger.error(f"Unexpected Error Adding Condition: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error, preserving input
        return render_template(
            'Doctor_Portal/Diseases/disease_form.html', # Adjusted path
            form_action=url_for('disease_management.add_disease'),
            form_title="Add New Disease/Condition",
            disease=request.form, # Pass form data back
            urgency_levels=urgency_levels, condition_types=condition_types,
            gender_relevance_opts=gender_relevance_opts, departments=departments,
            testing_types=testing_types, diagnosis_types=diagnosis_types,
            errors=errors # Pass validation errors to template if needed
        )

    # GET request
    return render_template(
        'Doctor_Portal/Diseases/disease_form.html', # Adjusted path
        form_action=url_for('disease_management.add_disease'),
        form_title="Add New Disease/Condition",
        disease=None, # No existing data for add form
        urgency_levels=urgency_levels, condition_types=condition_types,
        gender_relevance_opts=gender_relevance_opts, departments=departments,
        testing_types=testing_types, diagnosis_types=diagnosis_types
    )


@disease_management_bp.route('/<int:condition_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_disease(condition_id):
    """Handles editing an existing disease/condition."""
    if not check_doctor_authorization(current_user): abort(403)

    # Fetch options for dropdowns
    urgency_levels = get_enum_values('potential_conditions', 'urgency_level')
    condition_types = get_enum_values('potential_conditions', 'condition_type')
    gender_relevance_opts = get_enum_values('potential_conditions', 'gender_relevance')
    departments = get_all_departments()
    testing_types = get_all_testing_types()
    diagnosis_types = get_all_diagnosis_types()

    conn = None; cursor = None;

    if request.method == 'POST':
        errors = []; saved_filename_relative = None # Relative path of newly uploaded file
        # Get existing filename from hidden field to manage deletion
        previous_filename_relative = request.form.get('current_disease_image_filename')
        try:
            # --- Get form data (including new IDs) ---
            name = request.form.get('condition_name', '').strip()
            desc = request.form.get('description', '').strip() or None
            icd = request.form.get('icd_code', '').strip() or None
            urgency = request.form.get('urgency_level')
            cond_type = request.form.get('condition_type') or None
            age_rel = request.form.get('age_relevance', '').strip() or None
            gender_rel = request.form.get('gender_relevance')
            specialist = request.form.get('specialist_type', '').strip() or None
            self_treat = request.form.get('self_treatable') == 'on'
            duration = request.form.get('typical_duration', '').strip() or None
            edu_content = request.form.get('educational_content', '').strip() or None
            overview = request.form.get('overview', '').strip() or None
            symptoms_text = request.form.get('symptoms_text', '').strip() or None
            causes_text = request.form.get('causes_text', '').strip() or None
            testing_details = request.form.get('testing_details', '').strip() or None
            diagnosis_details = request.form.get('diagnosis_details', '').strip() or None
            # *** Get new IDs, defaulting to None ***
            testing_type_id = request.form.get('testing_type_id', type=int) if request.form.get('testing_type_id') else None
            diagnosis_type_id = request.form.get('diagnosis_type_id', type=int) if request.form.get('diagnosis_type_id') else None
            department_id = request.form.get('department_id', type=int) if request.form.get('department_id') else None

            # --- Validation ---
            if not name: errors.append("Condition Name is required.")
            if not urgency or urgency not in urgency_levels: errors.append("Valid Urgency Level is required.")
            # ... other validations ...

            # --- Handle File Upload & Deletion ---
            image_file = request.files.get('disease_image')
            delete_current_image = request.form.get('delete_image') == 'on'
            final_filename_relative = previous_filename_relative # Assume keeping old file initially

            if delete_current_image:
                 if previous_filename_relative:
                     if delete_disease_image(previous_filename_relative):
                          final_filename_relative = None # Mark for DB update to NULL
                     else:
                          errors.append("Failed to delete the current image file.")
                 else:
                      final_filename_relative = None # Was already no image
                 # Ignore any newly uploaded file if delete is checked
            elif image_file and image_file.filename != '':
                # New file uploaded, replace old one
                saved_filename_relative = save_disease_image(image_file) # Attempt to save new
                if saved_filename_relative:
                    # Delete the old file *after* successfully saving the new one
                    if previous_filename_relative:
                         delete_disease_image(previous_filename_relative) # Attempt deletion, ignore failure for now
                    final_filename_relative = saved_filename_relative # Use the new relative path
                else:
                    errors.append("Failed to save the new disease image.")
                    # Keep the old filename if new save failed
                    final_filename_relative = previous_filename_relative
            # Else: No new file uploaded, delete not checked -> Keep final_filename_relative = previous_filename_relative

            if errors: raise ValueError("Validation or file handling errors occurred.")

            # --- Perform UPDATE (with new IDs and filename) ---
            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            conn.start_transaction() # Use transaction
            cursor = conn.cursor()
            sql = """
                UPDATE potential_conditions SET
                    condition_name=%s, description=%s, icd_code=%s, urgency_level=%s, condition_type=%s,
                    age_relevance=%s, gender_relevance=%s, specialist_type=%s, self_treatable=%s,
                    typical_duration=%s, educational_content=%s, overview=%s, symptoms_text=%s,
                    causes_text=%s, testing_details=%s, diagnosis_details=%s, disease_image_filename=%s,
                    testing_type_id=%s, diagnosis_type_id=%s, department_id=%s,
                    updated_at=NOW()
                WHERE condition_id=%s AND is_active = TRUE
            """
            params = (
                name, desc, icd, urgency, cond_type, age_rel, gender_rel, specialist,
                self_treat, duration, edu_content, overview, symptoms_text, causes_text,
                testing_details, diagnosis_details, final_filename_relative, # Use final path
                testing_type_id, diagnosis_type_id, department_id, # Pass new IDs
                condition_id
            )
            cursor.execute(sql, params);
            if cursor.rowcount == 0:
                # Handle case where condition_id doesn't exist or is inactive
                conn.rollback() # Important: rollback if update failed
                flash("Condition not found or is inactive, update failed.", "warning")
                # If a new file was saved, delete it because the DB update failed
                if saved_filename_relative and saved_filename_relative != previous_filename_relative:
                    delete_disease_image(saved_filename_relative)
                return redirect(url_for('disease_management.list_diseases'))

            conn.commit() # Commit transaction
            flash(f"Condition '{name}' updated successfully.", "success")
            return redirect(url_for('disease_management.view_disease', condition_id=condition_id)) # Redirect to detail view

        except ValueError: # Catch validation/file errors specifically
            # If validation fails *after* saving a new file, delete it
            if saved_filename_relative and saved_filename_relative != previous_filename_relative:
                delete_disease_image(saved_filename_relative)
            for err_msg in errors: flash(err_msg, 'danger')
        except (mysql.connector.Error, ConnectionError, IOError) as err: # Catch DB, connection, file errors
            if conn and conn.is_connected(): conn.rollback()
            # If DB error *after* saving a new file, delete it
            if saved_filename_relative and saved_filename_relative != previous_filename_relative:
                 delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"DB/Connection/IO Error Editing Condition {condition_id}: {err}")
            flash("Database or file error updating condition.", "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            # If other error *after* saving a new file, delete it
            if saved_filename_relative and saved_filename_relative != previous_filename_relative:
                 delete_disease_image(saved_filename_relative)
            current_app.logger.error(f"Unexpected Error Editing Condition {condition_id}: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render edit form on error with submitted data
        form_data = request.form.to_dict()
        form_data['condition_id'] = condition_id # Add id back for template action URL
        # Ensure the image filename reflects the state *before* the failed attempt
        form_data['disease_image_filename'] = previous_filename_relative
        return render_template(
            'Doctor_Portal/Diseases/disease_form.html', # Adjusted path
            form_action=url_for('disease_management.edit_disease', condition_id=condition_id),
            form_title=f"Edit Condition (ID: {condition_id})",
            disease=form_data, # Pass submitted data back
            urgency_levels=urgency_levels, condition_types=condition_types,
            gender_relevance_opts=gender_relevance_opts, departments=departments,
            testing_types=testing_types, diagnosis_types=diagnosis_types,
            errors=errors # Pass errors for display
        )

    # --- GET request ---
    disease = get_disease_details_basic(condition_id) # Fetch current data
    if not disease:
        flash("Condition not found or is inactive.", "warning")
        return redirect(url_for('disease_management.list_diseases'))

    return render_template(
        'Doctor_Portal/Diseases/disease_form.html', # Adjusted path
        form_action=url_for('disease_management.edit_disease', condition_id=condition_id),
        form_title=f"Edit Condition: {disease.get('condition_name', 'N/A')}",
        disease=disease, # Pass existing data (already includes new FK IDs)
        urgency_levels=urgency_levels, condition_types=condition_types,
        gender_relevance_opts=gender_relevance_opts, departments=departments,
        testing_types=testing_types, diagnosis_types=diagnosis_types
    )


@disease_management_bp.route('/<int:condition_id>/deactivate', methods=['POST'])
@login_required
def deactivate_disease(condition_id):
    """Soft deletes (deactivates) a condition. (No change needed here)"""
    if not check_doctor_authorization(current_user): abort(403)
    conn = None; cursor = None;
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction() # Use transaction
        cursor = conn.cursor()
        sql = "UPDATE potential_conditions SET is_active = FALSE, updated_at = NOW() WHERE condition_id = %s"
        cursor.execute(sql, (condition_id,))
        if cursor.rowcount == 0:
            flash("Condition not found or already inactive.", "warning")
            conn.rollback() # Rollback if no rows affected
        else:
            conn.commit()
            flash("Condition deactivated successfully.", "success")
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_app.logger.error(f"DB/Connection Error Deactivating Condition {condition_id}: {err}")
        flash("Database error deactivating condition.", "danger")
    except Exception as e:
         if conn and conn.is_connected(): conn.rollback()
         current_app.logger.error(f"Unexpected Error Deactivating Condition {condition_id}: {e}", exc_info=True)
         flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('disease_management.list_diseases'))


# == AJAX routes for managing associations on the detail page ==
# (These AJAX routes for symptoms, risk factors, protocols remain largely the same
# as they operate on the junction tables which were not the primary focus of this schema change)
# --- Symptom Linking ---
@disease_management_bp.route('/<int:condition_id>/symptoms', methods=['POST'])
@login_required
def link_symptom(condition_id):
    # (Code from your provided file - appears functionally correct for its purpose)
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
    data = request.get_json()
    if not data: return jsonify(success=False, message="Invalid request data"), 400
    symptom_id = data.get('symptom_id')
    weight = data.get('weight', 1.0); is_required = data.get('is_required', False)
    if not symptom_id: return jsonify(success=False, message="Symptom ID required"), 400
    conn = None; cursor = None;
    try:
        symptom_id = int(symptom_id); weight = float(weight); is_required = bool(is_required)
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction() # Use transaction
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM symptom_condition_map WHERE condition_id = %s AND symptom_id = %s", (condition_id, symptom_id))
        if cursor.fetchone(): return jsonify(success=False, message="Symptom already linked."), 409
        cursor.execute("SELECT symptom_name FROM symptoms WHERE symptom_id = %s", (symptom_id,))
        symptom_info = cursor.fetchone()
        if not symptom_info: return jsonify(success=False, message="Symptom not found"), 404
        sql = "INSERT INTO symptom_condition_map (condition_id, symptom_id, weight, is_required) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql, (condition_id, symptom_id, weight, is_required));
        conn.commit()
        return jsonify(success=True, message=f"Symptom '{symptom_info['symptom_name']}' linked.", linked_item={'id': symptom_id, 'name': symptom_info['symptom_name'], 'weight': weight, 'is_required': is_required})
    except (ValueError, TypeError) as ve: return jsonify(success=False, message=f"Invalid input: {ve}"), 400
    except mysql.connector.Error as err:
        if conn: conn.rollback(); current_app.logger.error(f"Link symptom DB Error: {err}")
        msg = "Database error linking symptom."
        if err.errno == 1452: msg = "Invalid Condition ID or Symptom ID."
        return jsonify(success=False, message=msg), 500
    except ConnectionError as ce: current_app.logger.error(f"Link symptom Conn Error: {ce}"); return jsonify(success=False, message="DB connection error."), 500
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Link symptom error: {e}", exc_info=True)
        return jsonify(success=False, message="An unexpected error occurred."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Symptom Unlinking ---
@disease_management_bp.route('/<int:condition_id>/symptoms/<int:symptom_id>', methods=['DELETE'])
@login_required
def unlink_symptom(condition_id, symptom_id):
     # (Code from your provided file - appears functionally correct)
     if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
     conn = None; cursor = None;
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         conn.start_transaction() # Use transaction
         cursor = conn.cursor()
         sql = "DELETE FROM symptom_condition_map WHERE condition_id = %s AND symptom_id = %s"
         cursor.execute(sql, (condition_id, symptom_id));
         rowcount = cursor.rowcount
         conn.commit()
         if rowcount == 0: return jsonify(success=False, message="Link not found."), 404
         return jsonify(success=True, message="Symptom link removed")
     except (mysql.connector.Error, ConnectionError) as err:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink symptom DB/Conn Error: {err}")
         return jsonify(success=False, message="Database error removing link."), 500
     except Exception as e:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink symptom error: {e}", exc_info=True)
         return jsonify(success=False, message="An unexpected error occurred."), 500
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()


# --- Risk Factor Linking ---
@disease_management_bp.route('/<int:condition_id>/risk_factors', methods=['POST'])
@login_required
def link_risk_factor(condition_id):
    # (Code from your provided file - appears functionally correct)
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
    data = request.get_json();
    if not data: return jsonify(success=False, message="Invalid request data"), 400
    factor_id = data.get('factor_id'); weight = data.get('weight', 1.0)
    if not factor_id: return jsonify(success=False, message="Risk Factor ID required"), 400
    conn = None; cursor = None;
    try:
        factor_id = int(factor_id); weight = float(weight)
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction() # Use transaction
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM condition_risk_factors WHERE condition_id = %s AND factor_id = %s", (condition_id, factor_id))
        if cursor.fetchone(): return jsonify(success=False, message="Risk Factor already linked."), 409
        cursor.execute("SELECT factor_name, factor_type FROM risk_factors WHERE factor_id = %s", (factor_id,))
        factor_info = cursor.fetchone()
        if not factor_info: return jsonify(success=False, message="Risk Factor not found"), 404
        sql = "INSERT INTO condition_risk_factors (condition_id, factor_id, weight) VALUES (%s, %s, %s)"
        cursor.execute(sql, (condition_id, factor_id, weight));
        conn.commit()
        return jsonify(success=True, message=f"Risk Factor '{factor_info['factor_name']}' linked.", linked_item={'id': factor_id, 'name': factor_info['factor_name'], 'weight': weight, 'type': factor_info['factor_type']})
    except (ValueError, TypeError) as ve: return jsonify(success=False, message=f"Invalid input: {ve}"), 400
    except mysql.connector.Error as err:
        if conn: conn.rollback(); current_app.logger.error(f"Link risk factor DB Error: {err}")
        msg = "Database error linking risk factor."
        if err.errno == 1452: msg = "Invalid Condition or Factor ID."
        return jsonify(success=False, message=msg), 500
    except ConnectionError as ce: current_app.logger.error(f"Link risk factor Conn Error: {ce}"); return jsonify(success=False, message="DB connection error."), 500
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Link risk factor error: {e}", exc_info=True)
        return jsonify(success=False, message="An unexpected error occurred."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# --- Risk Factor Unlinking ---
@disease_management_bp.route('/<int:condition_id>/risk_factors/<int:factor_id>', methods=['DELETE'])
@login_required
def unlink_risk_factor(condition_id, factor_id):
     # (Code from your provided file - appears functionally correct)
     if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
     conn = None; cursor = None;
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         conn.start_transaction() # Use transaction
         cursor = conn.cursor()
         sql = "DELETE FROM condition_risk_factors WHERE condition_id = %s AND factor_id = %s"
         cursor.execute(sql, (condition_id, factor_id));
         rowcount = cursor.rowcount
         conn.commit()
         if rowcount == 0: return jsonify(success=False, message="Risk Factor link not found."), 404
         return jsonify(success=True, message="Risk Factor link removed")
     except (mysql.connector.Error, ConnectionError) as err:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink risk factor DB/Conn Error: {err}")
         return jsonify(success=False, message="Database error removing link."), 500
     except Exception as e:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink risk factor error: {e}", exc_info=True)
         return jsonify(success=False, message="An unexpected error occurred."), 500
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()


# --- Protocol Linking ---
@disease_management_bp.route('/<int:condition_id>/protocols', methods=['POST'])
@login_required
def link_protocol(condition_id):
    # (Code from your provided file - appears functionally correct)
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
    data = request.get_json();
    if not data: return jsonify(success=False, message="Invalid request data"), 400
    protocol_id = data.get('protocol_id'); relevance = data.get('relevance', 'Recommended')
    if not protocol_id: return jsonify(success=False, message="Protocol ID required"), 400
    conn = None; cursor = None;
    try:
        protocol_id = int(protocol_id)
        # TODO: Add validation for 'relevance' against ENUM values if critical
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        conn.start_transaction() # Use transaction
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM condition_protocols WHERE condition_id = %s AND protocol_id = %s", (condition_id, protocol_id))
        if cursor.fetchone(): return jsonify(success=False, message="Protocol already linked."), 409
        cursor.execute("SELECT protocol_name, guideline_url FROM treatment_protocols WHERE protocol_id = %s", (protocol_id,))
        protocol_info = cursor.fetchone()
        if not protocol_info: return jsonify(success=False, message="Treatment Protocol not found"), 404
        sql = "INSERT INTO condition_protocols (condition_id, protocol_id, relevance) VALUES (%s, %s, %s)"
        cursor.execute(sql, (condition_id, protocol_id, relevance));
        conn.commit()
        return jsonify(success=True, message=f"Protocol '{protocol_info['protocol_name']}' linked.", linked_item={'id': protocol_id, 'name': protocol_info['protocol_name'], 'relevance': relevance, 'guideline_url': protocol_info['guideline_url']})
    except (ValueError, TypeError) as ve: return jsonify(success=False, message=f"Invalid input: {ve}"), 400
    except mysql.connector.Error as err:
        if conn: conn.rollback(); current_app.logger.error(f"Link protocol DB Error: {err}")
        msg = "Database error linking protocol."
        if err.errno == 1452: msg = "Invalid Condition or Protocol ID."
        return jsonify(success=False, message=msg), 500
    except ConnectionError as ce: current_app.logger.error(f"Link protocol Conn Error: {ce}"); return jsonify(success=False, message="DB connection error."), 500
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Link protocol error: {e}", exc_info=True)
        return jsonify(success=False, message="An unexpected error occurred."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# --- Protocol Unlinking ---
@disease_management_bp.route('/<int:condition_id>/protocols/<int:protocol_id>', methods=['DELETE'])
@login_required
def unlink_protocol(condition_id, protocol_id):
     # (Code from your provided file - appears functionally correct)
     if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied"), 403
     conn = None; cursor = None;
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         conn.start_transaction() # Use transaction
         cursor = conn.cursor()
         sql = "DELETE FROM condition_protocols WHERE condition_id = %s AND protocol_id = %s"
         cursor.execute(sql, (condition_id, protocol_id));
         rowcount = cursor.rowcount
         conn.commit()
         if rowcount == 0: return jsonify(success=False, message="Protocol link not found."), 404
         return jsonify(success=True, message="Protocol link removed")
     except (mysql.connector.Error, ConnectionError) as err:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink protocol DB/Conn Error: {err}")
         return jsonify(success=False, message="Database error removing link."), 500
     except Exception as e:
         if conn: conn.rollback(); current_app.logger.error(f"Unlink protocol error: {e}", exc_info=True)
         return jsonify(success=False, message="An unexpected error occurred."), 500
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()
