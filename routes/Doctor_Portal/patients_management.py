# routes/Doctor_Portal/patients_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, has_app_context, send_from_directory, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, timedelta, time # Ensure time is imported
import math # For calculating age
import logging
import os # For os.path.exists, os.path.join
import json # For reading JSON file content

# Configure logger
logger = logging.getLogger(__name__)

# --- Attempt to import REAL functions from utils ---
try:
    from .utils import (
        check_doctor_authorization,
        is_doctor_authorized_for_patient,
        get_provider_id,
        get_enum_values,
        get_all_simple,
        calculate_age,
    )
    if 'get_all_simple' not in locals(): raise ImportError("get_all_simple not found")
    if 'get_enum_values' not in locals(): raise ImportError("get_enum_values not found")
except (ImportError, ValueError) as e1:
    logger.warning(f"Relative import for utils failed: {e1}. Trying non-relative.")
    try:
        from utils import (
            check_doctor_authorization, is_doctor_authorized_for_patient,
            get_provider_id, get_enum_values, get_all_simple, calculate_age,
        )
        if 'get_all_simple' not in locals(): raise ImportError("get_all_simple not found (non-relative)")
        if 'get_enum_values' not in locals(): raise ImportError("get_enum_values not found (non-relative)")
    except ImportError as e2:
        logger.critical(f"CRITICAL FAILURE: Could not import required functions from utils.py: {e2}", exc_info=True)
        def check_doctor_authorization(user, **kwargs): logger.error("UTILS FALLBACK: check_doctor_authorization"); return False
        def is_doctor_authorized_for_patient(doc_id, pat_id): logger.error("UTILS FALLBACK: is_doctor_authorized_for_patient"); return False
        def get_provider_id(user): logger.error("UTILS FALLBACK: get_provider_id"); return None
        def get_enum_values(table, column): logger.error(f"UTILS FALLBACK: get_enum_values for {table}.{column}"); return []
        def get_all_simple(table, id_col, name_expr, **kwargs): logger.error(f"UTILS FALLBACK: get_all_simple for {table}"); return []
        def calculate_age(dob): logger.error("UTILS FALLBACK: calculate_age"); return None

patients_bp = Blueprint(
    'patients',
    __name__,
    url_prefix='/portal/patients',
    template_folder='../../templates'
)

# --- Helper Functions ---
def get_patients_for_doctor(doctor_id, search_term=None):
    conn = None; cursor = None; patients_list = []
    current_logger = current_app.logger if has_app_context() else logger
    if not doctor_id: current_logger.warning("get_patients_for_doctor: no doctor_id."); return []
    try:
        conn = get_db_connection();
        if not conn: current_logger.error("get_patients_for_doctor: DB Connection failed."); return []
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT DISTINCT u.user_id, u.first_name, u.last_name, u.email, u.phone,
                            p.date_of_birth, p.gender
            FROM users u JOIN patients p ON u.user_id = p.user_id
                         JOIN appointments a ON p.user_id = a.patient_id
            WHERE a.doctor_id = %s AND u.user_type = 'patient' AND a.status != 'canceled'
        """
        params = [doctor_id]
        if search_term:
            search_like = f"%{search_term}%"
            query += " AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s OR CONCAT(u.first_name, ' ', u.last_name) LIKE %s OR CONCAT(u.last_name, ', ', u.first_name) LIKE %s OR CAST(u.user_id AS CHAR) LIKE %s)"
            params.extend([search_like, search_like, search_like, search_like, search_like, search_like])
        query += " ORDER BY u.last_name, u.first_name"
        cursor.execute(query, tuple(params)); patients_list = cursor.fetchall()
        for patient in patients_list: patient['age'] = calculate_age(patient.get('date_of_birth'))
    except Exception as e: current_logger.error(f"Error fetching patients for dr {doctor_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return patients_list

def get_patient_full_details(patient_id):
    conn = None; cursor = None
    details = {
        "user_info": None, "patient_info": None, "insurance_info": None,
        "allergies": [], "appointments": [], "diagnoses": [], "symptoms": [],
        "vaccinations": []
    }
    current_logger = current_app.logger if has_app_context() else logger
    if not patient_id: current_logger.warning("get_patient_full_details: no patient_id."); return None
    try:
        conn = get_db_connection();
        if not conn: current_logger.error(f"get_patient_full_details: DB conn failed for P:{patient_id}."); return None
        cursor = conn.cursor(dictionary=True)

        query_user_patient = """
            SELECT u.user_id, u.username, u.email, u.first_name, u.last_name,
                   u.phone, u.country, u.account_status, u.profile_picture,
                   p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
                   p.insurance_provider_id, p.insurance_policy_number,
                   p.insurance_group_number, p.insurance_expiration,
                   p.marital_status, p.occupation
            FROM users u
            LEFT JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_id = %s AND u.user_type = 'patient'"""
        cursor.execute(query_user_patient, (patient_id,))
        patient_data = cursor.fetchone()
        if not patient_data: current_logger.warning(f"No patient data for ID {patient_id}."); return None

        details["user_info"] = {k: v for k, v in patient_data.items() if k in ['user_id', 'username', 'email', 'first_name', 'last_name', 'phone', 'country', 'account_status', 'profile_picture']}
        details["patient_info"] = {k: v for k, v in patient_data.items() if k in ['date_of_birth', 'gender', 'blood_type', 'height_cm', 'weight_kg', 'insurance_provider_id', 'insurance_policy_number', 'insurance_group_number', 'insurance_expiration', 'marital_status', 'occupation']}
        details["patient_info"]['age'] = calculate_age(details["patient_info"].get('date_of_birth'))

        if details["patient_info"].get('insurance_provider_id'):
            cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE id = %s", (details["patient_info"]['insurance_provider_id'],))
            details["insurance_info"] = cursor.fetchone()

        queries = {
            "allergies": "SELECT al.allergy_id, al.allergy_name, al.allergy_type, pa.severity, pa.reaction_description, pa.diagnosed_date, pa.notes FROM patient_allergies pa JOIN allergies al ON pa.allergy_id = al.allergy_id WHERE pa.patient_id = %s ORDER BY al.allergy_name",
            "appointments": "SELECT a.*, at.type_name AS appointment_type_name, CONCAT(d_user.first_name, ' ', d_user.last_name) as doctor_name FROM appointments a LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id JOIN users d_user ON a.doctor_id = d_user.user_id WHERE a.patient_id = %s ORDER BY a.appointment_date DESC, a.start_time DESC LIMIT 50",
            "diagnoses": "SELECT dx.*, CONCAT(d_user.first_name, ' ', d_user.last_name) as doctor_name FROM diagnoses dx LEFT JOIN users d_user ON dx.doctor_id = d_user.user_id WHERE dx.patient_id = %s ORDER BY dx.diagnosis_date DESC LIMIT 50",
            "symptoms": "SELECT ps.*, s.symptom_name, CONCAT(r_user.first_name, ' ', r_user.last_name) as reporter_name FROM patient_symptoms ps JOIN symptoms s ON ps.symptom_id = s.symptom_id JOIN users r_user ON ps.reported_by = r_user.user_id WHERE ps.patient_id = %s ORDER BY ps.reported_date DESC LIMIT 100",
            "vaccinations": "SELECT pv.*, v.vaccine_name, v.abbreviation as vaccine_abbreviation FROM patient_vaccinations pv JOIN vaccines v ON pv.vaccine_id = v.vaccine_id WHERE pv.patient_id = %s ORDER BY pv.administration_date DESC"
        }
        for key, query_str in queries.items():
            cursor.execute(query_str, (patient_id,)); details[key] = cursor.fetchall()
            if key == "appointments":
                for appt in details[key]:
                    start_time_val = appt.get('start_time')
                    end_time_val = appt.get('end_time')
                    appt['start_time_str'] = str(start_time_val)[:5] if isinstance(start_time_val, timedelta) else (start_time_val.strftime('%H:%M') if isinstance(start_time_val, time) else None)
                    appt['end_time_str'] = str(end_time_val)[:5] if isinstance(end_time_val, timedelta) else (end_time_val.strftime('%H:%M') if isinstance(end_time_val, time) else None)
            # Removed tracker_reports specific formatting
    except (mysql.connector.Error, ConnectionError) as err:
        current_logger.error(f"DB error get_patient_full_details P:{patient_id}: {err}", exc_info=True); return None
    except Exception as e:
        current_logger.error(f"Unexpected error get_patient_full_details P:{patient_id}: {e}", exc_info=True); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

# --- Patient List Route (Remains the same) ---
@patients_bp.route('/', methods=['GET'])
@login_required
def patients_list():
    # ... (your existing patients_list logic) ...
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    search_term = request.args.get('search', '').strip()
    patients_data = get_patients_for_doctor(doctor_id, search_term)
    return render_template('Doctor_Portal/Patients/patients_list.html', patients=patients_data, search_term=search_term)


# --- NEW: Route for Patient Details Tab ---
@patients_bp.route('/<int:patient_id>/details', methods=['GET'])
@login_required
def view_patient_details_tab(patient_id):
    current_logger = current_app.logger if has_app_context() else logger
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized for this patient's record.", "danger"); return redirect(url_for('.patients_list'))

    patient_details_full = get_patient_full_details(patient_id)
    if not patient_details_full or not patient_details_full.get("user_info"):
        flash("Patient record not found or incomplete.", "warning"); return redirect(url_for('.patients_list'))
    
    return render_template(
        'Doctor_Portal/Patients/patient_profile_details.html',
        patient=patient_details_full,
        current_section='details', # For active tab highlighting in layout
        patient_id=patient_id 
    )

# --- NEW: Route for Patient Medical Records Tab ---
@patients_bp.route('/<int:patient_id>/records', methods=['GET'])
@login_required
def view_patient_records_tab(patient_id):
    current_logger = current_app.logger if has_app_context() else logger
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized for this patient's record.", "danger"); return redirect(url_for('.patients_list'))

    patient_details_full = get_patient_full_details(patient_id) # Fetches appts, diagnoses, etc.
    if not patient_details_full or not patient_details_full.get("user_info"):
        flash("Patient record not found or incomplete.", "warning"); return redirect(url_for('.patients_list'))

    return render_template(
        'Doctor_Portal/Patients/patient_profile_records.html',
        patient=patient_details_full,
        current_section='records',
        patient_id=patient_id
    )

# --- NEW: Route for Patient Add Clinical Entry Tab ---
@patients_bp.route('/<int:patient_id>/add-entry', methods=['GET'])
@login_required
def view_patient_add_entry_tab(patient_id):
    current_logger = current_app.logger if has_app_context() else logger
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized for this patient's record.", "danger"); return redirect(url_for('.patients_list'))

    patient_details_full = get_patient_full_details(patient_id) # Need patient_id for form actions
    if not patient_details_full or not patient_details_full.get("user_info"):
        flash("Patient record not found or incomplete.", "warning"); return redirect(url_for('.patients_list'))

    diagnosis_types_enum, diagnosis_severities_enum, symptom_frequencies_enum = [], [], []
    symptoms_catalog_list, vaccines_list = [], []
    try:
        diagnosis_types_enum = get_enum_values('diagnoses', 'diagnosis_type')
        diagnosis_severities_enum = get_enum_values('diagnoses', 'severity')
        symptom_frequencies_enum = get_enum_values('patient_symptoms', 'frequency')
        symptoms_catalog_list = get_all_simple(table_name='symptoms', id_column_name='symptom_id', name_column_expression='symptom_name', order_by='symptom_name')
        vaccines_list = get_all_simple(table_name='vaccines', id_column_name='vaccine_id', name_column_expression="CONCAT(vaccine_name, IFNULL(CONCAT(' (', abbreviation, ')'), ''))", order_by='vaccine_name', where_clause='is_active = TRUE')
    except Exception as e:
        current_logger.error(f"Error fetching form dropdown data for P_Profile AddEntry (P:{patient_id}): {e}", exc_info=True)
        flash("Error loading form options.", "warning")
        # Still render the page but some dropdowns might be empty
        
    return render_template(
        'Doctor_Portal/Patients/patient_profile_add_entry.html',
        patient=patient_details_full, # Pass patient_details_full to access user_info.user_id for form actions
        current_section='addentry',
        patient_id=patient_id,
        diagnosis_types=diagnosis_types_enum,
        diagnosis_severities=diagnosis_severities_enum,
        symptom_frequencies=symptom_frequencies_enum,
        symptoms_catalog=symptoms_catalog_list,
        vaccines_catalog=vaccines_list,
        today_date=date.today()
    )

# --- Form Submission Handlers (add_diagnosis, add_symptom, add_vaccination) ---
# These remain largely the same but their redirect should point to the relevant new tab route.
@patients_bp.route('/<int:patient_id>/diagnoses', methods=['POST'])
@login_required
def add_diagnosis(patient_id):
    # ... (your existing add_diagnosis logic) ...
    # On success or error, redirect appropriately:
    # Example redirect on error:
    # return redirect(url_for('.view_patient_add_entry_tab', patient_id=patient_id) + '#form-diagnosis-anchor')
    # Example redirect on success:
    # return redirect(url_for('.view_patient_records_tab', patient_id=patient_id) + '#diagnosesAccordionHeader')
    if not check_doctor_authorization(current_user): flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    if not is_doctor_authorized_for_patient(doctor_id, patient_id): flash("Not authorized.", "danger"); return redirect(url_for('.patients_list'))

    conn = None; cursor = None; errors = []
    form = request.form
    try:
        diagnosis_date_str = form.get('diagnosis_date')
        diagnosis_name = form.get('diagnosis_name', '').strip()
        diagnosis_code = form.get('diagnosis_code', '').strip() or None
        diagnosis_type = form.get('diagnosis_type')
        description = form.get('description', '').strip() or None
        notes = form.get('notes', '').strip() or None
        treatment_plan = form.get('treatment_plan', '').strip() or None
        follow_up_required = form.get('follow_up_required') == 'on'
        follow_up_date_str = form.get('follow_up_date', '').strip() or None
        follow_up_type = form.get('follow_up_type', '').strip() or None
        severity = form.get('severity')
        is_chronic = form.get('is_chronic') == 'on'
        is_resolved = form.get('is_resolved') == 'on'
        resolved_date_str = form.get('resolved_date', '').strip() or None

        diagnosis_date = date.fromisoformat(diagnosis_date_str) if diagnosis_date_str else None
        if not diagnosis_date: errors.append("Diagnosis date required.")
        if not diagnosis_name: errors.append("Diagnosis name required.")
        
        valid_diag_types = get_enum_values('diagnoses', 'diagnosis_type') 
        if diagnosis_type not in valid_diag_types: errors.append("Invalid diagnosis type."); diagnosis_type = 'final'
        valid_severities = get_enum_values('diagnoses', 'severity') 
        if severity not in valid_severities: errors.append("Invalid severity."); severity = 'unknown'
        
        follow_up_date = date.fromisoformat(follow_up_date_str) if follow_up_required and follow_up_date_str else None
        if follow_up_required and not follow_up_date: errors.append("Follow-up date required if marked.")
        if follow_up_required and not follow_up_type: errors.append("Follow-up type required if marked.")
        if not follow_up_required: follow_up_date, follow_up_type = None, None
        resolved_date = date.fromisoformat(resolved_date_str) if is_resolved and resolved_date_str else None
        if is_resolved and not resolved_date: errors.append("Resolved date required if marked.")
        if not is_resolved: resolved_date = None

        if errors: flash("Validation Errors: " + "; ".join(errors), "danger")
        else:
            conn = get_db_connection(); cursor = conn.cursor()
            sql = "INSERT INTO diagnoses (patient_id, doctor_id, diagnosis_date, diagnosis_code, diagnosis_name, diagnosis_type, description, notes, treatment_plan, follow_up_required, follow_up_date, follow_up_type, severity, is_chronic, is_resolved, resolved_date, created_by, updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            params = (patient_id, doctor_id, diagnosis_date, diagnosis_code, diagnosis_name, diagnosis_type, description, notes, treatment_plan, follow_up_required, follow_up_date, follow_up_type, severity, is_chronic, is_resolved, resolved_date, doctor_id, doctor_id)
            cursor.execute(sql, params); conn.commit(); flash("Diagnosis added.", "success")
            # Redirect to records tab after successful addition
            return redirect(url_for('.view_patient_records_tab', patient_id=patient_id) + '#diagnosesAccordionHeader') 
    except (mysql.connector.Error, ConnectionError, ValueError) as err: 
        if conn and conn.is_connected() and getattr(conn, 'in_transaction', False): conn.rollback()
        logger.error(f"Error adding dx for P:{patient_id}: {err}", exc_info=True); flash(f"Error adding diagnosis: {str(err)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    # On error, redirect back to the add entry tab, preserving form data is harder without WTForms
    return redirect(url_for('.view_patient_add_entry_tab', patient_id=patient_id) + '#form-diagnosis-anchor') # Add anchor

# --- Other routes (add_symptom, add_vaccination, search_conditions_json, view/download reports) ---
# These will also need their redirects updated if they were previously pointing to view_patient_profile
# For example, after add_symptom:
# return redirect(url_for('.view_patient_records_tab', patient_id=patient_id) + '#symptomsAccordionHeader') 

@patients_bp.route('/<int:patient_id>/symptoms', methods=['POST'])
@login_required
def add_symptom(patient_id):
    # ... (Keep your existing add_symptom logic) ...
    # Update redirect at the end:
    if not check_doctor_authorization(current_user): flash("Access denied.", "warning"); return redirect(url_for('auth.login'))
    doctor_id = get_provider_id(current_user)
    if doctor_id is None: flash("Could not identify provider ID.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    if not is_doctor_authorized_for_patient(doctor_id, patient_id): flash("Not authorized.", "danger"); return redirect(url_for('.patients_list'))

    conn = None; cursor = None; errors = []
    form = request.form
    try:
        symptom_input = form.get('symptom_name_or_id', '').strip()
        symptom_id_hidden = form.get('symptom_id', '').strip()
        reported_date_str = form.get('reported_date')
        onset_date_str = form.get('onset_date', '').strip() or None
        severity = form.get('severity', '').strip() or None
        duration = form.get('duration', '').strip() or None
        frequency = form.get('frequency') or None
        notes = form.get('notes', '').strip() or None

        symptom_id = None
        if symptom_id_hidden and symptom_id_hidden.isdigit(): symptom_id = int(symptom_id_hidden)
        elif symptom_input:
             if symptom_input.isdigit(): symptom_id = int(symptom_input)
             else:
                 temp_conn_symp = get_db_connection(); temp_cursor_symp = temp_conn_symp.cursor()
                 temp_cursor_symp.execute("SELECT symptom_id FROM symptoms WHERE LOWER(symptom_name) = LOWER(%s)", (symptom_input,))
                 result_symp = temp_cursor_symp.fetchone()
                 if result_symp: symptom_id = result_symp[0]
                 else: errors.append(f"Symptom '{symptom_input}' not found.")
                 if temp_cursor_symp: temp_cursor_symp.close()
                 if temp_conn_symp and temp_conn_symp.is_connected(): temp_conn_symp.close()
        else: errors.append("Symptom required.")

        reported_date = date.fromisoformat(reported_date_str) if reported_date_str else None
        if not reported_date: errors.append("Reported date required.")
        onset_date = date.fromisoformat(onset_date_str) if onset_date_str else None
        
        valid_frequencies = get_enum_values('patient_symptoms', 'frequency')
        if frequency and frequency not in valid_frequencies: errors.append("Invalid frequency."); frequency = None

        if errors: flash("Validation Errors: " + "; ".join(errors), "danger")
        else:
            conn = get_db_connection(); cursor = conn.cursor()
            sql = "INSERT INTO patient_symptoms (patient_id, symptom_id, reported_date, onset_date, severity, duration, frequency, notes, reported_by, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())"
            params = (patient_id, symptom_id, reported_date, onset_date, severity, duration, frequency, notes, doctor_id)
            cursor.execute(sql, params); conn.commit(); flash("Symptom recorded.", "success")
            return redirect(url_for('.view_patient_records_tab', patient_id=patient_id) + '#symptomsAccordionHeader')
    except (mysql.connector.Error, ConnectionError, ValueError) as err:
        if conn and conn.is_connected() and getattr(conn, 'in_transaction', False): conn.rollback()
        logger.error(f"Error adding symptom P:{patient_id}: {err}", exc_info=True); flash(f"Error: {str(err)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.view_patient_add_entry_tab', patient_id=patient_id) + '#form-symptom-anchor')


@patients_bp.route('/<int:patient_id>/vaccinations', methods=['POST'])
@login_required
def add_vaccination(patient_id):
    # ... (Keep your existing add_vaccination logic) ...
    # Update redirect at the end:
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if not is_doctor_authorized_for_patient(doctor_id, patient_id): flash("Not authorized.", "danger"); return redirect(url_for('.patients_list'))

    conn = None; cursor = None; errors = []
    form = request.form
    try:
        vaccine_id_str = form.get('vaccine_id')
        admin_date_str = form.get('administration_date')
        dose_number = form.get('dose_number', '').strip() or None
        lot_number = form.get('lot_number', '').strip() or None
        notes = form.get('vaccination_notes', '').strip() or None

        vaccine_id = int(vaccine_id_str) if vaccine_id_str and vaccine_id_str.isdigit() else None
        if not vaccine_id: errors.append("Select a vaccine.")
        admin_date = date.fromisoformat(admin_date_str) if admin_date_str else None
        if not admin_date: errors.append("Administration date required.")
        
        if errors: flash("Validation Errors: " + "; ".join(errors), "danger")
        else:
            conn = get_db_connection(); cursor = conn.cursor()
            sql = "INSERT INTO patient_vaccinations (patient_id, vaccine_id, administration_date, dose_number, lot_number, notes, administered_by_id) VALUES (%s,%s,%s,%s,%s,%s,%s)"
            cursor.execute(sql, (patient_id, vaccine_id, admin_date, dose_number, lot_number, notes, doctor_id))
            conn.commit(); flash("Vaccination recorded.", "success")
            return redirect(url_for('.view_patient_records_tab', patient_id=patient_id) + '#vaccinationsAccordionHeader')
    except (mysql.connector.Error, ConnectionError, ValueError) as err: 
        if conn and conn.is_connected() and getattr(conn, 'in_transaction', False): conn.rollback()
        logger.error(f"DB/Val error adding vaccination P:{patient_id}: {err}", exc_info=True); flash(f"Error: {str(err)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.view_patient_add_entry_tab', patient_id=patient_id) + '#form-vaccination-anchor')

@patients_bp.route('/conditions/search', methods=['GET'])
@login_required
def search_conditions_json():
    # ... (This AJAX route remains the same, it's used by the add_diagnosis form) ...
    if not check_doctor_authorization(current_user): return jsonify({"error": "Access Denied"}), 403
    search_query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)
    current_logger = current_app.logger if has_app_context() else logger
    if not search_query or len(search_query) < 2: return jsonify([])

    conn = None; cursor = None; conditions_list = []
    try:
        conn = get_db_connection(); 
        if not conn: current_logger.error("DB conn failed for condition search."); return jsonify({"error": "DB error"}), 500
        cursor = conn.cursor(dictionary=True)
        search_like, search_prefix_like = f"%{search_query}%", f"{search_query}%"
        query = """
            SELECT condition_id, condition_name, icd_code, description, overview, specialist_type
            FROM conditions WHERE is_active = TRUE AND (condition_name LIKE %s OR icd_code LIKE %s OR description LIKE %s)
            ORDER BY CASE WHEN condition_name LIKE %s THEN 0 WHEN condition_name LIKE %s THEN 1 WHEN icd_code LIKE %s THEN 2 ELSE 3 END, condition_name LIMIT %s """
        cursor.execute(query, (search_like, search_like, search_like, search_prefix_like, search_like, search_prefix_like, limit))
        conditions_list = cursor.fetchall()
    except Exception as e: current_logger.error(f"Error searching conditions JSON: {e}", exc_info=True); return jsonify({"error": "Search error"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return jsonify(conditions_list)