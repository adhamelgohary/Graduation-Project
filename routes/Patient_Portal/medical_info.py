# routes/Patient_Portal/medical_info.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort, get_flashed_messages # <<<<<<< ADD get_flashed_messages HERE
)
from flask_login import login_required, current_user
from db import get_db_connection
from utils.auth_helpers import check_patient_authorization
from datetime import datetime, date # Ensure date is imported if used
import math
import mysql.connector # Import for specific error handling


# Define Blueprint
patient_medical_info_bp = Blueprint(
    'patient_medical_info',
    __name__,
    url_prefix='/patient/medical-info',
    template_folder='../../templates'
)

ITEMS_PER_PAGE = 10

# --- Helper to get ENUMs (Keep as is) ---
ENUM_CACHE = {}
def get_enum_values(table_name, column_name):
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE: return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection();
        if not conn:
            current_app.logger.error(f"Failed to get DB connection for ENUM {table_name}.{column_name}")
            return []
        cursor = conn.cursor()
        db_name_query = "SELECT DATABASE()"
        cursor.execute(db_name_query)
        db_name_result = cursor.fetchone()
        if not db_name_result or not db_name_result[0]:
            # Fallback to config if connection.database is not set and SELECT DATABASE() fails
            db_name = current_app.config.get('MYSQL_DB')
            if not db_name:
                current_app.logger.error(f"Could not determine database name for ENUM {table_name}.{column_name}")
                return []
        else:
            db_name = db_name_result[0]

        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0]
            if isinstance(enum_str, bytes): enum_str = enum_str.decode('utf-8')
            if enum_str.lower().startswith('enum(') and enum_str.endswith(')'): # Make startswith case-insensitive
                 values = [v.strip("'") for v in enum_str[5:-1].split(',')]
            ENUM_CACHE[cache_key] = values
            return values
    except Exception as e:
        current_app.logger.error(f"Error fetching ENUM {table_name}.{column_name}: {e}")
        return [] # Return empty list on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return values # Return potentially empty list if no values found

# --- Routes ---

@patient_medical_info_bp.route('/')
@login_required
def view_medical_dashboard():
    if not check_patient_authorization(current_user): abort(403)
    # Redirect to the main "My Account" dashboard which serves as the medical info hub
    return redirect(url_for('patient_profile.my_account_dashboard'))

# --- Allergies ---
@patient_medical_info_bp.route('/allergies', methods=['GET', 'POST'])
@login_required
def manage_allergies():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None

    if request.method == 'POST':
        allergy_id_str = request.form.get('allergy_id')
        severity = request.form.get('severity')
        reaction = request.form.get('reaction_description', '').strip() or None
        diagnosed_date_str = request.form.get('diagnosed_date')
        notes = request.form.get('notes', '').strip() or None
        errors = []

        allergy_id = None
        if allergy_id_str and allergy_id_str.isdigit():
            allergy_id = int(allergy_id_str)
        else:
            errors.append("Please select a valid allergy.")

        allowed_severities = get_enum_values('patient_allergies', 'severity')
        if not severity or severity not in allowed_severities: # Also check if severity is provided
            errors.append("Please select a valid severity level.")
        
        diagnosed_date = None
        if diagnosed_date_str:
             try: diagnosed_date = datetime.strptime(diagnosed_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid diagnosed date format. Use YYYY-MM-DD.")
        # Diagnosed date can be optional

        if errors:
            for err in errors: flash(err, "danger")
        else:
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                # Using INSERT ... ON DUPLICATE KEY UPDATE for robustness
                # Assumes (patient_id, allergy_id) is the PRIMARY KEY or a UNIQUE KEY
                # in patient_allergies for ON DUPLICATE KEY UPDATE to work as expected.
                # Your schema shows (patient_id, allergy_id) as PK, so this is correct.
                sql = """INSERT INTO patient_allergies
                         (patient_id, allergy_id, severity, reaction_description, diagnosed_date, notes, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                         ON DUPLICATE KEY UPDATE
                         severity = VALUES(severity),
                         reaction_description = VALUES(reaction_description),
                         diagnosed_date = VALUES(diagnosed_date),
                         notes = VALUES(notes),
                         updated_at = NOW()"""
                cursor.execute(sql, (patient_id, allergy_id, severity, reaction, diagnosed_date, notes))
                conn.commit()
                flash("Allergy information saved successfully.", "success")
                return redirect(url_for('.manage_allergies'))
            except mysql.connector.Error as err:
                if conn: conn.rollback()
                current_app.logger.error(f"DB error saving allergy for patient {patient_id}, allergy_id {allergy_id}: {err}")
                if err.errno == 1062: # Duplicate entry, though ON DUPLICATE KEY should handle it
                    flash(f"This allergy is already recorded. You can edit it from the list.", "warning")
                else:
                    flash("Database error saving allergy information.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error saving allergy for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred while saving allergy information.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST error
    current_allergies = []
    all_allergies_list = [] # For the dropdown
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query_current = """SELECT pa.allergy_id, pa.severity, pa.reaction_description, pa.diagnosed_date, pa.notes,
                                  a.allergy_name, a.allergy_type
                           FROM patient_allergies pa
                           JOIN allergies a ON pa.allergy_id = a.allergy_id
                           WHERE pa.patient_id = %s ORDER BY a.allergy_name"""
        cursor.execute(query_current, (patient_id,))
        current_allergies = cursor.fetchall()

        cursor.execute("SELECT allergy_id, allergy_name, allergy_type FROM allergies ORDER BY allergy_name")
        all_allergies_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching allergies for patient {patient_id}: {e}")
        flash("Error loading allergy information.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    allergy_severities = get_enum_values('patient_allergies', 'severity')
    form_data = request.form if request.method == 'POST' and errors else {} # Pass form data only if there were errors

    return render_template('Patient_Portal/MedicalInfo/manage_allergies.html',
                           current_allergies=current_allergies,
                           all_allergies_list=all_allergies_list,
                           allergy_severities=allergy_severities,
                           form_data=form_data) # form_data will be populated on POST error

@patient_medical_info_bp.route('/allergies/<int:allergy_id>/delete', methods=['POST'])
@login_required
def delete_allergy(allergy_id): # allergy_id here is from the master allergies table
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn=None; cursor=None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        # The PK for patient_allergies is (patient_id, allergy_id)
        sql = "DELETE FROM patient_allergies WHERE patient_id = %s AND allergy_id = %s"
        cursor.execute(sql, (patient_id, allergy_id))
        conn.commit()
        if cursor.rowcount > 0: flash("Allergy removed successfully.", "success")
        else: flash("Allergy not found for this patient or already removed.", "warning")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting patient allergy (allergy_id {allergy_id}) for patient {patient_id}: {e}")
        flash("Error removing allergy.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.manage_allergies'))


# --- Symptoms ---
@patient_medical_info_bp.route('/symptoms', methods=['GET', 'POST'])
@login_required
def manage_symptoms():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;

    today_date_str = date.today().strftime('%Y-%m-%d') # For defaulting date input

    if request.method == 'POST':
        symptom_id_str = request.form.get('symptom_id')
        reported_date_str = request.form.get('reported_date')
        onset_date_str = request.form.get('onset_date')
        severity = request.form.get('severity', '').strip() or None # This is varchar
        duration = request.form.get('duration', '').strip() or None # varchar
        frequency = request.form.get('frequency') or None # ENUM
        # New fields from schema for patient_symptoms:
        triggers = request.form.get('triggers', '').strip() or None
        alleviating_factors = request.form.get('alleviating_factors', '').strip() or None
        worsening_factors = request.form.get('worsening_factors', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        errors = []

        symptom_id = None
        if symptom_id_str and symptom_id_str.isdigit():
            symptom_id = int(symptom_id_str)
        else:
            errors.append("Please select a valid symptom.")

        reported_date = None
        if reported_date_str:
             try: reported_date = datetime.strptime(reported_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Reported Date format. Use YYYY-MM-DD.")
        else: errors.append("Reported Date is required.")

        onset_date = None
        if onset_date_str: # Onset date is optional
             try: onset_date = datetime.strptime(onset_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Onset Date format. Use YYYY-MM-DD.")
        
        allowed_freq = get_enum_values('patient_symptoms', 'frequency')
        if frequency and frequency not in allowed_freq: # Frequency is optional
            errors.append("Invalid frequency selected.")

        if errors:
             for err in errors: flash(err, "danger")
        else:
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                # Schema has patient_symptom_id as auto_increment PK
                # reported_by should be current_user.id (patient themselves)
                sql = """INSERT INTO patient_symptoms
                         (patient_id, symptom_id, reported_date, onset_date, severity, 
                          duration, frequency, triggers, alleviating_factors, worsening_factors, notes, 
                          reported_by, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())"""
                params = (patient_id, symptom_id, reported_date, onset_date, severity, 
                          duration, frequency, triggers, alleviating_factors, worsening_factors, notes, 
                          patient_id)
                cursor.execute(sql, params)
                conn.commit()
                flash("Symptom logged successfully.", "success")
                return redirect(url_for('.manage_symptoms'))
            except mysql.connector.Error as err:
                 if conn: conn.rollback()
                 current_app.logger.error(f"DB error logging symptom for patient {patient_id}: {err}")
                 flash("Database error logging symptom.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error logging symptom for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred while logging symptom.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST Error
    symptom_history = []
    all_symptoms_list = [] # For dropdown
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query_history = """SELECT SQL_CALC_FOUND_ROWS 
                               ps.patient_symptom_id, ps.reported_date, ps.onset_date, 
                               ps.severity, ps.duration, ps.frequency, ps.notes,
                               ps.triggers, ps.alleviating_factors, ps.worsening_factors,
                               s.symptom_name
                           FROM patient_symptoms ps
                           JOIN symptoms s ON ps.symptom_id = s.symptom_id
                           WHERE ps.patient_id = %s
                           ORDER BY ps.reported_date DESC, ps.created_at DESC
                           LIMIT %s OFFSET %s"""
        cursor.execute(query_history, (patient_id, ITEMS_PER_PAGE, offset))
        symptom_history = cursor.fetchall()
        
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        total_items = total_row['total'] if total_row else 0
        
        cursor.execute("SELECT symptom_id, symptom_name FROM symptoms ORDER BY symptom_name")
        all_symptoms_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching symptoms for patient {patient_id}: {e}")
        flash("Error loading symptom information.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and total_items > 0 else 0
    symptom_frequencies = get_enum_values('patient_symptoms', 'frequency')
    form_data = request.form if request.method == 'POST' and errors else {}

    return render_template('Patient_Portal/MedicalInfo/manage_symptoms.html',
                           symptom_history=symptom_history,
                           all_symptoms_list=all_symptoms_list,
                           symptom_frequencies=symptom_frequencies,
                           current_page=page, total_pages=total_pages,
                           today_date_str=today_date_str, # For defaulting date input on GET
                           form_data=form_data)


# --- Vitals / Physical Characteristics ---
@patient_medical_info_bp.route('/vitals', methods=['GET', 'POST'])
@login_required
def manage_vitals():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;
    today_date_str = date.today().strftime('%Y-%m-%d') # For defaulting date input

    if request.method == 'POST':
        log_date_str = request.form.get('log_date')
        weight_kg_str = request.form.get('weight_kg')
        # Height is in `patients` table, less frequently logged as a "vital log"
        # user_nutrition_logs also has calories_consumed, water_consumed_ml, mood, energy_level
        calories_consumed_str = request.form.get('calories_consumed')
        water_consumed_ml_str = request.form.get('water_consumed_ml')
        mood = request.form.get('mood') or None
        energy_level = request.form.get('energy_level') or None
        notes = request.form.get('notes', '').strip() or None
        errors = []

        log_date = None
        if log_date_str:
             try: log_date = datetime.strptime(log_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Log Date format. Use YYYY-MM-DD.")
        else: errors.append("Log Date is required.")

        weight_val = None
        if weight_kg_str: # Weight is optional in user_nutrition_logs
            try: weight_val = float(weight_kg_str)
            except ValueError: errors.append("Invalid Weight format. Must be a number.")
        
        calories_val = None
        if calories_consumed_str:
            try: calories_val = int(calories_consumed_str)
            except ValueError: errors.append("Invalid Calories format. Must be a whole number.")

        water_val = None
        if water_consumed_ml_str:
            try: water_val = int(water_consumed_ml_str)
            except ValueError: errors.append("Invalid Water Consumed format. Must be a whole number.")
        
        allowed_moods = get_enum_values('user_nutrition_logs', 'mood')
        if mood and mood not in allowed_moods:
            errors.append("Invalid Mood selected.")

        allowed_energy = get_enum_values('user_nutrition_logs', 'energy_level')
        if energy_level and energy_level not in allowed_energy:
            errors.append("Invalid Energy Level selected.")

        # Require at least one piece of data to be logged for the date
        if weight_val is None and calories_val is None and water_val is None and not notes and not mood and not energy_level:
            errors.append("Please provide at least one piece of information to log (e.g., weight, calories, water, notes, mood, or energy level).")


        if errors:
            for err in errors: flash(err, "danger")
        else:
            try:
                conn = get_db_connection(); cursor = conn.cursor()
                sql = """INSERT INTO user_nutrition_logs 
                         (user_id, log_date, weight_kg, calories_consumed, water_consumed_ml, 
                          notes, mood, energy_level, created_at, updated_at)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                         ON DUPLICATE KEY UPDATE
                         weight_kg = VALUES(weight_kg), 
                         calories_consumed = VALUES(calories_consumed),
                         water_consumed_ml = VALUES(water_consumed_ml),
                         notes = VALUES(notes), 
                         mood = VALUES(mood),
                         energy_level = VALUES(energy_level),
                         updated_at = NOW()"""
                params = (patient_id, log_date, weight_val, calories_val, water_val, 
                          notes, mood, energy_level)
                cursor.execute(sql, params)
                conn.commit()
                flash("Daily log updated successfully.", "success")
                return redirect(url_for('.manage_vitals'))
            except mysql.connector.Error as err:
                 if conn: conn.rollback()
                 current_app.logger.error(f"DB error logging nutrition/vitals for patient {patient_id}: {err}")
                 flash("Database error logging information.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error logging nutrition/vitals for patient {patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()

    # GET Request or POST Error
    vitals_history = [] # From user_nutrition_logs
    current_patient_data = {} # For height from patients table
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Get current height from patients table for display context
        cursor.execute("SELECT height_cm, weight_kg FROM patients WHERE user_id = %s", (patient_id,))
        current_patient_data = cursor.fetchone() or {} # Also fetch latest weight for consistency if needed

        # Get paginated log history from user_nutrition_logs
        query_history = """SELECT SQL_CALC_FOUND_ROWS 
                               log_id, log_date, weight_kg, calories_consumed, water_consumed_ml, 
                               notes, mood, energy_level
                           FROM user_nutrition_logs
                           WHERE user_id = %s
                           ORDER BY log_date DESC
                           LIMIT %s OFFSET %s"""
        cursor.execute(query_history, (patient_id, ITEMS_PER_PAGE, offset))
        vitals_history = cursor.fetchall()
        
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        total_items = total_row['total'] if total_row else 0
    except Exception as e:
        current_app.logger.error(f"Error fetching nutrition/vitals log for patient {patient_id}: {e}")
        flash("Error loading log history.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and total_items > 0 else 0
    form_data = request.form if request.method == 'POST' and errors else {}
    
    mood_options = get_enum_values('user_nutrition_logs', 'mood')
    energy_options = get_enum_values('user_nutrition_logs', 'energy_level')


    return render_template('Patient_Portal/MedicalInfo/manage_vitals.html',
                           vitals_history=vitals_history,
                           current_patient_data=current_patient_data, # Contains height_cm, weight_kg
                           mood_options=mood_options,
                           energy_options=energy_options,
                           current_page=page, total_pages=total_pages,
                           today_date_str=today_date_str, # For defaulting date input on GET
                           form_data=form_data)


# --- Medical History (Self-Reported by Patient) ---
# This assumes a NEW table is created, e.g., `patient_self_reported_history`
# Schema for patient_self_reported_history (example):
# CREATE TABLE patient_self_reported_history (
#   history_id INT AUTO_INCREMENT PRIMARY KEY,
#   patient_id INT NOT NULL,
#   condition_name VARCHAR(255) NOT NULL,
#   start_date DATE NULL,
#   end_date DATE NULL,
#   notes TEXT NULL,
#   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
#   FOREIGN KEY (patient_id) REFERENCES users(user_id) ON DELETE CASCADE
# );
@patient_medical_info_bp.route('/history', methods=['GET'])
@login_required
def view_history():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    history_entries = []
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Query your new patient_self_reported_history table
        query = """SELECT history_id, condition_name, start_date, end_date, notes 
                   FROM patient_self_reported_history
                   WHERE patient_id = %s 
                   ORDER BY start_date DESC, created_at DESC"""
        cursor.execute(query, (patient_id,))
        history_entries = cursor.fetchall()
    except mysql.connector.Error as err:
        if err.errno == 1146: # Table doesn't exist
            flash("Medical History feature's database table not found. Please contact support.", "warning")
            current_app.logger.error(f"Table 'patient_self_reported_history' likely missing: {err}")
        else:
            flash("Error loading medical history.", "danger")
            current_app.logger.error(f"DB error fetching self-reported history for patient {patient_id}: {err}")
    except Exception as e:
        flash("An unexpected error occurred while loading medical history.", "danger")
        current_app.logger.error(f"Error fetching self-reported history for patient {patient_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    if not history_entries and not any(m[1] == 'warning' for m in get_flashed_messages(with_categories=True)): # Avoid double message
        flash("No self-reported medical history found. You can add entries below.", "info")
        
    return render_template('Patient_Portal/MedicalInfo/view_history.html', history=history_entries)


# --- Lifestyle / Occupation ---
# This is managed in profile.py, so the redirect is correct.
@patient_medical_info_bp.route('/lifestyle')
@login_required
def view_lifestyle():
     if not check_patient_authorization(current_user): abort(403)
     flash("Lifestyle information (occupation, marital status) is managed on your main profile page.", "info")
     return redirect(url_for('patient_profile.manage_profile'))