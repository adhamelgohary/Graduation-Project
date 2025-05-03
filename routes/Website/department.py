# routes/Website/department.py

from flask import Blueprint, render_template, current_app, abort
import mysql.connector
# Ensure db.py is in the parent directory or adjust the import path
try:
    from db import get_db_connection
except ImportError:
    # If db.py is in the same directory as the run.py or app factory
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from db import get_db_connection


# Import the function to get all departments from home.py
# Adjust the relative path if your structure differs
try:
    # Assumes home.py is in the same directory (routes/Website/)
    from .home import get_all_departments_from_db
except ImportError:
    try:
        # Alternative if structure is different (e.g., routes is a package)
        from routes.Website.home import get_all_departments_from_db
    except ImportError as e:
        current_app.logger.error(f"Could not import get_all_departments_from_db. Check paths. Original error: {e}")
        # Provide a fallback or raise the error depending on requirements
        def get_all_departments_from_db():
            current_app.logger.warning("Using fallback get_all_departments_from_db due to import error.")
            return [] # Return empty list to avoid crashing


# Define the blueprint
department_bp = Blueprint(
    'department',
    __name__,
    # Adjust relative path if needed. Assumes templates are two levels up from routes/Website/
    template_folder='../../templates',
    url_prefix='/departments'
)

# --- Helper Functions ---

# get_department_by_id - Verified, no changes needed for doctor display issue
def get_department_by_id(dept_id):
    department = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM departments WHERE department_id = %s"
        cursor.execute(query, (dept_id,))
        department = cursor.fetchone()
        # ... (rest of the theme mapping logic remains the same) ...
        if department:
            db_filename = department.get('image_filename')
            department['image_url'] = f"images/{db_filename}" if db_filename else "images/placeholder.jpg"
            dept_name = department.get('name', '')
            if dept_name == 'Cardiology':
                department['specific_css'] = 'Website/cardio.css' # Example path
                department['hero_icon'] = 'fa-heart-pulse'
                # ... other cardiology specifics
            elif dept_name == 'Neurology':
                department['specific_css'] = 'Website/neuro.css' # Example path
                department['hero_icon'] = 'fa-brain'
                # ... other neurology specifics
            # ... other departments ...
            else: # Default fallback
                department['specific_css'] = 'Website/generic_department.css' # Example path
                department['hero_icon'] = 'fa-stethoscope'
                department['hero_highlight'] = department.get('name', 'Medical')
                department['hero_main'] = 'Care'
                department['hero_images'] = []
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching department ID {dept_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching department ID {dept_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

# get_conditions_by_department - Verified, no changes needed for doctor display issue
def get_conditions_by_department(dept_id):
    conditions = []
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT condition_id, condition_name, description, condition_image_filename
            FROM conditions
            WHERE department_id = %s AND is_active = TRUE ORDER BY condition_name ASC
        """
        cursor.execute(query, (dept_id,))
        results = cursor.fetchall()
        for condition_data in results:
            condition_img_filename = condition_data.get('condition_image_filename')
            condition_data['image_url'] = f"images/{condition_img_filename}" if condition_img_filename else "images/disease_placeholder.png"
            condition_data['name'] = condition_data.get('condition_name')
            desc = condition_data.get('description', '')
            condition_data['short_description'] = (desc[:100] + '...') if len(desc) > 100 else desc
            conditions.append(condition_data)
    except mysql.connector.Error as db_err:
        # ... (error logging remains the same) ...
         if db_err.errno == 1054: column_name = str(db_err).split("'")[1]; current_app.logger.error(f"DB Error fetching conditions: Column '{column_name}' missing. Err: {db_err}")
         elif db_err.errno == 1146: current_app.logger.error(f"DB Error fetching conditions: Table 'conditions' missing. Err: {db_err}")
         else: current_app.logger.error(f"Database error fetching conditions for dept {dept_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching conditions for dept {dept_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return conditions

# get_condition_details_by_id - Verified, no changes needed for doctor display issue
def get_condition_details_by_id(condition_id):
    condition = None
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                c.condition_id, c.condition_name AS name, c.description, c.overview,
                c.symptoms_text AS symptoms, c.causes_text AS causes,
                c.diagnosis_details AS diagnosis, c.treatment_details AS treatment,
                c.testing_details AS testing, c.educational_content, c.emergency_info,
                c.icd_code, c.urgency_level, c.condition_type, c.age_relevance,
                c.gender_relevance, c.specialist_type, c.self_treatable,
                c.typical_duration, c.condition_image_filename,
                dept.name AS department_name, dept.department_id
            FROM conditions c
            JOIN departments dept ON c.department_id = dept.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query, (condition_id,))
        condition = cursor.fetchone()
        if condition:
            img_file = condition.get('condition_image_filename')
            condition['image_url'] = f"images/{img_file}" if img_file else "images/disease_placeholder.png"
            dept_name = condition.get('department_name', '')
            # --- CSS Mapping ---
            if dept_name == 'Cardiology': condition['specific_css'] = 'Website/cardisease.css'
            elif dept_name == 'Neurology': condition['specific_css'] = 'Website/neurodisease.css'
            elif dept_name == 'Orthopedics': condition['specific_css'] = 'Website/orthodisease.css'
            elif dept_name == 'Dermatology': condition['specific_css'] = 'Website/dermadisease.css'
            elif dept_name == 'Oncology': condition['specific_css'] = 'Website/oncologydisease.css'
            else: condition['specific_css'] = 'Website/generic_disease.css'
            # --- Boolean Display ---
            if 'self_treatable' in condition and condition['self_treatable'] is not None:
                 condition['self_treatable_display'] = 'Yes' if condition['self_treatable'] else 'No'
            else: condition['self_treatable_display'] = 'N/A'
    except mysql.connector.Error as db_err:
        # ... (error logging remains the same) ...
         if db_err.errno == 1054: column_name = str(db_err).split("'")[1]; current_app.logger.error(f"DB Error fetching condition details: Column '{column_name}' missing. Err: {db_err}")
         elif db_err.errno == 1146: current_app.logger.error(f"DB Error fetching condition details: Table missing. Err: {db_err}")
         else: current_app.logger.error(f"Database error fetching condition ID {condition_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching condition ID {condition_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return condition

# get_doctors_by_department - Verified, no changes needed for doctor display issue
def get_doctors_by_department(dept_id):
    doctors = []
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name,
                d.specialization_id, s.name as specialization_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            WHERE u.user_type = 'doctor' AND d.department_id = %s
            ORDER BY u.last_name ASC, u.first_name ASC
        """ # Changed u.user_type = 'Doctor' to 'doctor' to match ENUM
        params = (dept_id,)
        cursor.execute(query, params)
        doctors_raw = cursor.fetchall()
        for doc in doctors_raw:
            doc['specialization'] = doc.get('specialization_name', 'Specialist')
            doctors.append(doc)
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching doctors for dept {dept_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching doctors for dept {dept_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctors


# --- Routes ---

# list_departments - Verified, no changes needed
@department_bp.route('/')
def list_departments():
    all_departments = get_all_departments_from_db()
    return render_template('Website/Departments/department_list.html', departments=all_departments)

# department_landing - Verified, no changes needed
@department_bp.route('/<int:dept_id>/')
def department_landing(dept_id):
    department = get_department_by_id(dept_id)
    if not department:
        current_app.logger.warning(f"Department with ID {dept_id} not found.")
        abort(404)
    department_conditions = get_conditions_by_department(dept_id)
    return render_template(
        'Website/Departments/department_landing.html',
        department=department,
        conditions=department_conditions
    )

# view_condition - Verified, includes logging
@department_bp.route('/conditions/<int:condition_id>')
def view_condition(condition_id):
    condition = get_condition_details_by_id(condition_id)
    if not condition:
        current_app.logger.warning(f"Condition with ID {condition_id} not found.")
        abort(404)

    # --- Logging Added ---
    current_app.logger.debug(f"Condition data fetched for ID {condition_id}: {condition}")

    related_doctors = []
    department_id_for_condition = condition.get('department_id')
    current_app.logger.debug(f"Department ID for condition {condition_id}: {department_id_for_condition}")

    if department_id_for_condition:
        related_doctors = get_doctors_by_department(department_id_for_condition)
        current_app.logger.debug(f"Doctors fetched for dept {department_id_for_condition}: {related_doctors}")
    else:
        current_app.logger.debug(f"No department ID found for condition {condition_id}, skipping doctor fetch.")
    # --- End Logging ---

    # --- CRITICAL: Verify this template path ---
    template_path = 'Website/Departments/disease_detail.html' # Is it really in Departments subfolder? Or just Website/?
    current_app.logger.debug(f"Rendering template: {template_path}")
    # --- End Critical ---

    return render_template(
        template_path,
        condition=condition,
        doctors=related_doctors # Passing the list (even if empty) as 'doctors'
    )

# --- End of Routes ---