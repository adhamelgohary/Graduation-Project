# your_project/routes/Website/disease_info.py

import mysql.connector
import re # Import re if not already imported
from flask import (
    Blueprint, render_template, request, abort, url_for, current_app
)
# No login required for public website view



# Adjust import path for db connection helper
import sys
import os
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from db import get_db_connection
except ImportError:
    try: from db import get_db_connection
    except ImportError: get_db_connection = None; print("ERROR: Cannot import db.py")


# --- Helper Function to Get Condition Details (MODIFIED Processing Logic) ---
def get_condition_details_for_website(condition_id):
    conn = None; cursor = None;
    details = {'condition': None}
    logger = current_app.logger if current_app else print

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True, buffered=True)

        query_cond = """
            SELECT c.*, dept.name AS department_name
            FROM conditions c
            LEFT JOIN departments dept ON c.department_id = dept.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query_cond, (condition_id,))
        details['condition'] = cursor.fetchone()
        if not details['condition']:
            logger.warning(f"Condition ID {condition_id} not found or not active for website.")
            return None

        condition_data = details['condition']

        # --- Process Text Fields into LISTS ---
        text_fields_to_split = {
            'regular_symptoms_list': 'regular_symptoms_text',
            'emergency_symptoms_list': 'emergency_symptoms_text',
            'causes_list': 'causes_text',
            'complications_list': 'complications_text',
            'risk_factors_list': 'risk_factors_text',
            'treatment_protocols_list': 'treatment_protocols_text',
            'diagnosis_list': 'diagnosis_details',       # ADDED for splitting
            'testing_list': 'testing_details',         # ADDED for splitting
        }
        for list_key, db_col in text_fields_to_split.items():
            original_text = condition_data.get(db_col)
            condition_data[list_key] = split_text_to_list(original_text)
            # We keep the original text field (e.g., causes_text) as it might be used for snippets

        # --- Generate Snippets for TEXT fields needing "Read More" ---
        SNIPPET_LENGTH_DETAIL = 250
        text_fields_for_snippets = {
            # 'overview': 'overview', # REMOVED - Overview will show full text
            'causes': 'causes_text',                     # ADDED for snippet generation
            'risk_factors': 'risk_factors_text',         # ADDED for snippet generation
            'complications': 'complications_text',       # ADDED for snippet generation
            'diagnosis': 'diagnosis_details',            # ADDED for snippet generation
            'testing': 'testing_details',              # ADDED for snippet generation
            'treatment_protocols': 'treatment_protocols_text', # ADDED for snippet generation
            'education': 'educational_content'           # REMAINS
        }
        for display_key, db_col in text_fields_for_snippets.items():
            full_text = condition_data.get(db_col)
            # Check if not isinstance(full_text, list) is less relevant here as db_col refers to original text cols
            snippet, has_more = create_snippet(full_text, SNIPPET_LENGTH_DETAIL)
            condition_data[f"{display_key}_snippet"] = snippet
            condition_data[f"{display_key}_has_more"] = has_more
            condition_data[f"{display_key}_full"] = full_text # Store original full text

        # --- Image & CSS (Unchanged) ---
        img_file = condition_data.get('condition_image_filename')
        try:
            condition_data['image_url'] = url_for('disease_management.serve_condition_image', image_filename_in_db=img_file) if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")
        except Exception:
             condition_data['image_url'] = url_for('static', filename=f'uploads/condition_images/{img_file}') if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")

        dept_name = condition_data.get('department_name')
        if dept_name == 'Cardiology': condition_data['specific_css'] = 'website/cardisease.css'
        elif dept_name == 'Neurology': condition_data['specific_css'] = 'website/neurodisease.css'
        elif dept_name == 'Orthopedics': condition_data['specific_css'] = 'website/orthodisease.css'
        else: condition_data['specific_css'] = 'website/generic_disease.css'


        # --- Boolean Display (Unchanged) ---
        condition_data['self_treatable_display'] = 'Yes' if condition_data.get('self_treatable') else 'No'

    except Exception as e:
        logger.error(f"Error processing condition details for website ID {condition_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return details


# --- NEW Helper Function to Split Text ---
def split_text_to_list(text_content):
    """Splits a string by commas or newlines into a list of cleaned strings."""
    if not text_content:
        return []
    # Split by newline first, then iterate and split by comma
    items = []
    lines = text_content.splitlines() # Handles \n, \r, \r\n
    for line in lines:
        # Split line by comma, strip whitespace from each part
        parts = [part.strip() for part in line.split(',')]
        # Add non-empty parts to the list
        items.extend(part for part in parts if part)
    return items

# Define create_snippet helper locally
def create_snippet(text, max_length=250, indicator="..."):
    """Creates a snippet from text, trying to end at a sentence or space."""
    if not text or len(text) <= max_length:
        return text, False # Return original text if it's short enough or None/empty

    # Try to find the last period within a reasonable boundary before max_length
    end_sentence = text.rfind('.', 0, max_length + 1)
    # Heuristic: Prefer sentence end if it's reasonably close to the max length
    if end_sentence > max_length * 0.6:
        return text[:end_sentence + 1], True

    # If no suitable sentence end, try the last space
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.6: # Heuristic: Prefer space end if reasonably close
        return text[:end_space] + indicator, True

    # If neither works well, just truncate hard
    return text[:max_length] + indicator, True


# --- Blueprint Definition ---
disease_info_bp = Blueprint(
    'disease_info',
    __name__,
    template_folder='../../templates',
    url_prefix='/conditions'
)

# --- Route for Viewing Condition Detail (MODIFIED context passing) ---
@disease_info_bp.route('/<int:condition_id>')
def view_condition(condition_id):
    condition_details_wrapper = get_condition_details_for_website(condition_id)

    if not condition_details_wrapper or not condition_details_wrapper.get('condition'):
        abort(404, description=f"Information for condition ID {condition_id} not found.")

    condition_data = condition_details_wrapper['condition']

    # Fetch related doctors (Logic remains the same)
    related_doctors = []
    department_id_for_condition = condition_data.get('department_id')
    if department_id_for_condition:
        conn_doc = None; cursor_doc = None
        try:
            conn_doc = get_db_connection(); cursor_doc = conn_doc.cursor(dictionary=True, buffered=True)
            cursor_doc.execute("""
                SELECT u.user_id, u.first_name, u.last_name, u.profile_picture, s.name AS specialization_name, d.biography
                FROM users u JOIN doctors d ON u.user_id = d.user_id LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                WHERE u.user_type = 'doctor' AND u.account_status = 'active' AND d.department_id = %s AND d.verification_status = 'approved'
                ORDER BY u.last_name ASC, u.first_name ASC LIMIT 6
            """, (department_id_for_condition,))
            doctors_raw = cursor_doc.fetchall()
            for doc in doctors_raw:
                pic = doc.get('profile_picture')
                try:
                    doc['profile_picture_url'] = url_for('profile.serve_profile_picture', filename=pic) if pic else url_for('static', filename='images/profile_pics/default_avatar.png')
                except:
                    doc['profile_picture_url'] = url_for('static', filename=f'uploads/profile_pics/{pic}') if pic else url_for('static', filename='images/profile_pics/default_avatar.png')
                bio = doc.get('biography')
                doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
                related_doctors.append(doc)
        except Exception as e:
            current_app.logger.error(f"Error fetching doctors for condition detail page (Dept {department_id_for_condition}): {e}")
        finally:
            if cursor_doc: cursor_doc.close()
            if conn_doc and conn_doc.is_connected(): conn_doc.close()

    # Pass the fully processed condition dictionary
    return render_template(
        'Website/Departments/disease_detail.html',
        condition=condition_data,
        doctors=related_doctors
    )