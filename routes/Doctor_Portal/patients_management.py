# routes/Doctor_Portal/patients_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, timedelta
import math # For calculating age

# Assuming check_doctor_authorization is accessible (import or define)
def check_doctor_authorization(user):
    if not user or not user.is_authenticated: return False
    return getattr(user, 'user_type', None) == 'doctor'

# --- Blueprint Definition ---
patients_bp = Blueprint(
    'patients',
    __name__,
    url_prefix='/doctor/patients', # Base URL for patient routes
    template_folder='../../templates' # Adjust path as needed
)

# --- Helper Functions ---

def calculate_age(born):
    """Calculate age from date of birth."""
    if not born:
        return None
    today = date.today()
    try:
        # Ensure 'born' is a date object
        if isinstance(born, str):
            born_date = date.fromisoformat(born)
        elif isinstance(born, datetime):
            born_date = born.date()
        elif isinstance(born, date):
            born_date = born
        else:
            return None # Invalid type

        # Calculate age
        age = today.year - born_date.year - ((today.month, today.day) < (born_date.month, born_date.day))
        return age
    except (ValueError, TypeError):
        return None

def get_patients_for_doctor(doctor_id, search_term=None):
    """Fetches a list of patients associated with the doctor via appointments."""
    conn = None
    cursor = None
    patients_list = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        # Base query joining users and patients
        query = """
            SELECT DISTINCT
                u.user_id, u.first_name, u.last_name, u.email, u.phone,
                p.date_of_birth, p.gender
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            JOIN appointments a ON p.user_id = a.patient_id
            WHERE a.doctor_id = %s AND u.user_type = 'patient'
        """
        params = [doctor_id]

        # Add search filter if provided
        if search_term:
            search_like = f"%{search_term}%"
            query += """
                AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s OR CAST(u.user_id AS CHAR) LIKE %s)
            """
            params.extend([search_like, search_like, search_like, search_like])

        query += " ORDER BY u.last_name, u.first_name"

        cursor.execute(query, tuple(params))
        patients_list = cursor.fetchall()

        # Calculate age for each patient
        for patient in patients_list:
            patient['age'] = calculate_age(patient.get('date_of_birth'))

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching patients for doctor {doctor_id}: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return patients_list


def is_doctor_authorized_for_patient(doctor_id, patient_id):
    """Checks if the doctor has had at least one appointment with the patient."""
    conn = None
    cursor = None
    authorized = False
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for auth check")
        cursor = conn.cursor()
        query = """
            SELECT 1 FROM appointments
            WHERE doctor_id = %s AND patient_id = %s
            LIMIT 1
        """
        cursor.execute(query, (doctor_id, patient_id))
        authorized = cursor.fetchone() is not None
    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error checking doctor ({doctor_id}) auth for patient ({patient_id}): {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return authorized


def get_patient_full_details(patient_id):
    """Fetches comprehensive details for a single patient."""
    conn = None
    cursor = None
    details = {
        "user_info": None,
        "patient_info": None,
        "insurance_info": None,
        "allergies": [],
        "appointments": [],
        "diagnoses": [],
        "symptoms": []
    }
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        # 1. Get User and Patient Info
        query_user_patient = """
            SELECT u.*, p.*
            FROM users u
            LEFT JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """
        cursor.execute(query_user_patient, (patient_id,))
        patient_data = cursor.fetchone()
        if not patient_data: return None # Patient not found or not a patient type
        details["user_info"] = {k: v for k, v in patient_data.items() if k in ['user_id', 'username', 'email', 'first_name', 'last_name', 'phone', 'country', 'account_status']}
        details["patient_info"] = {k: v for k, v in patient_data.items() if k in ['date_of_birth', 'gender', 'blood_type', 'height_cm', 'weight_kg', 'insurance_provider_id', 'insurance_policy_number', 'insurance_group_number', 'insurance_expiration', 'marital_status', 'occupation']}
        details["patient_info"]['age'] = calculate_age(details["patient_info"].get('date_of_birth'))

        # 2. Get Insurance Provider Name (if ID exists)
        insurance_provider_id = details["patient_info"].get('insurance_provider_id')
        if insurance_provider_id:
            cursor.execute("SELECT provider_name FROM insurance_providers WHERE id = %s", (insurance_provider_id,))
            provider_data = cursor.fetchone()
            details["insurance_info"] = {"provider_name": provider_data['provider_name']} if provider_data else None

        # 3. Get Allergies
        query_allergies = """
            SELECT al.allergy_name, al.allergy_type, pa.severity, pa.reaction_description, pa.diagnosed_date, pa.notes
            FROM patient_allergies pa
            JOIN allergies al ON pa.allergy_id = al.allergy_id
            WHERE pa.patient_id = %s
            ORDER BY al.allergy_name
        """
        cursor.execute(query_allergies, (patient_id,))
        details["allergies"] = cursor.fetchall()

        # 4. Get Appointments History
        query_appointments = """
            SELECT a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                   a.appointment_type, a.status, a.reason,
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name
            FROM appointments a
            JOIN users d_user ON a.doctor_id = d_user.user_id AND d_user.user_type = 'doctor'
            WHERE a.patient_id = %s
            ORDER BY a.appointment_date DESC, a.start_time DESC
            LIMIT 50 -- Limit history for performance
        """
        cursor.execute(query_appointments, (patient_id,))
        details["appointments"] = cursor.fetchall()

        # 5. Get Diagnoses History
        query_diagnoses = """
            SELECT dx.*,
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name
            FROM diagnoses dx
            LEFT JOIN users d_user ON dx.doctor_id = d_user.user_id -- Left join in case doctor_id is NULL
            WHERE dx.patient_id = %s
            ORDER BY dx.diagnosis_date DESC
            LIMIT 50 -- Limit history
        """
        cursor.execute(query_diagnoses, (patient_id,))
        details["diagnoses"] = cursor.fetchall()

        # 6. Get Symptoms History
        query_symptoms = """
            SELECT ps.*, s.symptom_name, s.description as symptom_description,
                   r_user.first_name as reporter_first_name, r_user.last_name as reporter_last_name
            FROM patient_symptoms ps
            JOIN symptoms s ON ps.symptom_id = s.symptom_id
            JOIN users r_user ON ps.reported_by = r_user.user_id
            WHERE ps.patient_id = %s
            ORDER BY ps.reported_date DESC
            LIMIT 100 -- Limit history
        """
        cursor.execute(query_symptoms, (patient_id,))
        details["symptoms"] = cursor.fetchall()

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching full details for patient {patient_id}: {err}")
        return None # Indicate failure
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

# --- Patient Routes ---

@patients_bp.route('/', methods=['GET'])
@login_required
def patients_list():
    """Displays the list of patients associated with the doctor."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login'))

    doctor_id = current_user.id
    search_term = request.args.get('search', '').strip()

    patients = get_patients_for_doctor(doctor_id, search_term)

    return render_template(
        'Doctor_Portal/Patients/patients_list.html',
        patients=patients,
        search_term=search_term
    )


@patients_bp.route('/<int:patient_id>', methods=['GET'])
@login_required
def view_patient_profile(patient_id):
    """Displays the comprehensive profile and history for a specific patient."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login'))

    doctor_id = current_user.id

    # Authorization Check: Ensure this doctor should see this patient
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("You are not authorized to view this patient's record.", "danger")
         return redirect(url_for('patients.patients_list')) # Redirect to patient list

    patient_details = get_patient_full_details(patient_id)

    if not patient_details:
        flash("Patient record not found.", "warning")
        return redirect(url_for('patients.patients_list'))

    # Get diagnosis types for the dropdown
    # TODO: Ideally get this dynamically from DB schema or config
    diagnosis_types = ['preliminary', 'differential', 'final', 'working']
    diagnosis_severities = ['mild', 'moderate', 'severe', 'critical', 'unknown']
    symptom_frequencies = ['constant', 'intermittent', 'occasional', 'rare']

    # TODO: Fetch list of symptoms for dropdown/autocomplete
    symptoms_catalog = [] # Placeholder - fetch from `symptoms` table if needed

    return render_template(
        'Doctor_Portal/Patients/patient_profile.html',
        patient=patient_details, # Contains all nested info
        diagnosis_types=diagnosis_types,
        diagnosis_severities=diagnosis_severities,
        symptom_frequencies=symptom_frequencies,
        symptoms_catalog=symptoms_catalog
    )

@patients_bp.route('/<int:patient_id>/diagnoses', methods=['POST'])
@login_required
def add_diagnosis(patient_id):
    """Adds a new diagnosis record for the patient."""
    if not check_doctor_authorization(current_user): return redirect(url_for('auth.login'))
    doctor_id = current_user.id
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized for this patient.", "danger"); return redirect(url_for('patients.patients_list'))

    conn = None; cursor = None
    try:
        # Get form data
        diagnosis_date_str = request.form.get('diagnosis_date')
        diagnosis_name = request.form.get('diagnosis_name', '').strip()
        diagnosis_code = request.form.get('diagnosis_code', '').strip() or None
        diagnosis_type = request.form.get('diagnosis_type')
        description = request.form.get('description', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        treatment_plan = request.form.get('treatment_plan', '').strip() or None
        follow_up_required = request.form.get('follow_up_required') == 'on'
        follow_up_date_str = request.form.get('follow_up_date', '').strip() or None
        follow_up_type = request.form.get('follow_up_type', '').strip() or None
        severity = request.form.get('severity')
        is_chronic = request.form.get('is_chronic') == 'on'
        is_resolved = request.form.get('is_resolved') == 'on'
        resolved_date_str = request.form.get('resolved_date', '').strip() or None

        # --- Validation ---
        errors = []
        if not diagnosis_date_str: errors.append("Diagnosis date is required.")
        else:
            try: diagnosis_date = date.fromisoformat(diagnosis_date_str)
            except ValueError: errors.append("Invalid diagnosis date format."); diagnosis_date=None
        if not diagnosis_name: errors.append("Diagnosis name is required.")
        # Add more validation for types, severity etc. if using dropdowns
        follow_up_date = None
        if follow_up_required and not follow_up_date_str: errors.append("Follow-up date is required if follow-up is marked.")
        elif follow_up_date_str:
            try: follow_up_date = date.fromisoformat(follow_up_date_str)
            except ValueError: errors.append("Invalid follow-up date format.")
        resolved_date = None
        if is_resolved and not resolved_date_str: errors.append("Resolved date is required if condition is marked resolved.")
        elif resolved_date_str:
             try: resolved_date = date.fromisoformat(resolved_date_str)
             except ValueError: errors.append("Invalid resolved date format.")

        if errors: raise ValueError(", ".join(errors))
        # --- End Validation ---

        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        sql = """
            INSERT INTO diagnoses (
                patient_id, doctor_id, diagnosis_date, diagnosis_code, diagnosis_name,
                diagnosis_type, description, notes, treatment_plan, follow_up_required,
                follow_up_date, follow_up_type, severity, is_chronic, is_resolved,
                resolved_date, created_by, updated_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        params = (
            patient_id, doctor_id, diagnosis_date, diagnosis_code, diagnosis_name,
            diagnosis_type, description, notes, treatment_plan, follow_up_required,
            follow_up_date, follow_up_type if follow_up_required else None, severity, is_chronic, is_resolved,
            resolved_date if is_resolved else None, doctor_id, doctor_id # created_by, updated_by
        )
        cursor.execute(sql, params)
        conn.commit()
        flash("Diagnosis added successfully.", "success")

    except ValueError as ve:
        flash(f"Validation Error: {ve}", "danger")
    except (mysql.connector.Error, ConnectionError) as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error adding diagnosis for patient {patient_id} by doctor {doctor_id}: {err}")
        flash("Database error adding diagnosis.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error adding diagnosis for patient {patient_id} by doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('patients.view_patient_profile', patient_id=patient_id) + '#diagnoses-section') # Redirect back to profile, anchor to section


@patients_bp.route('/<int:patient_id>/symptoms', methods=['POST'])
@login_required
def add_symptom(patient_id):
    """Adds a new symptom record for the patient."""
    if not check_doctor_authorization(current_user): return redirect(url_for('auth.login'))
    doctor_id = current_user.id # Doctor is reporting
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized for this patient.", "danger"); return redirect(url_for('patients.patients_list'))

    conn = None; cursor = None
    try:
        # Get form data
        symptom_id_str = request.form.get('symptom_id') # Assuming dropdown selection
        reported_date_str = request.form.get('reported_date')
        onset_date_str = request.form.get('onset_date', '').strip() or None
        severity = request.form.get('severity', '').strip() or None
        duration = request.form.get('duration', '').strip() or None
        frequency = request.form.get('frequency') or None
        notes = request.form.get('notes', '').strip() or None
        # Add fields for triggers, alleviating_factors, worsening_factors if needed

        # --- Validation ---
        errors = []
        if not symptom_id_str: errors.append("Symptom selection is required.")
        else:
            try: symptom_id = int(symptom_id_str)
            except ValueError: errors.append("Invalid symptom selected."); symptom_id=None
        if not reported_date_str: errors.append("Reported date is required.")
        else:
            try: reported_date = date.fromisoformat(reported_date_str)
            except ValueError: errors.append("Invalid reported date format."); reported_date=None
        onset_date = None
        if onset_date_str:
            try: onset_date = date.fromisoformat(onset_date_str)
            except ValueError: errors.append("Invalid onset date format.")

        if errors: raise ValueError(", ".join(errors))
        # --- End Validation ---

        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        sql = """
            INSERT INTO patient_symptoms (
                patient_id, symptom_id, reported_date, onset_date, severity,
                duration, frequency, notes, reported_by
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        params = (
            patient_id, symptom_id, reported_date, onset_date, severity,
            duration, frequency, notes, doctor_id
        )
        cursor.execute(sql, params)
        conn.commit()
        flash("Symptom recorded successfully.", "success")

    except ValueError as ve:
        flash(f"Validation Error: {ve}", "danger")
    except (mysql.connector.Error, ConnectionError) as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error adding symptom for patient {patient_id} by doctor {doctor_id}: {err}")
        flash("Database error recording symptom.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error adding symptom for patient {patient_id} by doctor {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('patients.view_patient_profile', patient_id=patient_id) + '#symptoms-section') # Redirect back to profile, anchor