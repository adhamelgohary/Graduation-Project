# routes/Patient_Portal/medical_info.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort, get_flashed_messages
)
from flask_login import login_required, current_user
from db import get_db_connection
# Assuming utils.auth_helpers.py exists in your utils folder
from utils.auth_helpers import check_patient_authorization 
from datetime import datetime, date, time, timedelta 
import math
import mysql.connector 
import re 
import logging
import decimal # For Decimal type from DB

logger = logging.getLogger(__name__)

# --- Blueprint Definition ---
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
        db_name = None
        if hasattr(conn, 'database') and conn.database: 
            db_name = conn.database
        else: 
            db_name_query = "SELECT DATABASE()"
            cursor.execute(db_name_query)
            db_name_result = cursor.fetchone()
            if db_name_result and db_name_result[0]:
                db_name = db_name_result[0]
        if not db_name: 
            db_name = current_app.config.get('MYSQL_DB')
        if not db_name:
            current_app.logger.error(f"Could not determine database name for ENUM {table_name}.{column_name}")
            return []
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0]
            if isinstance(enum_str, bytes): enum_str = enum_str.decode('utf-8')
            if enum_str.lower().startswith('enum(') and enum_str.endswith(')'):
                 values = [v.strip("'") for v in enum_str[len("enum("):-1].split(',')]
            ENUM_CACHE[cache_key] = values
    except Exception as e:
        current_app.logger.error(f"Error fetching ENUM {table_name}.{column_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return values


# --- Custom Jinja Filter (as defined before) ---
@patient_medical_info_bp.app_template_filter()
def format_timedelta_as_time(delta):
    if isinstance(delta, timedelta):
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        try:
            return time(hours % 24, minutes).strftime('%I:%M %p') 
        except ValueError:
            return str(delta) 
    elif isinstance(delta, time):
        return delta.strftime('%I:%M %p')
    return "N/A"


# --- Function to get full diet plan details (similar to the one in diet_plan_management.py) ---
# You might want to move this to a shared service/helper if used in multiple blueprints
def get_full_diet_plan_details_for_patient(plan_id):
    conn = None; cursor = None; details = {'plan': None, 'meals': []}
    try:
        conn = get_db_connection();
        if not conn: 
            logger.error(f"DB Connection failed for get_full_diet_plan_details_for_patient (Plan ID: {plan_id})")
            return None
        cursor = conn.cursor(dictionary=True)
        
        query_plan = """
            SELECT dp.plan_id, dp.plan_name, dp.description, dp.plan_type, dp.calories, 
                   dp.protein_grams, dp.carbs_grams, dp.fat_grams, dp.fiber_grams, dp.sodium_mg,
                   dp.target_conditions, u.username as creator_username
            FROM diet_plans dp
            LEFT JOIN users u ON dp.creator_id = u.user_id
            WHERE dp.plan_id = %s 
            LIMIT 1 
        """
        cursor.execute(query_plan, (plan_id,))
        details['plan'] = cursor.fetchone()

        if not details['plan']: 
            logger.warning(f"No plan details found for plan_id {plan_id} in get_full_diet_plan_details_for_patient.")
            return None

        query_meals = """
            SELECT meal_id, meal_name, meal_type, description, calories, 
                   protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, 
                   time_of_day
            FROM diet_plan_meals 
            WHERE plan_id = %s 
            ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack', 'other'), time_of_day, meal_id
        """
        cursor.execute(query_meals, (plan_id,))
        meals_raw = cursor.fetchall() # List of dicts, each dict has meal properties
        
        meals_processed = [] # This will become details['meals']
        if meals_raw:
            meal_ids = [meal_raw_item['meal_id'] for meal_raw_item in meals_raw] # Corrected variable name
            if meal_ids:
                placeholders = ', '.join(['%s'] * len(meal_ids))
                query_items = f"""SELECT item_id, food_name, serving_size, calories, 
                                protein_grams, carbs_grams, fat_grams, 
                                notes, alternatives, meal_id 
                                FROM diet_plan_food_items WHERE meal_id IN ({placeholders}) 
                                ORDER BY meal_id, item_id"""
                cursor.execute(query_items, tuple(meal_ids))
                all_items_raw = cursor.fetchall()
                
                items_by_meal = {}
                for item_raw in all_items_raw:
                    item = item_raw.copy()
                    for key, value in item.items():
                        if isinstance(value, decimal.Decimal):
                            item[key] = float(value) 
                    meal_id_fk = item['meal_id']
                    if meal_id_fk not in items_by_meal: items_by_meal[meal_id_fk] = []
                    items_by_meal[meal_id_fk].append(item)

                # *** MODIFIED SECTION TO CREATE THE CORRECT STRUCTURE FOR THE TEMPLATE ***
                for meal_properties_raw in meals_raw:
                    # meal_info will store all properties of the meal itself
                    meal_info_dict = meal_properties_raw.copy() 

                    # Convert timedelta to time object and add to meal_info_dict
                    original_time = meal_info_dict.get('time_of_day')
                    if isinstance(original_time, timedelta):
                        total_seconds = int(original_time.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        try:
                            meal_info_dict['time_of_day_obj'] = time(hours % 24, minutes)
                        except ValueError: 
                            logger.warning(f"Could not convert timedelta {original_time} to time for meal_id {meal_info_dict.get('meal_id')}. Storing as string.")
                            meal_info_dict['time_of_day_obj'] = None 
                            meal_info_dict['time_of_day'] = str(original_time) # Ensure template has a string if conversion fails
                    elif isinstance(original_time, time):
                         meal_info_dict['time_of_day_obj'] = original_time
                    else:
                        meal_info_dict['time_of_day_obj'] = None
                    
                    # Construct the meal_entry structure expected by the template
                    meal_entry_for_template = {
                        'meal_info': meal_info_dict, # All meal properties are here
                        'food_items_list': items_by_meal.get(meal_info_dict['meal_id'], []) # Food items for this meal
                    }
                    meals_processed.append(meal_entry_for_template)
            else: # Case where there are meals but meal_ids list is empty (should not happen if meals_raw is not empty)
                 for meal_properties_raw in meals_raw:
                    meal_info_dict = meal_properties_raw.copy()
                    # Process time_of_day_obj as above
                    original_time = meal_info_dict.get('time_of_day')
                    if isinstance(original_time, timedelta):
                        total_seconds = int(original_time.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        try:
                            meal_info_dict['time_of_day_obj'] = time(hours % 24, minutes)
                        except ValueError:
                            meal_info_dict['time_of_day_obj'] = None
                            meal_info_dict['time_of_day'] = str(original_time)
                    elif isinstance(original_time, time):
                        meal_info_dict['time_of_day_obj'] = original_time
                    else:
                        meal_info_dict['time_of_day_obj'] = None
                    
                    meal_entry_for_template = {
                        'meal_info': meal_info_dict,
                        'food_items_list': [] # No food items if meal_ids was empty
                    }
                    meals_processed.append(meal_entry_for_template)

        details['meals'] = meals_processed

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error in get_full_diet_plan_details_for_patient for plan_id {plan_id}: {err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_full_diet_plan_details_for_patient for plan_id {plan_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details


# --- Routes ---
# ... (view_medical_dashboard, manage_allergies, delete_allergy, manage_symptoms, manage_vitals, view_history routes remain the same) ...

@patient_medical_info_bp.route('/')
@login_required
def view_medical_dashboard():
    if not check_patient_authorization(current_user): abort(403)
    return redirect(url_for('patient_profile.my_account_dashboard'))

@patient_medical_info_bp.route('/allergies', methods=['GET', 'POST'])
@login_required
def manage_allergies():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None
    errors = [] 
    if request.method == 'POST':
        allergy_id_str = request.form.get('allergy_id')
        severity = request.form.get('severity')
        reaction = request.form.get('reaction_description', '').strip() or None
        diagnosed_date_str = request.form.get('diagnosed_date')
        notes = request.form.get('notes', '').strip() or None
        allergy_id = None
        if allergy_id_str and allergy_id_str.isdigit():
            allergy_id = int(allergy_id_str)
        else:
            errors.append("Please select a valid allergy.")
        allowed_severities = get_enum_values('patient_allergies', 'severity')
        if not severity or severity not in allowed_severities: 
            errors.append("Please select a valid severity level.")
        diagnosed_date = None
        if diagnosed_date_str:
             try: diagnosed_date = datetime.strptime(diagnosed_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid diagnosed date format. Use YYYY-MM-DD.")
        if errors:
            for err in errors: flash(err, "danger")
        else:
            try:
                conn = get_db_connection(); cursor = conn.cursor()
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
                current_app.logger.error(f"DB error saving allergy for P:{patient_id}, A:{allergy_id}: {err}")
                if err.errno == 1062: 
                    flash(f"This allergy is already recorded.", "warning")
                else:
                    flash("Database error saving allergy.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error saving allergy for P:{patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
    current_allergies = []
    all_allergies_list = [] 
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query_current = "SELECT pa.allergy_id, pa.severity, pa.reaction_description, pa.diagnosed_date, pa.notes, a.allergy_name, a.allergy_type FROM patient_allergies pa JOIN allergies a ON pa.allergy_id = a.allergy_id WHERE pa.patient_id = %s ORDER BY a.allergy_name"
        cursor.execute(query_current, (patient_id,))
        current_allergies = cursor.fetchall()
        cursor.execute("SELECT allergy_id, allergy_name, allergy_type FROM allergies ORDER BY allergy_name")
        all_allergies_list = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching allergies for P:{patient_id}: {e}")
        flash("Error loading allergy info.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    allergy_severities = get_enum_values('patient_allergies', 'severity')
    form_data = request.form if request.method == 'POST' and errors else {} 
    return render_template('Patient_Portal/MedicalInfo/manage_allergies.html',
                           current_allergies=current_allergies,
                           all_allergies_list=all_allergies_list,
                           allergy_severities=allergy_severities,
                           form_data=form_data)

@patient_medical_info_bp.route('/allergies/<int:allergy_id>/delete', methods=['POST'])
@login_required
def delete_allergy(allergy_id): 
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
        current_app.logger.error(f"Error deleting patient allergy (A_ID {allergy_id}) for P:{patient_id}: {e}")
        flash("Error removing allergy.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.manage_allergies'))

@patient_medical_info_bp.route('/symptoms', methods=['GET', 'POST'])
@login_required
def manage_symptoms():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;
    errors = []
    today_date_str = date.today().strftime('%Y-%m-%d') 
    if request.method == 'POST':
        symptom_id_str = request.form.get('symptom_id')
        reported_date_str = request.form.get('reported_date')
        onset_date_str = request.form.get('onset_date')
        severity = request.form.get('severity', '').strip() or None 
        duration = request.form.get('duration', '').strip() or None 
        frequency = request.form.get('frequency') or None 
        triggers = request.form.get('triggers', '').strip() or None
        alleviating_factors = request.form.get('alleviating_factors', '').strip() or None
        worsening_factors = request.form.get('worsening_factors', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        symptom_id = None
        if symptom_id_str and symptom_id_str.isdigit():
            symptom_id = int(symptom_id_str)
        else: errors.append("Please select a valid symptom.")
        reported_date = None
        if reported_date_str:
             try: reported_date = datetime.strptime(reported_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Reported Date format. Use YYYY-MM-DD.")
        else: errors.append("Reported Date is required.")
        onset_date = None
        if onset_date_str: 
             try: onset_date = datetime.strptime(onset_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Onset Date format. Use YYYY-MM-DD.")
        allowed_freq = get_enum_values('patient_symptoms', 'frequency')
        if frequency and frequency not in allowed_freq: 
            errors.append("Invalid frequency selected.")
        if errors:
             for err in errors: flash(err, "danger")
        else:
            try:
                conn = get_db_connection(); cursor = conn.cursor()
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
                 current_app.logger.error(f"DB error logging symptom P:{patient_id}: {err}")
                 flash("Database error logging symptom.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error logging symptom P:{patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
    symptom_history = []
    all_symptoms_list = [] 
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
        current_app.logger.error(f"Error fetching symptoms for P:{patient_id}: {e}")
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
                           today_date_str=today_date_str, 
                           form_data=form_data)

@patient_medical_info_bp.route('/vitals', methods=['GET', 'POST'])
@login_required
def manage_vitals():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    conn = None; cursor = None;
    errors = []
    today_date_str = date.today().strftime('%Y-%m-%d') 
    if request.method == 'POST':
        log_date_str = request.form.get('log_date')
        weight_kg_str = request.form.get('weight_kg')
        calories_consumed_str = request.form.get('calories_consumed')
        water_consumed_ml_str = request.form.get('water_consumed_ml')
        mood = request.form.get('mood') or None
        energy_level = request.form.get('energy_level') or None
        notes = request.form.get('notes', '').strip() or None
        log_date = None
        if log_date_str:
             try: log_date = datetime.strptime(log_date_str, '%Y-%m-%d').date()
             except ValueError: errors.append("Invalid Log Date format. Use YYYY-MM-DD.")
        else: errors.append("Log Date is required.")
        weight_val = None
        if weight_kg_str: 
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
        if mood and mood not in allowed_moods: errors.append("Invalid Mood selected.")
        allowed_energy = get_enum_values('user_nutrition_logs', 'energy_level')
        if energy_level and energy_level not in allowed_energy: errors.append("Invalid Energy Level selected.")
        if weight_val is None and calories_val is None and water_val is None and not notes and not mood and not energy_level:
            errors.append("Please provide at least one piece of information to log.")
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
                 current_app.logger.error(f"DB error logging nutrition/vitals for P:{patient_id}: {err}")
                 flash("Database error logging information.", "danger")
            except Exception as e:
                 if conn and conn.is_connected(): conn.rollback()
                 current_app.logger.error(f"Error logging nutrition/vitals for P:{patient_id}: {e}", exc_info=True)
                 flash("An unexpected error occurred.", "danger")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
    vitals_history = [] 
    current_patient_data = {} 
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT height_cm, weight_kg FROM patients WHERE user_id = %s", (patient_id,))
        current_patient_data = cursor.fetchone() or {} 
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
        current_app.logger.error(f"Error fetching nutrition/vitals log for P:{patient_id}: {e}")
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
                           current_patient_data=current_patient_data, 
                           mood_options=mood_options,
                           energy_options=energy_options,
                           current_page=page, total_pages=total_pages,
                           today_date_str=today_date_str, 
                           form_data=form_data)

@patient_medical_info_bp.route('/history', methods=['GET'])
@login_required
def view_history():
    if not check_patient_authorization(current_user): 
        abort(403)
    patient_id = current_user.id
    all_history_entries = []
    conn = None; cursor = None
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * ITEMS_PER_PAGE
    total_items = 0
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return render_template('Patient_Portal/MedicalInfo/view_history.html', history=[], current_page=1, total_pages=0, patient_name=f"{current_user.first_name} {current_user.last_name}")
        cursor = conn.cursor(dictionary=True)
        query_diagnoses = """
            SELECT 'diagnosis' AS entry_type, d.diagnosis_id AS id, d.diagnosis_name AS title, d.diagnosis_date AS event_date, 
                   d.is_resolved, d.resolved_date, d.description, d.notes AS entry_notes, d.severity, d.is_chronic, d.treatment_plan,
                   CONCAT(u_doc.first_name, ' ', u_doc.last_name) AS related_person_name, 'Diagnosing Doctor' as related_person_role
            FROM diagnoses d LEFT JOIN users u_doc ON d.doctor_id = u_doc.user_id
            WHERE d.patient_id = %s """
        cursor.execute(query_diagnoses, (patient_id,))
        diagnoses = cursor.fetchall(); all_history_entries.extend(diagnoses)
        query_symptoms = """
            SELECT 'symptom' AS entry_type, ps.patient_symptom_id AS id, s.symptom_name AS title, ps.reported_date AS event_date,
                   ps.onset_date, ps.severity, ps.duration, ps.frequency, ps.triggers, ps.alleviating_factors, ps.worsening_factors, ps.notes AS entry_notes,
                   CONCAT(u_rep.first_name, ' ', u_rep.last_name) AS related_person_name, 'Reported By' as related_person_role
            FROM patient_symptoms ps JOIN symptoms s ON ps.symptom_id = s.symptom_id
            LEFT JOIN users u_rep ON ps.reported_by = u_rep.user_id
            WHERE ps.patient_id = %s """
        cursor.execute(query_symptoms, (patient_id,)); symptoms = cursor.fetchall(); all_history_entries.extend(symptoms)
        query_vaccinations = """
            SELECT 'vaccination' AS entry_type, pv.patient_vaccination_id AS id, v.vaccine_name AS title, pv.administration_date AS event_date,
                   pv.dose_number, pv.lot_number, pv.notes AS entry_notes,
                   CONCAT(u_admin.first_name, ' ', u_admin.last_name) AS related_person_name, 'Administered By' as related_person_role
            FROM patient_vaccinations pv JOIN vaccines v ON pv.vaccine_id = v.vaccine_id
            LEFT JOIN users u_admin ON pv.administered_by_id = u_admin.user_id
            WHERE pv.patient_id = %s """
        cursor.execute(query_vaccinations, (patient_id,)); vaccinations = cursor.fetchall(); all_history_entries.extend(vaccinations)
        all_history_entries.sort(key=lambda x: x['event_date'] if x['event_date'] else date.min, reverse=True)
        total_items = len(all_history_entries)
        paginated_history = all_history_entries[offset : offset + ITEMS_PER_PAGE]
        total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and total_items > 0 else 0
    except mysql.connector.Error as err:
        flash("Error loading comprehensive medical history.", "danger")
        current_app.logger.error(f"DB error fetching combined history for P:{patient_id}: {err}")
        paginated_history = []; total_pages = 0
    except Exception as e:
        flash("An unexpected error occurred while loading medical history.", "danger")
        current_app.logger.error(f"Error fetching combined history for P:{patient_id}: {e}", exc_info=True)
        paginated_history = []; total_pages = 0
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    if not paginated_history and page == 1 and not get_flashed_messages(category_filter=["warning", "danger"]):
        flash(f"No medical history items found for {current_user.first_name}.", "info")
    return render_template('Patient_Portal/MedicalInfo/view_history.html', 
                           history=paginated_history, current_page=page, total_pages=total_pages,
                           patient_name=f"{current_user.first_name} {current_user.last_name}")

# --- Route for Patient's Assigned Diet Plans ---
@patient_medical_info_bp.route('/my-diet-plans')
@login_required
def my_assigned_plans():
    if not check_patient_authorization(current_user): abort(403)
    patient_id = current_user.id
    assigned_plans_data = [] 
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            flash("Database connection error.", "danger")
            return render_template('Patient_Portal/MedicalInfo/my_assigned_plans.html', assigned_plans_data=[])
        cursor = conn.cursor(dictionary=True)
        # Query to fetch active assigned diet plans for the patient
        query_assigned = """
            SELECT 
                udp.user_diet_plan_id,
                udp.start_date,
                udp.end_date,
                udp.notes AS assignment_notes,
                dp.plan_id,
                dp.plan_name,
                dp.description AS plan_description, 
                dp.plan_type,
                dp.calories AS plan_calories, 
                CONCAT(u_assigner.first_name, ' ', u_assigner.last_name) AS assigner_name
            FROM user_diet_plans udp
            JOIN diet_plans dp ON udp.plan_id = dp.plan_id
            LEFT JOIN users u_assigner ON udp.assigned_by = u_assigner.user_id
            WHERE udp.user_id = %s AND udp.active = TRUE
            ORDER BY udp.start_date DESC 
        """
        cursor.execute(query_assigned, (patient_id,))
        active_assigned_plans_info = cursor.fetchall()

        if not active_assigned_plans_info:
            flash("You currently have no active diet plans assigned.", "info")
        else:
            for assigned_plan_info in active_assigned_plans_info:
                # For each assigned plan, fetch its full details including meals and items
                plan_details = get_full_diet_plan_details_for_patient(assigned_plan_info['plan_id'])
                if plan_details: 
                    assigned_plans_data.append({
                        'assignment_info': assigned_plan_info, 
                        'plan_details': plan_details 
                    })
                else:
                    logger.warning(f"Could not fetch full details for assigned plan_id {assigned_plan_info['plan_id']} for patient {patient_id}. Plan may be incomplete or an error occurred.")
                    assigned_plans_data.append({ 
                        'assignment_info': assigned_plan_info, 
                        'plan_details': {'plan': {'plan_name': assigned_plan_info['plan_name'], 'description': 'Details currently unavailable or plan is incomplete.'}, 'meals': []}
                    })
    except mysql.connector.Error as err:
        flash("Error loading your assigned diet plans.", "danger")
        current_app.logger.error(f"DB error fetching assigned diet plans for patient {patient_id}: {err}", exc_info=True)
    except Exception as e:
        flash("An unexpected error occurred while loading your diet plans.", "danger")
        current_app.logger.error(f"Error fetching assigned diet plans for patient {patient_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Patient_Portal/MedicalInfo/my_assigned_plans.html', 
                           assigned_plans_data=assigned_plans_data)

@patient_medical_info_bp.route('/lifestyle')
@login_required
def view_lifestyle():
     if not check_patient_authorization(current_user): abort(403)
     flash("Lifestyle information (occupation, marital status) is managed on your main profile page.", "info")
     return redirect(url_for('patient_profile.manage_profile'))