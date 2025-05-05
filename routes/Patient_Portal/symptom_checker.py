# routes/Patient_Portal/symptom_checker.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort, jsonify, session
)
from flask_login import login_required, current_user
from db import get_db_connection
from utils.auth_helpers import check_patient_authorization
from datetime import datetime
import json # For potentially storing list data in session or DB

# Define Blueprint
symptom_checker_bp = Blueprint(
    'symptom_checker',
    __name__,
    url_prefix='/patient/symptom-checker',
    template_folder='../../templates' # Adjust if needed
)


# --- Helper Functions ---

def get_body_locations():
    """Fetches main body locations."""
    # Similar to get_all_simple
    conn = None; cursor = None; locations = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT location_id, location_name FROM body_locations ORDER BY display_order, location_name")
        locations = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching body locations: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return locations

def get_sublocations(location_id):
    """Fetches sublocations for a given main location."""
    conn = None; cursor = None; sublocations = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT sublocation_id, sublocation_name FROM body_sublocations WHERE location_id = %s ORDER BY display_order, sublocation_name", (location_id,))
        sublocations = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching sublocations for location {location_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return sublocations

def get_symptoms_for_sublocation(sublocation_id):
    """Fetches symptoms commonly associated with a sublocation."""
    conn = None; cursor = None; symptoms = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query = """SELECT s.symptom_id, s.symptom_name, s.question_text
                   FROM symptoms s
                   JOIN symptom_body_locations sbl ON s.symptom_id = sbl.symptom_id
                   WHERE sbl.sublocation_id = %s
                   ORDER BY s.symptom_name""" # Or order by relevance_score if needed
        cursor.execute(query, (sublocation_id,))
        symptoms = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching symptoms for sublocation {sublocation_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return symptoms

def start_checker_session(user_id=None):
    """Creates a new symptom checker session record."""
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        ip_address = request.remote_addr
        device_info = request.headers.get('User-Agent')
        sql = """INSERT INTO symptom_checker_sessions
                 (user_id, start_time, ip_address, device_info)
                 VALUES (%s, NOW(), %s, %s)"""
        cursor.execute(sql, (user_id, ip_address, device_info))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error starting symptom checker session for user {user_id}: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def update_checker_session(session_id, data):
    """Updates a session record (e.g., selected symptoms, results)."""
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        # Build SET clause dynamically based on data provided
        set_clauses = []
        params = []
        for key, value in data.items():
            # Simple validation/allow list
            if key in ['completed', 'primary_complaint', 'selected_symptoms', 'risk_factors', 'results', 'recommendations', 'end_time']:
                set_clauses.append(f"{key} = %s")
                # Convert boolean/datetime/json if needed
                if key == 'completed': value = bool(value)
                elif key == 'end_time': value = datetime.now() # Set end time when updating results
                elif isinstance(value, (list, dict)): value = json.dumps(value) # Store lists/dicts as JSON strings
                params.append(value)

        if not set_clauses: return False # Nothing to update

        params.append(session_id) # Add session_id for WHERE clause
        sql = f"UPDATE symptom_checker_sessions SET {', '.join(set_clauses)} WHERE session_id = %s"
        cursor.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error updating symptom checker session {session_id}: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def calculate_potential_conditions(selected_symptom_ids):
     """
     Placeholder for the core logic to determine potential conditions.
     This would involve querying symptom_condition_map, conditions,
     applying weights, maybe considering risk factors.
     Returns a list of potential conditions and recommendations.
     """
     # TODO: Implement the actual matching algorithm
     current_app.logger.info(f"Calculating conditions for symptoms: {selected_symptom_ids}")
     # Example placeholder result
     results = [
         {'condition_id': 1, 'condition_name': 'Common Cold', 'match_score': 0.8, 'urgency': 'low', 'recommendation': 'Rest and fluids. See doctor if symptoms worsen.'},
         {'condition_id': 6, 'condition_name': 'GERD', 'match_score': 0.5, 'urgency': 'low', 'recommendation': 'Consider over-the-counter antacids. Consult doctor if persistent.'}
     ]
     recommendations = "Consult a healthcare professional for an accurate diagnosis. Based on your symptoms, consider mentioning the possibility of Common Cold or GERD."
     emergency_needed = False # Determine based on specific emergency symptoms

     return results, recommendations, emergency_needed


# --- Routes ---

@symptom_checker_bp.route('/', methods=['GET'])
# @login_required # Optional: Allow anonymous users?
def start_checker():
    """Displays the initial page for the symptom checker (e.g., select body area)."""
    # body_locations = get_body_locations() # Fetch locations if needed for first step
    user_id = current_user.id if current_user.is_authenticated else None
    # Start a session when the user visits the page
    session_id = start_checker_session(user_id)
    session['symptom_checker_session_id'] = session_id # Store session ID in Flask session

    # For a simple start, just render the entry page
    return render_template('Patient_Portal/SymptomChecker/start.html')

@symptom_checker_bp.route('/process', methods=['POST'])
# @login_required # Optional
def process_symptoms():
    """
    Handles submission of selected symptoms, calculates results,
    and redirects to the results page.
    (This is a simplified flow; a real checker might be multi-step AJAX)
    """
    session_id = session.get('symptom_checker_session_id')
    if not session_id:
        flash("Symptom checker session expired or invalid. Please start again.", "warning")
        return redirect(url_for('.start_checker'))

    # Get selected symptoms from the form (assuming checkboxes/multi-select)
    selected_symptom_ids = request.form.getlist('symptom_ids', type=int)
    primary_complaint = request.form.get('primary_complaint', '').strip() # Optional

    if not selected_symptom_ids:
        flash("Please select at least one symptom.", "warning")
        return redirect(url_for('.start_checker')) # Or back to the specific step

    # --- Calculate Potential Conditions ---
    potential_conditions, recommendations, emergency = calculate_potential_conditions(selected_symptom_ids)

    # --- Store Results and Update Session ---
    session_data = {
        'completed': True,
        'primary_complaint': primary_complaint or None,
        'selected_symptoms': selected_symptom_ids, # Store as list/JSON
        # 'risk_factors': ..., # TODO: Add risk factor handling if implemented
        'results': potential_conditions, # Store as list/JSON
        'recommendations': recommendations,
        'end_time': True # Signal to set end_time in update function
    }
    update_success = update_checker_session(session_id, session_data)

    if not update_success:
        flash("There was an error saving your assessment results.", "danger")
        # Decide where to redirect - maybe start over?
        return redirect(url_for('.start_checker'))

    # Clear session ID from Flask session after completion? Optional.
    # session.pop('symptom_checker_session_id', None)

    # Redirect to results page using the DB session ID
    return redirect(url_for('.view_results', session_id=session_id))


@symptom_checker_bp.route('/results/<int:session_id>', methods=['GET'])
# @login_required # Optional: Allow viewing results without login if session_id is known? Security risk?
def view_results(session_id):
    """Displays the results of a completed symptom checker session."""
    user_id = current_user.id if current_user.is_authenticated else None
    session_data = None
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Fetch completed session data
        # Add user_id check if results should only be viewable by the logged-in user who created it
        query = "SELECT * FROM symptom_checker_sessions WHERE session_id = %s AND completed = TRUE"
        params = [session_id]
        # if user_id: # Optional: Restrict access to own sessions if logged in
        #    query += " AND user_id = %s"
        #    params.append(user_id)

        cursor.execute(query, tuple(params))
        session_data = cursor.fetchone()

        if not session_data:
            flash("Assessment results not found or not completed.", "warning")
            return redirect(url_for('.start_checker'))

        # Parse JSON data if stored as strings
        for key in ['selected_symptoms', 'risk_factors', 'results']:
             if session_data.get(key) and isinstance(session_data[key], str):
                 try:
                     session_data[key] = json.loads(session_data[key])
                 except json.JSONDecodeError:
                     current_app.logger.warning(f"Could not parse JSON for field '{key}' in session {session_id}")
                     session_data[key] = [] # Or handle error appropriately

    except Exception as e:
        current_app.logger.error(f"Error fetching symptom checker results for session {session_id}: {e}")
        flash("Error loading assessment results.", "danger")
        return redirect(url_for('.start_checker'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # TODO: Fetch symptom names for the selected_symptom_ids to display them nicely
    symptom_details = {} # Placeholder

    return render_template('Patient_Portal/SymptomChecker/results.html',
                           results=session_data,
                           symptom_details=symptom_details)


# --- AJAX Routes (Example for dynamic symptom loading - Requires JS) ---

@symptom_checker_bp.route('/ajax/sublocations/<int:location_id>')
# @login_required # Optional
def ajax_get_sublocations(location_id):
    """AJAX endpoint to get sublocations for a body area."""
    sublocations = get_sublocations(location_id)
    return jsonify(sublocations=sublocations)

@symptom_checker_bp.route('/ajax/symptoms/<int:sublocation_id>')
# @login_required # Optional
def ajax_get_symptoms(sublocation_id):
    """AJAX endpoint to get symptoms for a sublocation."""
    symptoms = get_symptoms_for_sublocation(sublocation_id)
    return jsonify(symptoms=symptoms)