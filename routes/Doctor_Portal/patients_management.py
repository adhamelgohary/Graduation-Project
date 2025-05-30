# routes/Doctor_Portal/patients_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, has_app_context
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, timedelta
import math # For calculating age
import logging

# Configure logger
logger = logging.getLogger(__name__)

# --- Attempt to import REAL functions from utils ---
try:
    from .utils import (
        check_doctor_authorization,
        is_doctor_authorized_for_patient, # Use the one from utils
        get_provider_id,
        get_enum_values,                 # For dynamic dropdowns/validations
        get_all_simple,                  # For lookup lists like symptoms
        calculate_age,
        # Import others if needed (allowed_file, generate_secure_filename, etc.)
    )
    # Check if get_all_simple was successfully imported
    if 'get_all_simple' not in locals():
         raise ImportError("get_all_simple not found in relative utils import")
    if 'get_enum_values' not in locals():
         raise ImportError("get_enum_values not found in relative utils import")

except (ImportError, ValueError) as e1:
    logger.warning(
        f"Relative import attempt for utils failed: {e1}. Trying non-relative."
    )
    try:
        # Assuming utils.py is in the parent directory or Python path
        from utils import (
            check_doctor_authorization,
            is_doctor_authorized_for_patient,
            get_provider_id,
            get_enum_values,
            get_all_simple,
            calculate_age,
        )
        if 'get_all_simple' not in locals():
             raise ImportError("get_all_simple not found in non-relative utils import")
        if 'get_enum_values' not in locals():
             raise ImportError("get_enum_values not found in non-relative utils import")

    except ImportError as e2:
        logger.error(f"CRITICAL FAILURE: Could not import required functions from utils.py: {e2}", exc_info=True)
        # Define minimal fallbacks ONLY IF ABSOLUTELY NECESSARY for app to start,
        # otherwise let it fail here. These fallbacks will likely break functionality.
        def check_doctor_authorization(user, **kwargs): logger.error("UTILS FALLBACK: check_doctor_authorization"); return False
        def is_doctor_authorized_for_patient(doc_id, pat_id): logger.error("UTILS FALLBACK: is_doctor_authorized_for_patient"); return False
        def get_provider_id(user): logger.error("UTILS FALLBACK: get_provider_id"); return None
        def get_enum_values(t, c): logger.error(f"UTILS FALLBACK: get_enum_values for {t}.{c}"); return []
        def get_all_simple(t, i, n, **kw): logger.error(f"UTILS FALLBACK: get_all_simple for {t}"); return []
        def calculate_age(d): logger.error("UTILS FALLBACK: calculate_age"); return None
        # It's often better to just raise the ImportError here if utils are critical:
        # raise ImportError(f"Critical utils functions failed to import: {e2}")


# --- Blueprint Definition ---
patients_bp = Blueprint(
    'patients',
    __name__,
    url_prefix='/portal/patients', # Updated prefix to match convention
    template_folder='../../templates' # Adjust path as needed
)

# --- Helper Functions ---

def get_patients_for_doctor(doctor_id, search_term=None):
    """Fetches a list of patients associated with the doctor via non-canceled appointments."""
    conn = None
    cursor = None
    patients_list = []
    current_logger = current_app.logger if has_app_context() else logger

    if not doctor_id:
        current_logger.warning("get_patients_for_doctor called without doctor_id.")
        return []
    try:
        conn = get_db_connection()
        if not conn:
            current_logger.error("DB Connection failed in get_patients_for_doctor.")
            return []
        cursor = conn.cursor(dictionary=True)

        # Ensure relationship is based on non-canceled appointments for relevance
        query = """
            SELECT DISTINCT
                u.user_id, u.first_name, u.last_name, u.email, u.phone,
                p.date_of_birth, p.gender
            FROM users u
            JOIN patients p ON u.user_id = p.user_id
            JOIN appointments a ON p.user_id = a.patient_id
            WHERE a.doctor_id = %s
              AND u.user_type = 'patient'
              AND a.status != 'canceled'
        """
        params = [doctor_id]

        if search_term:
            search_like = f"%{search_term}%"
            # Include patient ID in search
            query += """
                AND (u.first_name LIKE %s
                     OR u.last_name LIKE %s
                     OR u.email LIKE %s
                     OR CONCAT(u.first_name, ' ', u.last_name) LIKE %s
                     OR CONCAT(u.last_name, ', ', u.first_name) LIKE %s
                     OR CAST(u.user_id AS CHAR) LIKE %s
                )
            """
            params.extend([search_like, search_like, search_like, search_like, search_like, search_like])

        query += " ORDER BY u.last_name, u.first_name"

        cursor.execute(query, tuple(params))
        patients_list = cursor.fetchall()

        # Calculate age for each patient
        for patient in patients_list:
            patient['age'] = calculate_age(patient.get('date_of_birth'))

    except (mysql.connector.Error, ConnectionError) as err:
        current_logger.error(f"Error fetching patients for doctor {doctor_id}: {err}")
    except Exception as e:
         current_logger.error(f"Unexpected error fetching patients for doctor {doctor_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return patients_list


def get_patient_full_details(patient_id):
    """Fetches comprehensive details for a single patient."""
    conn = None
    cursor = None
    details = { # Initialize structure
        "user_info": None, "patient_info": None, "insurance_info": None,
        "allergies": [], "appointments": [], "diagnoses": [], "symptoms": []
    }
    current_logger = current_app.logger if has_app_context() else logger

    if not patient_id:
        current_logger.warning("get_patient_full_details called with no patient_id.")
        return None
    try:
        conn = get_db_connection()
        if not conn:
            current_logger.error(f"DB Connection failed for get_patient_full_details (Patient ID: {patient_id}).")
            return None
        cursor = conn.cursor(dictionary=True)

        # 1. Get User and Patient Info
        query_user_patient = """
            SELECT u.user_id, u.username, u.email, u.first_name, u.last_name,
                   u.phone, u.country, u.account_status, u.profile_picture,
                   p.date_of_birth, p.gender, p.blood_type, p.height_cm, p.weight_kg,
                   p.insurance_provider_id, p.insurance_policy_number,
                   p.insurance_group_number, p.insurance_expiration,
                   p.marital_status, p.occupation
            FROM users u
            LEFT JOIN patients p ON u.user_id = p.user_id
            WHERE u.user_id = %s AND u.user_type = 'patient'
        """
        cursor.execute(query_user_patient, (patient_id,))
        patient_data = cursor.fetchone()
        if not patient_data:
            current_logger.warning(f"No patient found with user_id {patient_id} or user is not of type 'patient'.")
            return None

        # Separate user and patient specific info for clarity
        details["user_info"] = {
            k: v for k, v in patient_data.items() if k in
            ['user_id', 'username', 'email', 'first_name', 'last_name', 'phone', 'country', 'account_status', 'profile_picture']
        }
        details["patient_info"] = {
            k: v for k, v in patient_data.items() if k in
            ['date_of_birth', 'gender', 'blood_type', 'height_cm', 'weight_kg', 'insurance_provider_id',
             'insurance_policy_number', 'insurance_group_number', 'insurance_expiration', 'marital_status', 'occupation']
        }
        # Ensure patient_info is not None even if no patient record exists (though the initial query prevents this case)
        details["patient_info"] = details["patient_info"] or {}
        details["patient_info"]['age'] = calculate_age(details["patient_info"].get('date_of_birth'))

        # 2. Get Insurance Provider Name
        insurance_provider_id = details["patient_info"].get('insurance_provider_id')
        if insurance_provider_id:
            cursor.execute("SELECT id, provider_name FROM insurance_providers WHERE id = %s", (insurance_provider_id,))
            provider_data = cursor.fetchone()
            details["insurance_info"] = provider_data # Store full provider info if needed later
        else:
             details["insurance_info"] = None

        # 3. Get Allergies
        query_allergies = """
            SELECT al.allergy_id, al.allergy_name, al.allergy_type, pa.severity,
                   pa.reaction_description, pa.diagnosed_date, pa.notes
            FROM patient_allergies pa
            JOIN allergies al ON pa.allergy_id = al.allergy_id
            WHERE pa.patient_id = %s
            ORDER BY al.allergy_name
        """
        cursor.execute(query_allergies, (patient_id,))
        details["allergies"] = cursor.fetchall()

        # 4. Get Appointments History (Using appointment_type_id)
        query_appointments = """
            SELECT a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                   a.status, a.reason, a.appointment_type_id,
                   at.type_name AS appointment_type_name, -- Select type name
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name
            FROM appointments a
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id -- Join appointment_types
            JOIN users d_user ON a.doctor_id = d_user.user_id -- Assuming doctor exists
            WHERE a.patient_id = %s
            ORDER BY a.appointment_date DESC, a.start_time DESC
            LIMIT 50
        """
        cursor.execute(query_appointments, (patient_id,))
        details["appointments"] = cursor.fetchall()
         # Convert timedelta times to strings for easier template use if needed (optional here, could be done in template)
        for appt in details["appointments"]:
            appt['start_time_str'] = str(appt['start_time'])[:5] if isinstance(appt.get('start_time'), timedelta) else None
            appt['end_time_str'] = str(appt['end_time'])[:5] if isinstance(appt.get('end_time'), timedelta) else None


        # 5. Get Diagnoses History
        query_diagnoses = """
            SELECT dx.*, -- Select all columns from diagnoses
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name
            FROM diagnoses dx
            LEFT JOIN users d_user ON dx.doctor_id = d_user.user_id -- Doctor might be NULL
            WHERE dx.patient_id = %s
            ORDER BY dx.diagnosis_date DESC
            LIMIT 50
        """
        cursor.execute(query_diagnoses, (patient_id,))
        details["diagnoses"] = cursor.fetchall()

        # 6. Get Symptoms History
        query_symptoms = """
            SELECT ps.*, s.symptom_name, -- Select all from patient_symptoms and name from symptoms
                   r_user.first_name as reporter_first_name, r_user.last_name as reporter_last_name
            FROM patient_symptoms ps
            JOIN symptoms s ON ps.symptom_id = s.symptom_id
            JOIN users r_user ON ps.reported_by = r_user.user_id
            WHERE ps.patient_id = %s
            ORDER BY ps.reported_date DESC
            LIMIT 100
        """
        cursor.execute(query_symptoms, (patient_id,))
        details["symptoms"] = cursor.fetchall()

    except (mysql.connector.Error, ConnectionError) as err:
        current_logger.error(f"DB error fetching full details for patient {patient_id}: {err}", exc_info=True)
        return None # Indicate failure
    except Exception as e:
        current_logger.error(f"Unexpected error fetching full details for patient {patient_id}: {e}", exc_info=True)
        return None # Indicate failure
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

    # routes/Doctor_Portal/patients_management.py
# ... (other imports) ...

# ... (existing code) ...

@patients_bp.route('/conditions/search', methods=['GET'])
@login_required
def search_conditions_json():
    """
    Provides JSON search results for the conditions table.
    Used via AJAX by the add diagnosis form.
    """
    if not check_doctor_authorization(current_user): # Or a more general logged-in check if appropriate
        return jsonify({"error": "Access Denied"}), 403

    search_query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)
    current_logger = current_app.logger if has_app_context() else logger


    if not search_query or len(search_query) < 2:
        return jsonify([])

    conn = None; cursor = None; conditions_list = []
    try:
        conn = get_db_connection()
        if not conn:
            current_logger.error("DB connection failed for condition search.")
            return jsonify({"error": "Database connection error"}), 500
        cursor = conn.cursor(dictionary=True)
        
        search_like = f"%{search_query}%"
        search_prefix_like = f"{search_query}%"

        # Search condition_name and icd_code
        query = """
            SELECT condition_id, condition_name, icd_code, description, overview, specialist_type
            FROM conditions
            WHERE is_active = TRUE AND (condition_name LIKE %s OR icd_code LIKE %s OR description LIKE %s)
            ORDER BY
                CASE
                    WHEN condition_name LIKE %s THEN 0  -- Exact prefix match in name
                    WHEN condition_name LIKE %s THEN 1  -- Contains in name
                    WHEN icd_code LIKE %s THEN 2        -- Exact prefix match in ICD
                    ELSE 3
                END,
                condition_name
            LIMIT %s
        """
        # Add the query itself as a high-priority match for condition_name and icd_code
        cursor.execute(query, (
            search_like, search_like, search_like,  # General search
            search_prefix_like,                     # Prioritize name prefix
            search_like,                            # Contains in name
            search_prefix_like,                     # Prioritize ICD prefix
            limit
        ))
        conditions_list = cursor.fetchall()

    except mysql.connector.Error as db_err:
        current_logger.error(f"DB error searching conditions (JSON): {db_err}")
        return jsonify({"error": "Database search failed"}), 500
    except Exception as e:
        current_logger.error(f"Error searching conditions (JSON): {e}", exc_info=True)
        return jsonify({"error": "Search error"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return jsonify(conditions_list)

# ... (rest of patients_management.py) ...

# --- Patient Routes ---

@patients_bp.route('/', methods=['GET'])
@login_required
def patients_list():
    """Displays the list of patients associated with the logged-in doctor."""
    if not check_doctor_authorization(current_user):
        flash("Access denied. You must be logged in as a doctor.", "warning")
        # Redirect to login or a relevant dashboard
        return redirect(url_for('auth.login')) # Adjust target as needed

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify your provider ID.", "danger")
         return redirect(url_for('doctor_portal.dashboard')) # Adjust target

    search_term = request.args.get('search', '').strip()
    patients_data = get_patients_for_doctor(doctor_id, search_term)

    return render_template(
        'Doctor_Portal/Patients/patients_list.html',
        patients=patients_data,
        search_term=search_term
    )

# routes/Doctor_Portal/patients_management.py

# ... (other imports and code) ...

@patients_bp.route('/<int:patient_id>', methods=['GET'])
@login_required
def view_patient_profile(patient_id):
    """Displays the comprehensive profile and history for a specific patient."""
    current_logger = current_app.logger if has_app_context() else logger # Define logger at the start

    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify your provider ID.", "danger")
         return redirect(url_for('doctor_portal.dashboard'))

    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("You are not authorized to view this patient's record.", "danger")
         return redirect(url_for('.patients_list'))

    patient_details = get_patient_full_details(patient_id)

    if not patient_details or not patient_details.get("user_info"):
        flash("Patient record not found or is incomplete.", "warning")
        return redirect(url_for('.patients_list'))

    # Initialize lists that will be populated
    diagnosis_types_enum = []
    diagnosis_severities_enum = []
    symptom_frequencies_enum = []
    symptoms_catalog_list = []
    vaccines_list = []
    patient_vaccinations = []
    
    conn = None  # Initialize conn and cursor to None
    cursor = None

    try:
        # Fetch dynamic lists for forms first
        diagnosis_types_enum = get_enum_values('diagnoses', 'diagnosis_type')
        diagnosis_severities_enum = get_enum_values('diagnoses', 'severity')
        symptom_frequencies_enum = get_enum_values('patient_symptoms', 'frequency')
        symptoms_catalog_list = get_all_simple(
            table_name='symptoms',
            id_column_name='symptom_id',
            name_column_expression='symptom_name',
            order_by='symptom_name'
        )
        
        # Now fetch vaccine data using a new connection/cursor block
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("DB Connection failed for vaccine data.")
        cursor = conn.cursor(dictionary=True)

        vaccines_list = get_all_simple( # Assuming get_all_simple handles its own connection or you pass one
            table_name='vaccines',
            id_column_name='vaccine_id',
            name_column_expression="CONCAT(name, IFNULL(CONCAT(' (', abbreviation, ')'), ''))", # Nicer display
            order_by='name',
            where_clause='is_active = TRUE'
        )
        
        # Fetch patient's existing vaccinations
        cursor.execute("""
            SELECT pv.*, v.vaccine_name as vaccine_name, v.abbreviation as vaccine_abbreviation
            FROM patient_vaccinations pv
            JOIN vaccines v ON pv.vaccine_id = v.vaccine_id
            WHERE pv.patient_id = %s
            ORDER BY pv.administration_date DESC
        """, (patient_id,))
        patient_vaccinations = cursor.fetchall()

    except (mysql.connector.Error, ConnectionError) as db_err: # Catch DB specific errors
        current_logger.error(f"Database error fetching dynamic lists/vaccinations for patient profile {patient_id}: {db_err}")
        flash("Error loading some form options or vaccine data due to a database issue.", "warning")
    except Exception as e:
         current_logger.error(f"Error fetching dynamic lists/vaccinations for patient profile {patient_id}: {e}", exc_info=True)
         flash("Error loading some form options or vaccine data. Some features might be unavailable.", "warning")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


    return render_template(
        'Doctor_Portal/Patients/patient_profile.html',
        patient=patient_details,
        diagnosis_types=diagnosis_types_enum,
        diagnosis_severities=diagnosis_severities_enum,
        symptom_frequencies=symptom_frequencies_enum,
        symptoms_catalog=symptoms_catalog_list,
        vaccines_catalog=vaccines_list,
        patient_vaccinations=patient_vaccinations,
        today_date=date.today()
    )

# ... (rest of the file, including add_diagnosis, add_symptom, add_vaccination, search_conditions_json)

@patients_bp.route('/<int:patient_id>/diagnoses', methods=['POST'])
@login_required
def add_diagnosis(patient_id):
    """Adds a new diagnosis record for the patient."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify your provider ID.", "danger")
         return redirect(url_for('doctor_portal.dashboard'))

    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized to add diagnosis for this patient.", "danger")
         return redirect(url_for('.patients_list'))

    conn = None; cursor = None
    try:
        # Get form data
        diagnosis_date_str = request.form.get('diagnosis_date')
        diagnosis_name = request.form.get('diagnosis_name', '').strip()
        diagnosis_code = request.form.get('diagnosis_code', '').strip() or None
        diagnosis_type = request.form.get('diagnosis_type') # Get selected value
        description = request.form.get('description', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        treatment_plan = request.form.get('treatment_plan', '').strip() or None
        follow_up_required = request.form.get('follow_up_required') == 'on'
        follow_up_date_str = request.form.get('follow_up_date', '').strip() or None
        follow_up_type = request.form.get('follow_up_type', '').strip() or None
        severity = request.form.get('severity') # Get selected value
        is_chronic = request.form.get('is_chronic') == 'on'
        is_resolved = request.form.get('is_resolved') == 'on'
        resolved_date_str = request.form.get('resolved_date', '').strip() or None

        # --- Validation ---
        errors = []
        diagnosis_date = None
        if not diagnosis_date_str: errors.append("Diagnosis date is required.")
        else:
            try: diagnosis_date = date.fromisoformat(diagnosis_date_str)
            except ValueError: errors.append("Invalid diagnosis date format.")

        if not diagnosis_name: errors.append("Diagnosis name is required.")

        # Validate ENUM values received from form against fetched ENUMs
        valid_diag_types = get_enum_values('diagnoses', 'diagnosis_type')
        if diagnosis_type not in valid_diag_types:
            errors.append(f"Invalid diagnosis type '{diagnosis_type}'.")
            diagnosis_type = 'final' # Default or handle error

        valid_severities = get_enum_values('diagnoses', 'severity')
        if severity not in valid_severities:
             errors.append(f"Invalid severity value '{severity}'.")
             severity = 'unknown' # Default or handle error

        follow_up_date = None
        if follow_up_required:
            if not follow_up_date_str: errors.append("Follow-up date is required if follow-up is marked.")
            else:
                try: follow_up_date = date.fromisoformat(follow_up_date_str)
                except ValueError: errors.append("Invalid follow-up date format.")
            if not follow_up_type: # Check if type is provided when date is
                errors.append("Follow-up type is required if follow-up is marked.")
        else: # If follow-up not required, ensure related fields are null
            follow_up_date = None
            follow_up_type = None

        resolved_date = None
        if is_resolved:
            if not resolved_date_str: errors.append("Resolved date is required if condition is marked resolved.")
            else:
                 try: resolved_date = date.fromisoformat(resolved_date_str)
                 except ValueError: errors.append("Invalid resolved date format.")
        else: # If not resolved, ensure resolved_date is null
            resolved_date = None

        if errors:
            # Combine errors into a single flash message
            flash("Validation Errors: " + "; ".join(errors), "danger")
            # Redirect back to profile, ideally preserving form data (more complex)
            # For simplicity here, just redirecting. Consider using Flask-WTF for easier form handling.
            return redirect(url_for('.view_patient_profile', patient_id=patient_id) + '#add-entry')

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
            follow_up_date, follow_up_type, severity, is_chronic, is_resolved,
            resolved_date, doctor_id, doctor_id # created_by, updated_by set to the acting doctor
        )
        cursor.execute(sql, params)
        conn.commit()
        flash("Diagnosis added successfully.", "success")

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_logger = current_app.logger if has_app_context() else logger
        current_logger.error(f"DB error adding diagnosis for P:{patient_id} by D:{doctor_id}: {err}", exc_info=True)
        flash("Database error adding diagnosis. Please try again.", "danger")
    except Exception as e: # Catch any other unexpected error
        if conn and conn.is_connected(): conn.rollback()
        current_logger = current_app.logger if has_app_context() else logger
        current_logger.error(f"Unexpected error adding diagnosis P:{patient_id} by D:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while adding the diagnosis.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Redirect back to the profile page, anchoring to the diagnosis section if possible
    # The anchor might need adjustment based on actual element IDs in patient_profile.html
    return redirect(url_for('.view_patient_profile', patient_id=patient_id) + '#headingDiagnoses')


@patients_bp.route('/<int:patient_id>/symptoms', methods=['POST'])
@login_required
def add_symptom(patient_id):
    """Adds a new symptom record for the patient."""
    if not check_doctor_authorization(current_user):
        flash("Access denied.", "warning")
        return redirect(url_for('auth.login'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
         flash("Could not identify your provider ID.", "danger")
         return redirect(url_for('doctor_portal.dashboard'))

    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
         flash("Not authorized to add symptom for this patient.", "danger")
         return redirect(url_for('.patients_list'))

    conn = None; cursor = None
    try:
        # Get form data
        # The form might submit the ID directly if JS sets hidden field,
        # or just the name if user types a new one (handle appropriately)
        symptom_input = request.form.get('symptom_name_or_id', '').strip() # Input field likely contains name or ID
        symptom_id_hidden = request.form.get('symptom_id', '').strip() # Hidden field set by JS

        reported_date_str = request.form.get('reported_date')
        onset_date_str = request.form.get('onset_date', '').strip() or None
        severity = request.form.get('severity', '').strip() or None
        duration = request.form.get('duration', '').strip() or None
        frequency = request.form.get('frequency') or None
        notes = request.form.get('notes', '').strip() or None

        # --- Validation & Symptom ID handling ---
        errors = []
        symptom_id = None

        if symptom_id_hidden and symptom_id_hidden.isdigit():
             symptom_id = int(symptom_id_hidden)
             # Optional: Verify this ID exists in the symptoms table
        elif symptom_input:
             # If no ID was set by JS (maybe user typed a new symptom name)
             # Option 1: Reject - require selection from list
             # Option 2: Try to find ID by name (case-insensitive match?)
             # Option 3: Allow adding *new* symptoms to the master list (requires more logic)

             # Let's go with Option 2 (find by name) for now, case-insensitive.
             temp_conn = get_db_connection()
             temp_cursor = temp_conn.cursor()
             temp_cursor.execute("SELECT symptom_id FROM symptoms WHERE LOWER(symptom_name) = LOWER(%s)", (symptom_input,))
             result = temp_cursor.fetchone()
             if result:
                 symptom_id = result[0]
             else:
                 # If you want to allow adding new symptoms on the fly:
                 # INSERT INTO symptoms (symptom_name, ...) VALUES (%s, ...); symptom_id = LAST_INSERT_ID();
                 # For now, consider it an error if name doesn't match existing and no ID provided
                 errors.append(f"Symptom '{symptom_input}' not found in catalog. Please select from the list or ensure it's added first.")
             if temp_cursor: temp_cursor.close()
             if temp_conn and temp_conn.is_connected(): temp_conn.close()
        else:
            errors.append("Symptom is required.")

        reported_date = None
        if not reported_date_str: errors.append("Reported date is required.")
        else:
            try: reported_date = date.fromisoformat(reported_date_str)
            except ValueError: errors.append("Invalid reported date format.")

        onset_date = None
        if onset_date_str:
            try: onset_date = date.fromisoformat(onset_date_str)
            except ValueError: errors.append("Invalid onset date format.")

        # Validate frequency ENUM
        valid_frequencies = get_enum_values('patient_symptoms', 'frequency')
        if frequency and frequency not in valid_frequencies:
            errors.append(f"Invalid frequency value '{frequency}'.")
            frequency = None # Reset if invalid

        if errors:
            flash("Validation Errors: " + "; ".join(errors), "danger")
            return redirect(url_for('.view_patient_profile', patient_id=patient_id) + '#add-entry')
        # --- End Validation ---

        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        sql = """
            INSERT INTO patient_symptoms (
                patient_id, symptom_id, reported_date, onset_date, severity,
                duration, frequency, notes, reported_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
        """
        params = (
            patient_id, symptom_id, reported_date, onset_date, severity,
            duration, frequency, notes, doctor_id
        )
        cursor.execute(sql, params)
        conn.commit()
        flash("Symptom recorded successfully.", "success")

    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected(): conn.rollback()
        current_logger = current_app.logger if has_app_context() else logger
        current_logger.error(f"DB error adding symptom for P:{patient_id} by D:{doctor_id}: {err}", exc_info=True)
        flash("Database error recording symptom.", "danger")
    except Exception as e: # Catch any other unexpected error
        if conn and conn.is_connected(): conn.rollback()
        current_logger = current_app.logger if has_app_context() else logger
        current_logger.error(f"Unexpected error adding symptom P:{patient_id} by D:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Redirect back to the profile page, anchoring to the symptoms section
    return redirect(url_for('.view_patient_profile', patient_id=patient_id) + '#headingSymptoms')

# routes/Doctor_Portal/patients_management.py

@patients_bp.route('/<int:patient_id>/vaccinations', methods=['POST'])
@login_required
def add_vaccination(patient_id):
    if not check_doctor_authorization(current_user): abort(403)
    doctor_id = get_provider_id(current_user)
    if not is_doctor_authorized_for_patient(doctor_id, patient_id):
        flash("Not authorized to add vaccination for this patient.", "danger")
        return redirect(url_for('.patients_list'))

    conn = None; cursor = None; errors = []
    try:
        vaccine_id_str = request.form.get('vaccine_id')
        admin_date_str = request.form.get('administration_date')
        dose_number = request.form.get('dose_number', '').strip() or None
        lot_number = request.form.get('lot_number', '').strip() or None
        notes = request.form.get('vaccination_notes', '').strip() or None # Use unique name

        vaccine_id = None
        if vaccine_id_str and vaccine_id_str.isdigit():
            vaccine_id = int(vaccine_id_str)
        else:
            errors.append("Please select a vaccine.")

        admin_date = None
        if not admin_date_str:
            errors.append("Administration date is required.")
        else:
            try:
                admin_date = date.fromisoformat(admin_date_str)
            except ValueError:
                errors.append("Invalid administration date format.")
        
        if errors:
            for error in errors: flash(error, 'danger')
        else:
            conn = get_db_connection(); cursor = conn.cursor()
            sql = """INSERT INTO patient_vaccinations
                     (patient_id, vaccine_id, administration_date, dose_number, lot_number, notes, administered_by_id)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql, (patient_id, vaccine_id, admin_date, dose_number, lot_number, notes, doctor_id))
            conn.commit()
            flash("Vaccination recorded successfully.", "success")
    
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB error recording vaccination for P:{patient_id}: {err}", exc_info=True)
        flash("Database error recording vaccination.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error recording vaccination for P:{patient_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.view_patient_profile', patient_id=patient_id) + '#addentry-tab-pane') # Or specific anchor