# routes/Website/department.py

from flask import Blueprint, render_template, current_app, abort, url_for
import mysql.connector
import sys
import os
import re # Import regex for potential cleanup

# --- Database Connection Setup ---
# ... (keep as is) ...
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from db import get_db_connection
except ImportError:
    try:
        from db import get_db_connection
    except ImportError:
        print("CRITICAL ERROR: Failed to import get_db_connection. Check PYTHONPATH and db.py location.", file=sys.stderr)
        def get_db_connection():
            print("CRITICAL ERROR: get_db_connection is not available.", file=sys.stderr)
            return None

# --- Import Shared Functions ---
# ... (keep as is) ...
try:
    from .home import get_all_departments_from_db
except ImportError as e:
    print(f"WARNING: Could not import get_all_departments_from_db from .home. Error: {e}", file=sys.stderr)
    def get_all_departments_from_db():
        if current_app:
             current_app.logger.warning("Using fallback get_all_departments_from_db due to import error.")
        else:
             print("WARNING: Using fallback get_all_departments_from_db due to import error.", file=sys.stderr)
        return []


# --- Blueprint Definition ---
# ... (keep as is) ...
department_bp = Blueprint(
    'department',
    __name__,
    template_folder='../../templates',
    url_prefix='/departments'
)

# --- Helper: Simple Text Snippet Generation ---
def create_snippet(text, max_length=250, indicator="..."):
    """
    Creates a snippet from text if it exceeds max_length.
    Tries to break cleanly at sentence ends or spaces near the limit.
    Returns the snippet and a boolean indicating if more content exists.
    """
    if not text or len(text) <= max_length:
        return text, False # No snippet needed or text is short

    # Try to find a sentence end near the max_length
    end_sentence = text.rfind('.', 0, max_length + 1)
    if end_sentence > max_length * 0.7: # Found a sentence end reasonably close
        snippet = text[:end_sentence + 1]
        return snippet, True

    # Try to find a space near the max_length
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.7: # Found a space reasonably close
         snippet = text[:end_space] + indicator
         return snippet, True

    # Fallback: hard cut
    snippet = text[:max_length] + indicator
    return snippet, True

# --- Helper Functions ---

def get_department_by_id(dept_id):
    # ... (keep as is - no changes needed here for read more) ...
    """Fetches department details by ID, adds image URL and specific theme info."""
    department = None
    conn = None
    cursor = None
    logger = current_app.logger if current_app else print
    log_method_error = logger.error if hasattr(logger, 'error') else logger
    log_method_exception = logger.exception if hasattr(logger, 'exception') else logger

    try:
        conn = get_db_connection()
        if not conn:
             log_method_error(f"Failed to get DB connection for department ID {dept_id}")
             return None
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM departments WHERE department_id = %s"
        cursor.execute(query, (dept_id,))
        department = cursor.fetchone()

        if department:
            # Image URL construction using url_for (keep for images)
            db_filename = department.get('image_filename')
            department['image_url'] = url_for('static', filename=f"images/departments/{db_filename}") if db_filename else url_for('static', filename="images/departments/placeholder.jpg")

            # Theme/CSS mapping (Add your specific logic here)
            # REMOVED url_for for CSS paths - using direct strings relative to static folder
            # ASSUMPTION: CSS files are in 'static/website/' directory
            dept_name = department.get('name', '')
            if dept_name == 'Cardiology':
                department['specific_css'] = 'website/cardio.css' # FIXED
                department['hero_icon'] = 'fa-heart-pulse'
                department['hero_highlight'] = 'Cardiology'
                department['hero_main'] = 'Care'
            elif dept_name == 'Neurology':
                department['specific_css'] = 'website/neuro.css' # FIXED
                department['hero_icon'] = 'fa-brain'
                department['hero_highlight'] = 'Neurology'
                department['hero_main'] = 'Expertise'
            # Add elif blocks for other specific departments...
            else: # Default fallback
                department['specific_css'] = 'website/generic_department.css' # FIXED
                department['hero_icon'] = 'fa-stethoscope'
                department['hero_highlight'] = department.get('name', 'Medical')
                department['hero_main'] = 'Services'
                department['hero_images'] = []

    except mysql.connector.Error as db_err:
        log_method_error(f"Database error fetching department ID {dept_id}: {db_err}")
    except Exception as e:
        log_method_exception(f"Unexpected error fetching department ID {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department


def get_conditions_by_department(dept_id):
    # --- Added snippet generation for condition list descriptions ---
    """Fetches active conditions, generates short descriptions for list view."""
    conditions = []
    conn = None
    cursor = None
    logger = current_app.logger if current_app else print
    log_method_error = logger.error if hasattr(logger, 'error') else logger
    log_method_exception = logger.exception if hasattr(logger, 'exception') else logger
    SNIPPET_LENGTH_LIST = 100 # Shorter snippet for list view

    try:
        conn = get_db_connection()
        if not conn:
            log_method_error(f"Failed to get DB connection for conditions in dept {dept_id}")
            return []
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT condition_id, condition_name, description, condition_image_filename
            FROM conditions
            WHERE department_id = %s AND is_active = TRUE
            ORDER BY condition_name ASC
        """
        cursor.execute(query, (dept_id,))
        results = cursor.fetchall()
        for condition_data in results:
            # Keep url_for for images
            condition_img_filename = condition_data.get('condition_image_filename')
            condition_data['image_url'] = url_for('static', filename=f"images/conditions/{condition_img_filename}") if condition_img_filename else url_for('static', filename="images/conditions/disease_placeholder.png")

            condition_data['name'] = condition_data.get('condition_name')
            desc = condition_data.get('description', '')
            # Use helper to generate snippet for the list view
            condition_data['short_description'], _ = create_snippet(desc, SNIPPET_LENGTH_LIST) # Ignore 'has_more' flag for list view

            conditions.append(condition_data)
    except mysql.connector.Error as db_err:
         if db_err.errno == 1054:
             try: column_name = str(db_err).split("'")[1]
             except IndexError: column_name = "unknown"
             log_method_error(f"DB Error fetching conditions: Column '{column_name}' missing. Schema mismatch? Err: {db_err}")
         elif db_err.errno == 1146:
             log_method_error(f"DB Error fetching conditions: Table 'conditions' missing. Err: {db_err}")
         else:
             log_method_error(f"Database error fetching conditions for dept {dept_id}: {db_err}")
    except Exception as e:
        log_method_exception(f"Unexpected error fetching conditions for dept {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return conditions

def get_condition_details_by_id(condition_id):
    """
    Fetches detailed condition info, generates snippets for long text fields,
    and adds flags indicating if more content exists.
    """
    condition = None
    conn = None
    cursor = None
    logger = current_app.logger if current_app else print
    log_method_error = logger.error if hasattr(logger, 'error') else logger
    log_method_exception = logger.exception if hasattr(logger, 'exception') else logger
    SNIPPET_LENGTH_DETAIL = 250 # Define snippet length for detail view

    try:
        conn = get_db_connection()
        if not conn:
            log_method_error(f"Failed to get DB connection for condition ID {condition_id}")
            return None
        cursor = conn.cursor(dictionary=True)
        # Fetch all necessary fields
        query = """
            SELECT
                c.condition_id, c.condition_name AS name, c.description, c.overview,
                c.symptoms_text AS symptoms, c.causes_text AS causes,
                c.diagnosis_details AS diagnosis,
                c.testing_details AS testing, c.educational_content,
                c.icd_code, c.urgency_level, c.condition_type, c.age_relevance,
                c.gender_relevance, c.specialist_type, c.self_treatable,
                c.typical_duration, c.condition_image_filename,
                dept.name AS department_name, dept.department_id
            FROM conditions c
            LEFT JOIN departments dept ON c.department_id = dept.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query, (condition_id,))
        condition = cursor.fetchone()

        if condition:
            # --- Snippet Generation & Flags ---
            fields_to_snippet = [ 'symptoms', 'causes', 'diagnosis', 'testing', 'educational_content', 'emergency_info']
            for field in fields_to_snippet:
                full_text = condition.get(field)
                snippet, has_more = create_snippet(full_text, SNIPPET_LENGTH_DETAIL)
                condition[f"{field}_snippet"] = snippet # e.g., condition['symptoms_snippet']
                condition[f"{field}_has_more"] = has_more # e.g., condition['symptoms_has_more']
            # --- End Snippet Generation ---

            # Keep url_for for images
            img_file = condition.get('condition_image_filename')
            condition['image_url'] = url_for('static', filename=f"images/conditions/{img_file}") if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")

            # CSS Mapping (direct paths)
            dept_name = condition.get('department_name')
            if dept_name == 'Cardiology': condition['specific_css'] = 'website/cardisease.css'
            elif dept_name == 'Neurology': condition['specific_css'] = 'website/neurodisease.css'
            elif dept_name == 'Orthopedics': condition['specific_css'] = 'website/orthodisease.css'
            elif dept_name == 'Dermatology': condition['specific_css'] = 'website/dermadisease.css'
            elif dept_name == 'Oncology': condition['specific_css'] = 'website/oncologydisease.css'
            else: condition['specific_css'] = 'website/generic_disease.css'

            # Boolean Display
            if 'self_treatable' in condition and condition['self_treatable'] is not None:
                 condition['self_treatable_display'] = 'Yes' if condition['self_treatable'] else 'No'
            else:
                condition['self_treatable_display'] = 'N/A'

    except mysql.connector.Error as db_err:
         if db_err.errno == 1054:
             try: column_name = str(db_err).split("'")[1]
             except IndexError: column_name = "unknown"
             log_method_error(f"DB Error fetching condition details: Column '{column_name}' missing. Schema mismatch? Err: {db_err}")
         elif db_err.errno == 1146:
             log_method_error(f"DB Error fetching condition details: Table 'conditions' or 'departments' missing. Err: {db_err}")
         else:
             log_method_error(f"Database error fetching condition ID {condition_id}: {db_err}")
    except Exception as e:
        log_method_exception(f"Unexpected error fetching condition ID {condition_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return condition # Returns None if error or not found

def get_doctors_by_department(dept_id):
    # ... (keep as is - no changes needed here for read more) ...
    """Fetches active and approved doctors associated with a department ID."""
    doctors = []
    conn = None
    cursor = None
    logger = current_app.logger if current_app else print
    log_method_error = logger.error if hasattr(logger, 'error') else logger
    log_method_exception = logger.exception if hasattr(logger, 'exception') else logger

    try:
        conn = get_db_connection()
        if not conn:
             log_method_error(f"Failed to get DB connection for doctors in dept {dept_id}")
             return []
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name,
                u.profile_picture, d.specialization_id, s.name AS specialization_name,
                d.biography
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            WHERE
                u.user_type = 'doctor'
            AND u.account_status = 'active'
            AND d.department_id = %s
            AND d.verification_status = 'approved'
            ORDER BY u.last_name ASC, u.first_name ASC
        """
        params = (dept_id,)
        cursor.execute(query, params)
        doctors_raw = cursor.fetchall()
        for doc in doctors_raw:
            doc['specialization'] = doc.get('specialization_name', 'Specialist')
            # Keep url_for for images
            profile_pic_filename = doc.get('profile_picture')
            if profile_pic_filename:
                doc['profile_picture_url'] = url_for('static', filename=f'images/profile_pics/{profile_pic_filename}')
            else:
                doc['profile_picture_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')
            bio = doc.get('biography')
            doc['short_bio'] = (bio[:150] + '...') if bio and len(bio) > 150 else bio
            doctors.append(doc)
    except mysql.connector.Error as db_err:
        log_method_error(f"Database error fetching doctors for dept {dept_id}: {db_err}")
    except Exception as e:
        log_method_exception(f"Unexpected error fetching doctors for dept {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctors


# --- Routes ---

@department_bp.route('/')
def list_departments():
    # ... (keep as is) ...
    """Renders the page listing all available departments."""
    all_departments = get_all_departments_from_db()
    if not all_departments and current_app:
        current_app.logger.warning("Department list page: get_all_departments_from_db returned empty. Check logs for that function.")

    return render_template(
        'Website/Departments/department_list.html',
        departments=all_departments
    )

@department_bp.route('/<int:dept_id>/')
def department_landing(dept_id):
    # ... (keep as is) ...
    """Renders the landing page for a specific department."""
    department = get_department_by_id(dept_id)
    if not department:
        if current_app:
            current_app.logger.warning(f"Department landing page requested for non-existent ID {dept_id}.")
        abort(404, description=f"Department with ID {dept_id} not found.")

    department_conditions = get_conditions_by_department(dept_id)
    if current_app:
        current_app.logger.debug(f"Rendering landing page for dept {dept_id} ('{department.get('name')}'). Conditions found: {len(department_conditions)}")

    template_path = 'Website/Departments/department_landing.html'
    return render_template(
        template_path,
        department=department,
        conditions=department_conditions
    )


@department_bp.route('/conditions/<int:condition_id>')
def view_condition(condition_id):
    # ... (keep as is - logic is correct, relies on updated get_condition_details_by_id) ...
    """Renders the details page for a specific condition."""
    condition = get_condition_details_by_id(condition_id) # Now returns snippets and flags

    if not condition:
        if current_app:
            current_app.logger.warning(f"Condition details requested for ID {condition_id}, but get_condition_details_by_id returned None. Check for DB errors or if condition exists and is active.")
        abort(404, description=f"Condition with ID {condition_id} not found or not available.")

    if current_app:
        current_app.logger.debug(f"Successfully fetched condition data for ID {condition_id}: {condition.get('name')}")

    related_doctors = []
    department_id_for_condition = condition.get('department_id')

    if department_id_for_condition:
        if current_app:
            current_app.logger.debug(f"Fetching related doctors for department ID: {department_id_for_condition} (Condition: {condition.get('name')})")
        related_doctors = get_doctors_by_department(department_id_for_condition)
        if current_app:
             current_app.logger.debug(f"Found {len(related_doctors)} related approved/active doctors for dept {department_id_for_condition}.")
    elif current_app:
        current_app.logger.warning(f"Condition {condition_id} ('{condition.get('name')}') has no associated department_id. Cannot fetch related doctors.")

    template_path = 'Website/Departments/disease_detail.html'
    if current_app:
        current_app.logger.debug(f"Rendering condition detail template: {template_path}")

    # Pass the condition object (now containing snippets and flags) to the template
    return render_template(
        template_path,
        condition=condition,
        doctors=related_doctors
    )

# --- End of Routes ---