# routes/Patient_Portal/medical_info.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from utils.auth_helpers import check_patient_authorization
from datetime import datetime
import math

# Define Blueprint
patient_medical_info_bp = Blueprint(
    'patient_medical_info',
    __name__,
    url_prefix='/patient/medical-info',
    template_folder='../../templates' # Adjust if needed
)

ITEMS_PER_PAGE = 10 # Example for pagination

# --- Helper to get ENUMs (copy or import from another file) ---
ENUM_CACHE = {}
def get_enum_values(table_name, column_name):
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE: return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0];
            if isinstance(enum_str, bytes): enum_str = enum_str.decode('utf-8')
            if enum_str.startswith('enum(') and enum_str.endswith(')'):
                 values = [v.strip("'") for v in enum_str[5:-1].split(',')]
            ENUM_CACHE[cache_key] = values; return values
    except Exception as e: current_app.logger.error(f"Error fetching ENUM {table_name}.{column_name}: {e}"); return []
    finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()
    return values

# --- Routes ---

@patient_medical_info_bp.route('/')
@login_required
def view_medical_dashboard():
    """Display overview/dashboard of patient's medical info."""
    if not check_patient_authorization(current_user): abort(403)
    # TODO: Fetch summary data (e.g., recent logs, allergy count)
    summary_data = {}
    return render_template('Patient_Portal/MedicalInfo/dashboard.html', summary=summary_data)

# --- Allergies ---
@patient_medical_info_bp.route('/allergies', methods=['GET', 'POST'])
@login_required
def manage_allergies():
    """View and add patient allergies."""
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;

    if request.method == 'POST':
        allergy_id = request.form.get('allergy_id', type=int)
        severity = request.form.get('severity')
        reaction = request.form.get('reaction_description', '').strip() or None
        diagnosed_date_str = request.form.get('diagnosed_date')
        notes = request.form.get('notes', '').strip() or None
        errors = []

        # Validation
        if not allergy_id: errors.append("Please select an allergy.")
        # Validate severity against ENUM
        allowed_severities = get_enum_values('patient_allergies', 'severity')
        if severity not in allowed_severities: errors.append("Invalid severity level selected.")
        diagnosed_date = None
        if diagnosed_date_str:
             try: diagnosed_date = datetime.strptime(diagnosed_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid diagnosed date format.")

        if errors:
            for err in errors: flash(err, "danger")
        else:
            # Database Insert/Update (consider ON DUPLICATE KEY UPDATE)
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                # Using REPLACE INTO for simplicity, ON DUPLICATE KEY UPDATE is generally better
                sql = """REPLACE INTO patient_allergies
                         (patient_id, allergy_id, severity, reaction_description, diagnosed_date, notes, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())"""
                cursor.execute(sql, (patient_id, allergy_id, severity, reaction, diagnosed_date, notes))
                conn.commit()
                flash("Allergy information saved.", "success")
                return redirect(url_for('.manage_allergies')) # Refresh list
            except mysql.connector.Error as err:
                if conn: conn.rollback()
                current_app.logger.error(f"DB error saving allergy for patient {patient_id}: {err}")
                flash("Database error saving allergy.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error saving allergy for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST error
    current_allergies = []
    all_allergies_list = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Get current patient allergies
        query_current = """SELECT pa.*, a.allergy_name, a.allergy_type
                           FROM patient_allergies pa
                           JOIN allergies a ON pa.allergy_id = a.allergy_id
                           WHERE pa.patient_id = %s ORDER BY a.allergy_name"""
        cursor.execute(query_current, (patient_id,))
        current_allergies = cursor.fetchall()
        # Get master list of all allergies for dropdown
        cursor.execute("SELECT allergy_id, allergy_name, allergy_type FROM allergies ORDER BY allergy_name")
        all_allergies_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching allergies for patient {patient_id}: {e}")
        flash("Error loading allergy information.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    allergy_severities = get_enum_values('patient_allergies', 'severity')
    # Pass submitted data back on POST error
    form_data = request.form if request.method == 'POST' else None

    return render_template('Patient_Portal/MedicalInfo/manage_allergies.html',
                           current_allergies=current_allergies,
                           all_allergies_list=all_allergies_list,
                           allergy_severities=allergy_severities,
                           form_data=form_data)

@patient_medical_info_bp.route('/allergies/<int:allergy_id>/delete', methods=['POST'])
@login_required
def delete_allergy(allergy_id):
    """Deletes a patient's allergy record."""
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn=None; cursor=None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        sql = "DELETE FROM patient_allergies WHERE patient_id = %s AND allergy_id = %s"
        cursor.execute(sql, (patient_id, allergy_id))
        conn.commit()
        if cursor.rowcount > 0: flash("Allergy removed successfully.", "success")
        else: flash("Allergy not found or already removed.", "warning")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting allergy {allergy_id} for patient {patient_id}: {e}")
        flash("Error removing allergy.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.manage_allergies'))


# --- Symptoms ---
@patient_medical_info_bp.route('/symptoms', methods=['GET', 'POST'])
@login_required
def manage_symptoms():
    """View symptom history and log new symptoms."""
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;

    if request.method == 'POST':
        symptom_id = request.form.get('symptom_id', type=int)
        reported_date_str = request.form.get('reported_date') # Use this as primary date
        onset_date_str = request.form.get('onset_date')
        severity = request.form.get('severity', '').strip() or None
        duration = request.form.get('duration', '').strip() or None
        frequency = request.form.get('frequency') or None
        notes = request.form.get('notes', '').strip() or None
        errors = []

        # Validation
        if not symptom_id: errors.append("Please select a symptom.")
        reported_date = None
        if reported_date_str:
             try: reported_date = datetime.strptime(reported_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Reported Date format.")
        else: errors.append("Reported Date is required.")
        onset_date = None
        if onset_date_str:
             try: onset_date = datetime.strptime(onset_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Onset Date format.")
        # Validate frequency against ENUM
        allowed_freq = get_enum_values('patient_symptoms', 'frequency')
        if frequency and frequency not in allowed_freq: errors.append("Invalid frequency selected.")

        if errors:
             for err in errors: flash(err, "danger")
        else:
            # DB Insert
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                sql = """INSERT INTO patient_symptoms
                         (patient_id, symptom_id, reported_date, onset_date, severity, duration, frequency, notes, reported_by, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())"""
                params = (patient_id, symptom_id, reported_date, onset_date, severity, duration, frequency, notes, patient_id) # Reported by patient
                cursor.execute(sql, params)
                conn.commit()
                flash("Symptom logged successfully.", "success")
                return redirect(url_for('.manage_symptoms'))
            except mysql.connector.Error as err:
                 if conn: conn.rollback(); current_app.logger.error(f"DB error logging symptom for patient {patient_id}: {err}")
                 flash("Database error logging symptom.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback();
                 current_app.logger.error(f"Error logging symptom for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close();
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST Error
    symptom_history = []
    all_symptoms_list = []
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Get paginated symptom history
        query_history = """SELECT SQL_CALC_FOUND_ROWS ps.*, s.symptom_name
                           FROM patient_symptoms ps
                           JOIN symptoms s ON ps.symptom_id = s.symptom_id
                           WHERE ps.patient_id = %s
                           ORDER BY ps.reported_date DESC, ps.created_at DESC
                           LIMIT %s OFFSET %s"""
        cursor.execute(query_history, (patient_id, ITEMS_PER_PAGE, offset))
        symptom_history = cursor.fetchall()
        # Get total count for pagination
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        total_items = total_row['total'] if total_row else 0
        # Get master symptom list
        cursor.execute("SELECT symptom_id, symptom_name FROM symptoms ORDER BY symptom_name")
        all_symptoms_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching symptoms for patient {patient_id}: {e}")
        flash("Error loading symptom information.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    symptom_frequencies = get_enum_values('patient_symptoms', 'frequency')
    form_data = request.form if request.method == 'POST' else None

    return render_template('Patient_Portal/MedicalInfo/manage_symptoms.html',
                           symptom_history=symptom_history,
                           all_symptoms_list=all_symptoms_list,
                           symptom_frequencies=symptom_frequencies,
                           current_page=page, total_pages=total_pages,
                           form_data=form_data)


# --- Vitals / Physical Characteristics ---
@patient_medical_info_bp.route('/vitals', methods=['GET', 'POST'])
@login_required
def manage_vitals():
    """View and log vitals like height and weight (using user_nutrition_logs)."""
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;

    if request.method == 'POST':
        log_date_str = request.form.get('log_date')
        weight_kg = request.form.get('weight_kg')
        # Height is less frequently logged, might be better in profile?
        # For this example, we'll allow logging it here too.
        height_cm = request.form.get('height_cm') # Get from profile if not logged here?
        notes = request.form.get('notes', '').strip() or None # Allow notes on log
        errors = []

        log_date = None
        if log_date_str:
             try: log_date = datetime.strptime(log_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Log Date format.")
        else: errors.append("Log Date is required.")

        weight_val = None
        if weight_kg:
            try: weight_val = float(weight_kg);
            except ValueError: errors.append("Invalid Weight format.")
        # Add similar validation for height if logged here

        # At least weight or height should be provided for a log entry
        if weight_val is None: # Add OR height_val is None if tracking height here too
            errors.append("At least Weight must be provided for a log entry.")

        if errors:
            for err in errors: flash(err, "danger")
        else:
            # DB Insert/Update (handle potential unique constraint on user_id, log_date)
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                # Use INSERT ... ON DUPLICATE KEY UPDATE to handle existing logs for the same day
                sql = """INSERT INTO user_nutrition_logs (user_id, log_date, weight_kg, notes, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, NOW(), NOW())
                         ON DUPLICATE KEY UPDATE
                         weight_kg = VALUES(weight_kg), notes = VALUES(notes), updated_at = NOW()"""
                # Add height_cm = VALUES(height_cm) if logging height here
                params = (patient_id, log_date, weight_val, notes)
                cursor.execute(sql, params)
                conn.commit()
                flash("Vitals logged successfully.", "success")
                return redirect(url_for('.manage_vitals'))
            except mysql.connector.Error as err:
                 if conn: conn.rollback(); current_app.logger.error(f"DB error logging vitals for patient {patient_id}: {err}")
                 flash("Database error logging vitals.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback();
                 current_app.logger.error(f"Error logging vitals for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close();
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST Error
    vitals_history = []
    current_vitals = {} # Store latest height/weight maybe from patients table
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Get current height/weight from patients table for display
        cursor.execute("SELECT height_cm, weight_kg FROM patients WHERE user_id = %s", (patient_id,))
        current_vitals = cursor.fetchone() or {}

        # Get paginated log history
        query_history = """SELECT SQL_CALC_FOUND_ROWS log_id, log_date, weight_kg, notes
                           FROM user_nutrition_logs
                           WHERE user_id = %s AND weight_kg IS NOT NULL {# Example: only show logs with weight #}
                           ORDER BY log_date DESC
                           LIMIT %s OFFSET %s"""
        cursor.execute(query_history, (patient_id, ITEMS_PER_PAGE, offset))
        vitals_history = cursor.fetchall()
        # Get total count
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        total_items = total_row['total'] if total_row else 0
    except Exception as e:
        current_app.logger.error(f"Error fetching vitals for patient {patient_id}: {e}")
        flash("Error loading vitals history.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    form_data = request.form if request.method == 'POST' else None

    return render_template('Patient_Portal/MedicalInfo/manage_vitals.html',
                           vitals_history=vitals_history,
                           current_vitals=current_vitals,
                           current_page=page, total_pages=total_pages,
                           form_data=form_data)

# --- Medical History ---
# Needs a dedicated table like 'patient_medical_history' (condition_name, start_date, end_date, notes, patient_id)
@patient_medical_info_bp.route('/history', methods=['GET'])
@login_required
def view_history():
    """View personal medical history."""
    if not check_patient_authorization(current_user): abort(403)
    # TODO: Fetch data from 'patient_medical_history' table
    history_entries = []
    flash("Medical History view is not yet fully implemented.", "info")
    return render_template('Patient_Portal/MedicalInfo/view_history.html', history=history_entries)

@patient_medical_info_bp.route('/history/add', methods=['GET', 'POST'])
@login_required
def add_history_entry():
    """Add a new medical history entry."""
    if not check_patient_authorization(current_user): abort(403)
    if request.method == 'POST':
        # TODO: Get form data (condition_name, dates, notes)
        # TODO: Validate data
        # TODO: Insert into 'patient_medical_history' table
        flash("Medical History add is not yet fully implemented.", "info")
        return redirect(url_for('.view_history'))
    return render_template('Patient_Portal/MedicalInfo/add_history_form.html')

# --- Lifestyle / Occupation ---
# This info is on the 'patients' table, so likely updated via the main profile route.
# If you want a separate section:
@patient_medical_info_bp.route('/lifestyle', methods=['GET'])
@login_required
def view_lifestyle():
     """View lifestyle factors (occupation, marital status)."""
     if not check_patient_authorization(current_user): abort(403)
     # Fetch from patients table (likely already fetched in manage_profile)
     # Redirect or render a read-only view
     flash("Lifestyle info is managed via the main profile page.", "info")
     return redirect(url_for('patient_profile.manage_profile'))