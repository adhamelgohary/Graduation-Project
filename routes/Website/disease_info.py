# your_project/routes/Website/disease_info.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, abort, url_for, current_app
)
# No login required for public website view
# from flask_login import login_required, current_user

# Adjust import path for db connection helper
import sys
import os
try:
    # Assumes this file is in routes/Website, and db.py is at project root
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from db import get_db_connection
except ImportError:
    # Fallback if run differently or structure differs
    try: from db import get_db_connection
    except ImportError: get_db_connection = None; print("ERROR: Cannot import db.py")

# Import snippet helper if moved to a shared utils
# from ..utils import create_snippet # Example if utils is one level up
# OR define it here if not shared
def create_snippet(text, max_length=250, indicator="..."):
    if not text or len(text) <= max_length: return text, False
    end_sentence = text.rfind('.', 0, max_length + 1)
    if end_sentence > max_length * 0.7: return text[:end_sentence + 1], True
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.7: return text[:end_space] + indicator, True
    return text[:max_length] + indicator, True

# --- Blueprint Definition ---
disease_info_bp = Blueprint(
    'disease_info', # New blueprint name
    __name__,
    template_folder='../../templates', # Point to main templates dir
    url_prefix='/conditions' # Base URL for conditions
)

# --- Helper Function to Get Full Condition Details for Website View ---
def get_condition_details_for_website(condition_id):
    """Fetches condition details including associations with names for public display."""
    conn = None; cursor = None;
    # Use details structure similar to disease_management
    details = {
        'condition': None,
        'symptoms': [], # Will store dicts like {'symptom_name': 'Headache'}
        'risk_factors': [], # Will store dicts like {'factor_name': 'Smoking', 'factor_type': 'lifestyle'}
        'protocols': [] # Will store dicts like {'protocol_name': 'Std Mgmt', 'guideline_url': '...'}
    }
    logger = current_app.logger if current_app else print # Use logger

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True, buffered=True)

        # 1. Get Condition Details (including needed fields for display/CSS)
        query_cond = """
            SELECT
                c.condition_id, c.condition_name AS name, c.description, c.overview,
                c.symptoms_text, c.causes_text, c.diagnosis_details AS diagnosis,
                c.testing_details AS testing, c.educational_content,
                c.icd_code, c.urgency_level, c.condition_type, c.age_relevance,
                c.gender_relevance, c.specialist_type, c.self_treatable,
                c.typical_duration, c.condition_image_filename,
                dept.name AS department_name, dept.department_id
            FROM conditions c
            LEFT JOIN departments dept ON c.department_id = dept.department_id
            WHERE c.condition_id = %s AND c.is_active = TRUE
        """
        cursor.execute(query_cond, (condition_id,))
        details['condition'] = cursor.fetchone()
        if not details['condition']:
            logger.warning(f"Condition ID {condition_id} not found or not active.")
            return None

        condition_data = details['condition'] # Shortcut

        # --- Snippet Generation ---
        SNIPPET_LENGTH_DETAIL = 250
        # Map internal field names to potentially different keys if needed, or use directly
        text_fields = {
            'symptoms': 'symptoms_text', 'causes': 'causes_text', 'diagnosis': 'diagnosis',
            'testing': 'testing', 'educational_content': 'educational_content'
            # Add 'emergency_info' if that's a column in your 'conditions' table
        }
        for display_key, db_col in text_fields.items():
            full_text = condition_data.get(db_col)
            snippet, has_more = create_snippet(full_text, SNIPPET_LENGTH_DETAIL)
            condition_data[f"{display_key}_snippet"] = snippet
            condition_data[f"{display_key}_has_more"] = has_more

        # --- Image & CSS ---
        img_file = condition_data.get('condition_image_filename')
        # Using the dedicated route is slightly better practice than direct static link
        condition_data['image_url'] = url_for('disease_management.serve_condition_image', image_filename_in_db=img_file) if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")

        dept_name = condition_data.get('department_name')
        # Simplified CSS logic - assumes files exist in static/website/
        if dept_name == 'Cardiology': condition_data['specific_css'] = 'website/cardisease.css'
        elif dept_name == 'Neurology': condition_data['specific_css'] = 'website/neurodisease.css'
        # Add other specific mappings
        else: condition_data['specific_css'] = 'website/generic_disease.css'

        # --- Boolean Display ---
        condition_data['self_treatable_display'] = 'Yes' if condition_data.get('self_treatable') else 'No'

        # --- Fetch ASSOCIATED ITEMS with NAMES ---

        # 2. Associated Symptoms (Names Only)
        cursor.execute("""
            SELECT s.symptom_name
            FROM symptoms s JOIN symptom_condition_map scm ON s.symptom_id = scm.symptom_id
            WHERE scm.condition_id = %s ORDER BY s.symptom_name
        """, (condition_id,))
        details['symptoms'] = cursor.fetchall() # List of dicts like [{'symptom_name': 'Headache'}, ...]

        # 3. Associated Risk Factors (Names Only)
        cursor.execute("""
            SELECT rf.factor_name, rf.factor_type
            FROM risk_factors rf JOIN condition_risk_factors crf ON rf.factor_id = crf.factor_id
            WHERE crf.condition_id = %s ORDER BY rf.factor_name
        """, (condition_id,))
        details['risk_factors'] = cursor.fetchall() # [{'factor_name': 'Smoking', 'factor_type': 'lifestyle'}, ...]

        # 4. Associated Protocols (Names and URL)
        cursor.execute("""
            SELECT tp.protocol_name, tp.guideline_url
            FROM treatment_protocols tp JOIN condition_protocols cp ON tp.protocol_id = cp.protocol_id
            WHERE cp.condition_id = %s AND tp.is_active = TRUE ORDER BY cp.relevance, tp.protocol_name
        """, (condition_id,))
        details['protocols'] = cursor.fetchall() # [{'protocol_name': 'HTN Mgmt', 'guideline_url': '...'}, ...]

    except mysql.connector.Error as db_err:
        logger.error(f"DB Error getting condition details for website ID {condition_id}: {db_err}", exc_info=True)
        return None # Return None on error
    except ConnectionError as ce:
         logger.error(f"DB Connection Error getting condition details for website ID {condition_id}: {ce}", exc_info=True)
         return None
    except Exception as e:
        logger.error(f"Unexpected Error getting condition details for website ID {condition_id}: {e}", exc_info=True)
        return None # Return None on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return details # Return the full dictionary including associations


# --- Route for Viewing Condition Detail ---
@disease_info_bp.route('/<int:condition_id>') # Changed route prefix via Blueprint
def view_condition(condition_id):
    """Renders the details page for a specific condition (Public Website View)."""
    # Fetch data using the dedicated helper
    condition_details = get_condition_details_for_website(condition_id)

    if not condition_details or not condition_details.get('condition'):
        current_app.logger.warning(f"Condition details requested for ID {condition_id}, but not found or error occurred.")
        abort(404, description=f"Information for condition ID {condition_id} not found.")

    # Fetch related doctors (optional, logic can stay here or move to helper)
    related_doctors = []
    department_id_for_condition = condition_details['condition'].get('department_id')
    if department_id_for_condition:
        # This logic could also be moved to a shared helper if used elsewhere
        conn_doc = None; cursor_doc = None
        try:
            conn_doc = get_db_connection(); cursor_doc = conn_doc.cursor(dictionary=True, buffered=True)
            cursor_doc.execute("""
                SELECT u.user_id, u.first_name, u.last_name, u.profile_picture, s.name AS specialization_name, d.biography
                FROM users u JOIN doctors d ON u.user_id = d.user_id LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                WHERE u.user_type = 'doctor' AND u.account_status = 'active' AND d.department_id = %s AND d.verification_status = 'approved'
                ORDER BY u.last_name ASC, u.first_name ASC LIMIT 6
            """, (department_id_for_condition,)) # Limit number of doctors shown
            doctors_raw = cursor_doc.fetchall()
            for doc in doctors_raw:
                pic = doc.get('profile_picture')
                doc['profile_picture_url'] = url_for('static', filename=f'uploads/profile_pics/{pic}') if pic else url_for('static', filename='images/profile_pics/default_avatar.png')
                bio = doc.get('biography')
                doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
                related_doctors.append(doc)
        except Exception as e:
            current_app.logger.error(f"Error fetching doctors for condition detail page (Dept {department_id_for_condition}): {e}")
        finally:
            if cursor_doc: cursor_doc.close()
            if conn_doc and conn_doc.is_connected(): conn_doc.close()

    # Render the detail template, passing the fetched data structure
    return render_template(
        'Website/Departments/disease_detail.html', # Use the existing template path
        condition=condition_details['condition'], # Pass the main condition data
        symptoms=condition_details['symptoms'], # Pass associated symptoms list
        risk_factors=condition_details['risk_factors'], # Pass associated risk factors list
        protocols=condition_details['protocols'], # Pass associated protocols list
        doctors=related_doctors # Pass related doctors
    )