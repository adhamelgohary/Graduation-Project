# routes/Website/department.py

from flask import Blueprint, render_template, current_app, abort, url_for
import mysql.connector
import sys
import os

_project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _project_root_path not in sys.path:
    sys.path.append(_project_root_path)

try:
    from db import get_db_connection
except ImportError:
    print("CRITICAL ERROR: Failed to import get_db_connection in department.py.", file=sys.stderr)
    def get_db_connection(): return None

try:
    from utils.directory_configs import get_relative_path_for_db
except ImportError:
    print("CRITICAL ERROR: Failed to import get_relative_path_for_db from utils.directory_configs in department.py.", file=sys.stderr)
    def get_relative_path_for_db(absolute_filepath): return None

try:
    from .home import get_all_departments_from_db
except ImportError as e:
    print(f"WARNING: Could not import get_all_departments_from_db from .home. Error: {e}", file=sys.stderr)
    def get_all_departments_from_db(): return []

department_bp = Blueprint(
    'department',
    __name__,
    template_folder='../../templates',
    url_prefix='/departments'
)

def create_snippet(text, max_length=250, indicator="..."):
    if not text or len(text) <= max_length:
        return text, False
    end_sentence = text.rfind('.', 0, max_length + 1)
    if end_sentence > max_length * 0.7:
        return text[:end_sentence + 1], True
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.7:
         return text[:end_space] + indicator, True
    return text[:max_length] + indicator, True

def get_department_by_id(dept_id):
    department = None; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection()
        if not conn: 
            getattr(logger, 'error', print)(f"Failed to get DB connection for dept ID {dept_id}"); return None
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM departments WHERE department_id = %s", (dept_id,))
        department = cursor.fetchone()
        if department:
            db_filename_from_db = department.get('image_filename')
            if db_filename_from_db and current_app and 'UPLOAD_FOLDER_DEPARTMENTS' in current_app.config and get_relative_path_for_db:
                actual_filename = os.path.basename(db_filename_from_db)
                full_image_path = os.path.join(current_app.config['UPLOAD_FOLDER_DEPARTMENTS'], actual_filename)
                relative_image_path = get_relative_path_for_db(full_image_path)
                if relative_image_path:
                    department['image_url'] = url_for('static', filename=relative_image_path)
                else:
                    department['image_url'] = url_for('static', filename="images/departments/placeholder.jpg")
                    getattr(logger, 'warning', print)(f"Could not generate relative path for department image: {actual_filename} (original: {db_filename_from_db}) for dept ID {dept_id}. Using placeholder.")
            else:
                department['image_url'] = url_for('static', filename="images/departments/placeholder.jpg")
            
            dept_name = department.get('name', '')
            if dept_name == 'Cardiology':
                department['specific_css'] = 'Website/Departments/cardio.css'
                department['hero_icon'] = 'fa-heart-pulse'; department['hero_highlight'] = 'Cardiology'; department['hero_main'] = 'Rhythm'
            elif dept_name == 'Neurology':
                department['specific_css'] = 'Website/Departments/neuro.css'
                department['hero_icon'] = 'fa-brain'; department['hero_highlight'] = 'Neurology'; department['hero_main'] = 'Insight'
            elif dept_name == 'Orthopedics':
                department['specific_css'] = 'Website/Departments/ortho.css'
                department['hero_icon'] = 'fa-bone'; department['hero_highlight'] = 'Orthopedics'; department['hero_main'] = 'Mobility'
            elif dept_name == 'Dermatology':
                department['specific_css'] = 'Website/Departments/derma.css'
                department['hero_icon'] = 'fa-skin'; department['hero_highlight'] = 'Dermatology'; department['hero_main'] = 'Radiance'
            else: 
                department['specific_css'] = 'Website/generic_department.css'
                department['hero_icon'] = 'fa-stethoscope'; department['hero_highlight'] = department.get('name', 'Medical'); department['hero_main'] = 'Care'
                department['hero_images'] = [] 
    except Exception as e: getattr(logger, 'exception', print)(f"Error fetching dept ID {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

def get_conditions_by_department(dept_id):
    conditions = []; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    SNIPPET_LENGTH_LIST = 100
    try:
        conn = get_db_connection()
        if not conn: 
            getattr(logger, 'error', print)(f"DB conn failed for conditions in dept {dept_id}"); return []
        cursor = conn.cursor(dictionary=True)
        # MODIFIED QUERY to include specialization_name
        query = """
            SELECT 
                c.condition_id, c.condition_name, c.description, c.condition_image_filename,
                s.name AS specialization_name
            FROM conditions c
            LEFT JOIN specializations s ON c.specialization_id = s.specialization_id
            WHERE c.department_id = %s AND c.is_active = TRUE 
            ORDER BY c.condition_name ASC
        """
        cursor.execute(query, (dept_id,))
        for cond_data in cursor.fetchall():
            img_file_from_db = cond_data.get('condition_image_filename')
            if img_file_from_db and current_app and 'UPLOAD_FOLDER_CONDITIONS' in current_app.config and get_relative_path_for_db:
                actual_filename = os.path.basename(img_file_from_db)
                full_image_path = os.path.join(current_app.config['UPLOAD_FOLDER_CONDITIONS'], actual_filename)
                relative_image_path = get_relative_path_for_db(full_image_path)
                if relative_image_path:
                    cond_data['image_url'] = url_for('static', filename=relative_image_path)
                else:
                    cond_data['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")
                    getattr(logger, 'warning', print)(f"Could not generate relative path for condition image: {actual_filename} (original: {img_file_from_db}) in dept {dept_id}. Using placeholder.")
            else:
                cond_data['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")
            
            cond_data['name'] = cond_data.get('condition_name')
            desc = cond_data.get('description', '')
            cond_data['short_description'], _ = create_snippet(desc, SNIPPET_LENGTH_LIST)
            # specialization_name is already in cond_data from the query
            conditions.append(cond_data)
    except Exception as e: getattr(logger, 'exception', print)(f"Error fetching conditions for dept {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return conditions

def get_condition_details_by_id(condition_id): 
    condition = None; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    SNIPPET_LENGTH_DETAIL = 250
    try:
        conn = get_db_connection()
        if not conn: 
            getattr(logger, 'error', print)(f"DB conn failed for condition ID {condition_id}"); return None
        cursor = conn.cursor(dictionary=True)
        # MODIFIED QUERY to include specialization_name
        query = """
            SELECT 
                c.*, c.condition_name AS name, 
                dept.name AS department_name, dept.department_id,
                s.name AS specialization_name
            FROM conditions c
            LEFT JOIN departments dept ON c.department_id = dept.department_id
            LEFT JOIN specializations s ON c.specialization_id = s.specialization_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query, (condition_id,))
        condition = cursor.fetchone()
        if condition:
            fields_to_snippet = ['description', 'overview', 'symptoms_text', 'causes_text', 'diagnosis_details', 'testing_details', 'treatment_options', 'prevention_tips', 'prognosis', 'management_lifestyle', 'when_to_see_doctor', 'emergency_info', 'educational_content']
            for field in fields_to_snippet:
                full_text = condition.get(field)
                snippet, has_more = create_snippet(full_text, SNIPPET_LENGTH_DETAIL)
                condition[f"{field}_snippet"] = snippet
                condition[f"{field}_has_more"] = has_more
            
            img_file_from_db = condition.get('condition_image_filename')
            if img_file_from_db and current_app and 'UPLOAD_FOLDER_CONDITIONS' in current_app.config and get_relative_path_for_db:
                actual_filename = os.path.basename(img_file_from_db)
                full_image_path = os.path.join(current_app.config['UPLOAD_FOLDER_CONDITIONS'], actual_filename)
                relative_image_path = get_relative_path_for_db(full_image_path)
                if relative_image_path:
                    condition['image_url'] = url_for('static', filename=relative_image_path)
                else:
                    condition['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")
            else:
                condition['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")

            dept_name = condition.get('department_name')
            if dept_name == 'Cardiology': condition['specific_css'] = 'Website/Conditions/cardiodisease.css'
            elif dept_name == 'Neurology': condition['specific_css'] = 'Website/Conditions/neurodisease.css'
            elif dept_name == 'Orthopedics': condition['specific_css'] = 'Website/Conditions/orthodisease.css'
            elif dept_name == 'Dermatology': condition['specific_css'] = 'Website/Conditions/dermadisease.css'
            else: condition['specific_css'] = 'Website/Conditions/generic_disease.css'
            condition['self_treatable_display'] = 'Yes' if condition.get('self_treatable') else ('No' if condition.get('self_treatable') is not None else 'N/A')
            # specialization_name is already in condition from the query
    except Exception as e: getattr(logger, 'exception', print)(f"Error fetching condition ID {condition_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return condition

@department_bp.route('/')
def list_departments():
    all_departments_raw = get_all_departments_from_db()
    departments_to_display = []
    excluded_department_name = "Nutrition Services"
    if all_departments_raw:
        for dept in all_departments_raw:
            if dept.get('name', '').strip().lower() != excluded_department_name.lower():
                departments_to_display.append(dept)
    if not departments_to_display and current_app:
        current_app.logger.info(f"No departments to display after excluding '{excluded_department_name}'.")
    return render_template('Website/Departments/department_list.html', departments=departments_to_display)

@department_bp.route('/<int:dept_id>/')
def department_landing(dept_id):
    department = get_department_by_id(dept_id)
    if not department:
        abort(404, description=f"Department with ID {dept_id} not found.")
    excluded_department_name = "Nutrition Services"
    if department.get('name', '').strip().lower() == excluded_department_name.lower():
        abort(404, description="This department page is not available.")
    department_conditions = get_conditions_by_department(dept_id) # This now includes specialization_name
    return render_template('Website/Departments/department_landing.html', department=department, conditions=department_conditions)

@department_bp.route('/condition/<int:condition_id>/')
def condition_detail_page(condition_id): 
    # This route is less used now that disease_info.view_condition is primary,
    # but get_condition_details_by_id() is updated for consistency.
    condition = get_condition_details_by_id(condition_id)
    if not condition:
        abort(404, description=f"Condition with ID {condition_id} not found.")
    
    # Note: Doctor fetching logic here would also need adjustment if this page were primary
    # For now, it will show doctors from the condition's department.
    # The main `disease_info.view_condition` route handles specialization-specific doctors.
    related_doctors = []
    department_id_for_condition = condition.get('department_id')
    if department_id_for_condition:
        conn_doc, cursor_doc = None, None
        try:
            conn_doc = get_db_connection()
            if conn_doc:
                cursor_doc = conn_doc.cursor(dictionary=True, buffered=True)
                # Basic doctor fetching by department (as it was)
                # For specialization-specific doctors, use the `disease_info.py` route.
                cursor_doc.execute("""
                    SELECT u.user_id, u.first_name, u.last_name, d.profile_photo_url, s.name AS specialization_name, d.biography
                    FROM users u JOIN doctors d ON u.user_id = d.user_id LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                    WHERE u.user_type = 'doctor' AND u.account_status = 'active' AND d.department_id = %s AND d.verification_status = 'approved'
                    ORDER BY u.last_name ASC, u.first_name ASC LIMIT 6
                """, (department_id_for_condition,))
                doctors_raw = cursor_doc.fetchall()
                for doc in doctors_raw:
                    path_relative_to_static_from_db = doc.get('profile_photo_url')
                    doc['profile_picture_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')
                    if path_relative_to_static_from_db:
                         if current_app and current_app.static_folder:
                            full_abs_path_to_check = os.path.join(current_app.static_folder, path_relative_to_static_from_db)
                            if os.path.exists(full_abs_path_to_check):
                                doc['profile_picture_url'] = url_for('static', filename=path_relative_to_static_from_db)
                    bio = doc.get('biography')
                    doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
                    related_doctors.append(doc)
        except Exception as e:
            logger = current_app.logger if current_app else print
            getattr(logger, 'error', print)(f"Error fetching doctors for old condition detail page (Dept {department_id_for_condition}): {e}", exc_info=True)
        finally:
            if cursor_doc: cursor_doc.close()
            if conn_doc and conn_doc.is_connected(): conn_doc.close()

    return render_template('Website/Departments/disease_detail.html', condition=condition, doctors=related_doctors, page_title=condition.get('name', 'Condition Details'))