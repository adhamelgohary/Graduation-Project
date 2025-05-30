# your_project/routes/Website/disease_info.py
import mysql.connector
import re 
from flask import (
    Blueprint, render_template, request, abort, url_for, current_app
)
import sys
import os

_project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _project_root_path not in sys.path:
    sys.path.append(_project_root_path)

try:
    from db import get_db_connection
except ImportError:
    print("CRITICAL ERROR: Cannot import db.py from disease_info.py.", file=sys.stderr)
    def get_db_connection(): return None

try:
    from utils.directory_configs import get_relative_path_for_db
except ImportError:
    print("CRITICAL ERROR: Failed to import get_relative_path_for_db in disease_info.py.", file=sys.stderr)
    def get_relative_path_for_db(absolute_filepath): return None # Fallback

# --- Helper Functions needed by get_condition_details_for_website ---
def split_text_to_list(text_content):
    """Splits a string by commas or newlines into a list of cleaned strings."""
    if not text_content:
        return []
    items = []
    lines = text_content.splitlines() 
    for line in lines:
        parts = [part.strip() for part in line.split(',')]
        items.extend(part for part in parts if part)
    return items

def create_snippet(text, max_length=250, indicator="..."):
    """Creates a snippet from text, trying to end at a sentence or space."""
    if not text or len(text) <= max_length:
        return text, False 
    end_sentence = text.rfind('.', 0, max_length + 1)
    if end_sentence > max_length * 0.6:
        return text[:end_sentence + 1], True
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.6: 
        return text[:end_space] + indicator, True
    return text[:max_length] + indicator, True
# --- End Helper Functions ---


def get_condition_details_for_website(condition_id):
    conn = None; cursor = None; details = {'condition': None} # conn for condition details
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection() # conn for condition details
        if not conn: 
            getattr(logger, 'error', print)(f"DB Connection failed for condition_details_for_website ID {condition_id}")
            return None
            
        cursor = conn.cursor(dictionary=True, buffered=True) # cursor for condition details
        query_cond = """
            SELECT c.*, dept.name AS department_name, dept.department_id
            FROM conditions c
            LEFT JOIN departments dept ON c.department_id = dept.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query_cond, (condition_id,))
        condition_data = cursor.fetchone()
        if not condition_data:
            getattr(logger, 'warning', print)(f"Condition ID {condition_id} not found or not active for website.")
            return None
        
        details['condition'] = condition_data

        text_fields_to_split = {
            'regular_symptoms_list': 'regular_symptoms_text', 
            'emergency_symptoms_list': 'emergency_symptoms_text',
            'causes_list': 'causes_text', 
            'complications_list': 'complications_text',
            'risk_factors_list': 'risk_factors_text', 
            'treatment_protocols_list': 'treatment_protocols_text',
            'diagnosis_list': 'diagnosis_details', 
            'testing_list': 'testing_details',
        }
        for list_key, db_col in text_fields_to_split.items():
            condition_data[list_key] = split_text_to_list(condition_data.get(db_col))

        SNIPPET_LENGTH_DETAIL = 250
        text_fields_for_snippets = {
            'causes': 'causes_text', 
            'risk_factors': 'risk_factors_text', 
            'complications': 'complications_text',
            'diagnosis': 'diagnosis_details', 
            'testing': 'testing_details',
            'treatment_protocols': 'treatment_protocols_text', 
            'education': 'educational_content',
            'overview': 'overview'
        }
        for display_key, db_col in text_fields_for_snippets.items():
            full_text = condition_data.get(db_col)
            snippet, has_more = create_snippet(full_text, SNIPPET_LENGTH_DETAIL)
            condition_data[f"{display_key}_snippet"] = snippet
            condition_data[f"{display_key}_has_more"] = has_more
            condition_data[f"{display_key}_full"] = full_text 

        img_file_from_db = condition_data.get('condition_image_filename')
        if img_file_from_db and current_app and 'UPLOAD_FOLDER_CONDITIONS' in current_app.config and get_relative_path_for_db:
            actual_filename = os.path.basename(img_file_from_db) 
            full_image_path = os.path.join(current_app.config['UPLOAD_FOLDER_CONDITIONS'], actual_filename)
            relative_image_path = get_relative_path_for_db(full_image_path)
            if relative_image_path:
                condition_data['image_url'] = url_for('static', filename=relative_image_path)
            else:
                condition_data['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")
        else:
            condition_data['image_url'] = url_for('static', filename="images/conditions/disease_placeholder.png")

        dept_name = condition_data.get('department_name')
        if dept_name == 'Cardiology': condition_data['specific_css'] = 'Website/Conditions/cardiodisease.css'
        elif dept_name == 'Neurology': condition_data['specific_css'] = 'Website/Conditions/neurodisease.css'
        elif dept_name == 'Orthopedics': condition_data['specific_css'] = 'Website/Conditions/orthodisease.css'
        elif dept_name == 'Dermatology': condition_data['specific_css'] = 'Website/Conditions/dermadisease.css'
        else: condition_data['specific_css'] = 'Website/Conditions/generic_disease.css'
        condition_data['self_treatable_display'] = 'Yes' if condition_data.get('self_treatable') else 'No'

    except Exception as e:
        getattr(logger, 'error', print)(f"Error processing condition details for website ID {condition_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close() # cursor for condition details
        if conn and conn.is_connected(): conn.close() # conn for condition details
    return details


disease_info_bp = Blueprint(
    'disease_info',
    __name__,
    template_folder='../../templates',
    url_prefix='/conditions'
)

@disease_info_bp.route('/<int:condition_id>')
def view_condition(condition_id):
    condition_details_wrapper = get_condition_details_for_website(condition_id)
    if not condition_details_wrapper or not condition_details_wrapper.get('condition'):
        abort(404, description=f"Information for condition ID {condition_id} not found.")
    condition_data = condition_details_wrapper['condition']
    logger = current_app.logger if current_app else print
    getattr(logger, 'debug', print)(f"Viewing condition ID: {condition_id}, Name: {condition_data.get('name')}")

    related_doctors = []
    department_id_for_condition = condition_data.get('department_id')
    getattr(logger, 'debug', print)(f"Department ID for condition: {department_id_for_condition}")

    if department_id_for_condition:
        conn_doc = None # Connection for fetching doctors
        cursor_doc = None # Cursor for fetching doctors
        try:
            conn_doc = get_db_connection(); 
            if not conn_doc:
                getattr(logger, 'error', print)("DB Connection failed for fetching doctors in view_condition.")
            else:
                cursor_doc = conn_doc.cursor(dictionary=True, buffered=True)
                cursor_doc.execute("""
                    SELECT u.user_id, u.first_name, u.last_name, 
                           d.profile_photo_url,  
                           s.name AS specialization_name, d.biography
                    FROM users u 
                    JOIN doctors d ON u.user_id = d.user_id 
                    LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                    WHERE u.user_type = 'doctor' AND u.account_status = 'active' 
                          AND d.department_id = %s AND d.verification_status = 'approved'
                    ORDER BY u.last_name ASC, u.first_name ASC LIMIT 6
                """, (department_id_for_condition,))
                doctors_raw = cursor_doc.fetchall()
                getattr(logger, 'debug', print)(f"Found {len(doctors_raw)} raw doctor records for department {department_id_for_condition}")

                for doc_idx, doc in enumerate(doctors_raw):
                    doc_user_id = doc.get('user_id', 'N/A')
                    getattr(logger, 'debug', print)(f"Processing doctor #{doc_idx + 1} (User ID: {doc_user_id})")
                    
                    path_relative_to_static_from_db = doc.get('profile_photo_url') 
                    getattr(logger, 'debug', print)(f"  Doctor {doc_user_id} - path_relative_to_static_from_db: '{path_relative_to_static_from_db}'")

                    doc['profile_picture_url'] = url_for('static', filename='images/profile_pics/default_avatar.png') 

                    if path_relative_to_static_from_db:
                        if current_app and current_app.static_folder:
                            full_abs_path_to_check = os.path.join(current_app.static_folder, path_relative_to_static_from_db)
                            if not os.path.exists(full_abs_path_to_check):
                                getattr(logger, 'warning', print)(f"  Doctor {doc_user_id} - Profile image file NOT FOUND at '{full_abs_path_to_check}' (DB path: '{path_relative_to_static_from_db}'). Using default.")
                            else:
                                doc['profile_picture_url'] = url_for('static', filename=path_relative_to_static_from_db)
                                getattr(logger, 'info', print)(f"  Doctor {doc_user_id} - Successfully generated profile_picture_url: '{doc['profile_picture_url']}' using DB path.")
                        else:
                            doc['profile_picture_url'] = url_for('static', filename=path_relative_to_static_from_db)
                            getattr(logger, 'info', print)(f"  Doctor {doc_user_id} - Generated profile_picture_url (no existence check): '{doc['profile_picture_url']}' using DB path.")
                    else:
                        getattr(logger, 'warning', print)(f"  Doctor {doc_user_id} - No profile picture path in DB (is None or empty). Using default.")
                    
                    bio = doc.get('biography')
                    doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
                    related_doctors.append(doc)
        except Exception as e:
            getattr(logger, 'error', print)(f"Error fetching/processing doctors for condition detail page (Dept {department_id_for_condition}): {e}", exc_info=True)
        finally:
            if cursor_doc: cursor_doc.close() # Close cursor_doc
            if conn_doc and conn_doc.is_connected(): conn_doc.close() # **FIXED HERE: Close conn_doc**
    else:
        getattr(logger, 'info', print)("No department ID found for the condition, so no doctors will be fetched.")

    return render_template(
        'Website/Departments/disease_detail.html', 
        condition=condition_data,
        doctors=related_doctors
    )