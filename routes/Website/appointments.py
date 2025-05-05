# routes/Website/appointments.py

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, current_app, jsonify # Removed session, make_response unless needed later
)
from flask_login import login_required, current_user
import mysql.connector
from db import get_db_connection
import datetime
# Assuming your helpers are in utils and accessible
# If timedelta_to_time is only used in templates, it might not be needed here
# from utils.template_helpers import format_timedelta_as_time # Filter for templates
from utils.template_helpers import map_status_to_badge_class # May not be needed here directly

# Define the blueprint for PUBLIC FACING appointment actions (patient perspective mostly)
# NOTE: Doctor-specific appointment management might be in the Doctor_Portal blueprint
appointment_bp = Blueprint(
    'appointment', # Keep name simple, prefix distinguishes
    __name__,
    template_folder='../../templates/Website', # Points to templates/Website
    url_prefix='/appointments' # Base URL: /appointments/schedule, /appointments/view, etc.
)

# --- Helper Functions (Can be moved to a utils/appointment_helpers.py later) ---

def get_doctor_details(doctor_id):
    """Fetches basic details for a doctor needed for scheduling form."""
    conn = None; cursor = None; doctor_info = None
    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): raise ConnectionError("DB Connect failed")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name,
                s.name AS specialization_name,
                d.profile_photo_url,
                d.department_id, -- Needed if we want to pre-select department
                dept.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor'
              AND u.account_status = 'active' AND d.verification_status = 'approved'
        """
        cursor.execute(query, (doctor_id,))
        doctor_info = cursor.fetchone()
        # Add default image path if needed
        if doctor_info and not doctor_info.get('profile_photo_url'):
             doctor_info['profile_photo_url'] = 'images/default_doctor.png'
    except Exception as e:
        current_app.logger.error(f"Error fetching doctor details {doctor_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctor_info

def get_available_slots(doctor_id, selected_date_str):
    """
    Fetches available time slots for a doctor on a specific date.
    Returns a list of available start times (as HH:MM strings).
    """
    available_slots = []
    conn = None; cursor = None
    try:
        # Validate date format first
        selected_date_obj = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        # Prevent booking in the past
        if selected_date_obj < datetime.date.today():
            return []

        conn = get_db_connection()
        if not conn or not conn.is_connected(): raise ConnectionError("DB Connect failed")
        cursor = conn.cursor(dictionary=True)

        # Determine MySQL day of week (0=Sunday, 1=Monday...)
        mysql_day_of_week = selected_date_obj.isoweekday() % 7

        # 1. Get regular availability
        avail_query = """
            SELECT start_time, end_time
            FROM doctor_availability
            WHERE doctor_id = %s AND day_of_week = %s AND is_available = TRUE
            ORDER BY start_time
        """
        cursor.execute(avail_query, (doctor_id, mysql_day_of_week))
        regular_schedule = cursor.fetchall()

        # 2. Get overrides for the specific date
        override_query = """
            SELECT start_time, end_time, is_unavailable
            FROM doctor_availability_overrides
            WHERE doctor_id = %s AND override_date = %s
            ORDER BY start_time
        """
        cursor.execute(override_query, (doctor_id, selected_date_str))
        overrides = cursor.fetchall()

        # 3. Get existing *confirmed/scheduled* appointments
        appt_query = """
            SELECT start_time, end_time
            FROM appointments
            WHERE doctor_id = %s AND appointment_date = %s
              AND status IN ('scheduled', 'confirmed', 'rescheduled') -- Active bookings
            ORDER BY start_time
        """
        cursor.execute(appt_query, (doctor_id, selected_date_str))
        booked_slots = cursor.fetchall()

        # --- Calculate available slots ---
        slot_duration = datetime.timedelta(minutes=30) # Assuming 30 min slots - TODO: Make configurable?

        # Check for full day unavailability override
        is_fully_unavailable = any(ovr['is_unavailable'] and ovr['start_time'] is None for ovr in overrides)
        if is_fully_unavailable:
            return [] # Early exit if the whole day is blocked

        # Determine the day's effective schedule (regular vs override)
        effective_schedule = []
        has_available_override = any(not ovr['is_unavailable'] and ovr['start_time'] and ovr['end_time'] for ovr in overrides)

        if has_available_override:
            # Use only explicitly available override periods
            for ovr in overrides:
                if not ovr['is_unavailable'] and ovr['start_time'] and ovr['end_time']:
                    effective_schedule.append({'start_time': ovr['start_time'], 'end_time': ovr['end_time']})
        else:
            # Use regular schedule if no *available* overrides exist (the full day block handled above)
            effective_schedule = regular_schedule

        # Generate potential slots and check conflicts
        for schedule_period in effective_schedule:
            # Ensure start and end times are valid time objects or timedeltas
            if not isinstance(schedule_period['start_time'], (datetime.time, datetime.timedelta)) or \
               not isinstance(schedule_period['end_time'], (datetime.time, datetime.timedelta)):
                 current_app.logger.warning(f"Invalid time format in schedule for doc {doctor_id} on {selected_date_str}: {schedule_period}")
                 continue

            # Convert timedelta to time if necessary for comparison
            start_t = schedule_period['start_time']
            end_t = schedule_period['end_time']
            if isinstance(start_t, datetime.timedelta): start_t = (datetime.datetime.min + start_t).time()
            if isinstance(end_t, datetime.timedelta): end_t = (datetime.datetime.min + end_t).time()

            current_dt = datetime.datetime.combine(selected_date_obj, start_t)
            end_schedule_dt = datetime.datetime.combine(selected_date_obj, end_t)

            while current_dt + slot_duration <= end_schedule_dt:
                slot_start_time_obj = current_dt.time()
                # slot_end_time_obj = (current_dt + slot_duration).time() # Not strictly needed for checks

                # Check 1: Does this slot fall within a specific *unavailable* override period?
                is_overridden_unavailable = False
                for ovr in overrides:
                    if ovr['is_unavailable'] and ovr['start_time'] and ovr['end_time']:
                         ovr_start_t = ovr['start_time']
                         ovr_end_t = ovr['end_time']
                         if isinstance(ovr_start_t, datetime.timedelta): ovr_start_t = (datetime.datetime.min + ovr_start_t).time()
                         if isinstance(ovr_end_t, datetime.timedelta): ovr_end_t = (datetime.datetime.min + ovr_end_t).time()
                         # Check if slot START time falls within the unavailable block
                         if ovr_start_t <= slot_start_time_obj < ovr_end_t:
                              is_overridden_unavailable = True
                              break
                if is_overridden_unavailable:
                    current_dt += slot_duration # Move to next potential slot start
                    continue # Skip this overridden slot

                # Check 2: Does this slot overlap with an existing booked appointment?
                is_booked = False
                for booked in booked_slots:
                    booked_start_t = booked['start_time']
                    booked_end_t = booked['end_time']
                    if isinstance(booked_start_t, datetime.timedelta): booked_start_t = (datetime.datetime.min + booked_start_t).time()
                    if isinstance(booked_end_t, datetime.timedelta): booked_end_t = (datetime.datetime.min + booked_end_t).time()
                    # Check if the potential slot's start time falls within a booked period
                    if booked_start_t <= slot_start_time_obj < booked_end_t:
                        is_booked = True
                        break
                if is_booked:
                    current_dt += slot_duration
                    continue # Skip this booked slot

                # If not overridden and not booked, it's available
                available_slots.append(slot_start_time_obj.strftime('%H:%M'))

                current_dt += slot_duration # Move to next potential slot start

    except ValueError:
        current_app.logger.error(f"Invalid date format for availability check: {selected_date_str}")
        return []
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB Error fetching availability for doc {doctor_id} on {selected_date_str}: {err}")
    except ConnectionError as conn_err:
         current_app.logger.error(f"{conn_err} fetching availability for doc {doctor_id} on {selected_date_str}.")
    except Exception as e:
        current_app.logger.error(f"Error calculating availability for doc {doctor_id} on {selected_date_str}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    current_app.logger.debug(f"Available slots for Doc {doctor_id} on {selected_date_str}: {available_slots}")
    return available_slots
# Add this helper function or import it
def check_daily_limit(doctor_id, location_id, appt_date_obj):
    """Checks if the daily appointment limit for a provider/location/date has been reached."""
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)

        # 1. Find the limit for this specific day/location
        cursor.execute("""
            SELECT max_appointments FROM provider_daily_limits
            WHERE provider_id = %s AND location_id = %s AND limit_date = %s
            """, (doctor_id, location_id, appt_date_obj))
        limit_row = cursor.fetchone()

        if not limit_row:
            return True # No specific limit set, allow booking

        max_allowed = limit_row['max_appointments']
        if max_allowed == 0: # Explicitly blocked
             current_app.logger.info(f"Booking blocked for Doc:{doctor_id} Loc:{location_id} Date:{appt_date_obj} due to max_appointments=0")
             return False

        # 2. Count existing confirmed/scheduled appointments
        cursor.execute("""
            SELECT COUNT(appointment_id) as current_count FROM appointments
            WHERE doctor_id = %s AND location_id = %s AND appointment_date = %s
            AND status IN ('scheduled', 'confirmed', 'rescheduled')
            """, (doctor_id, location_id, appt_date_obj))
        count_row = cursor.fetchone()
        current_count = count_row['current_count'] if count_row else 0

        # 3. Compare
        if current_count >= max_allowed:
             current_app.logger.warning(f"Daily limit reached for Doc:{doctor_id} Loc:{location_id} Date:{appt_date_obj}. Limit={max_allowed}, Current={current_count}")
             return False # Limit reached
        else:
             return True # Limit not reached

    except Exception as e:
        current_app.logger.error(f"Error checking daily limit for Doc:{doctor_id} Loc:{location_id} Date:{appt_date_obj}: {e}")
        return False # Fail closed - block booking if check fails
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def get_appointment_types():
     """ Fetches active appointment types from the database. """
     conn = None; cursor = None; types = []
     try:
         conn = get_db_connection()
         cursor = conn.cursor(dictionary=True)
         query = "SELECT type_name, default_duration_minutes FROM appointment_types WHERE is_active = TRUE ORDER BY type_name"
         cursor.execute(query)
         types = cursor.fetchall()
     except Exception as e:
         current_app.logger.error(f"Error fetching appointment types: {e}", exc_info=True)
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()
     # Return default list if DB fetch fails, or adjust as needed
     return types if types else [
        {'type_name': 'Initial Consultation', 'default_duration_minutes': 60},
        {'type_name': 'Follow-up Visit', 'default_duration_minutes': 30},
        {'type_name': 'Telehealth Consultation', 'default_duration_minutes': 30},
     ] # Example fallback

def create_appointment_record(patient_id, doctor_id, appt_date_str, start_time_str, appt_type_name, reason, location_id=None):
    """Creates a new appointment record in the database."""
    conn = None; cursor = None; new_appointment_id = None
    try:
        # --- Validation and Preparation ---
        # Convert date and time strings
        appt_date_obj = datetime.datetime.strptime(appt_date_str, '%Y-%m-%d').date()
        start_time_obj = datetime.datetime.strptime(start_time_str, '%H:%M').time()

        # TODO: Get default duration based on appt_type_name from appointment_types table
        # For now, assume 30 mins
        duration = datetime.timedelta(minutes=30)
        # Calculate end_time based on duration
        end_time_obj = (datetime.datetime.combine(datetime.date.min, start_time_obj) + duration).time()

        # Check for conflicts again just before inserting (small race condition window exists)
        # This check prevents double booking if slots were taken between page load and submit
        conflict_query = """
            SELECT appointment_id FROM appointments
            WHERE doctor_id = %s AND appointment_date = %s
            AND status NOT IN ('canceled', 'no-show')
            AND (
                (%s >= start_time AND %s < end_time) OR -- New start overlaps existing
                (%s > start_time AND %s <= end_time) OR -- New end overlaps existing
                (start_time >= %s AND end_time <= %s)    -- New slot envelops existing
            ) LIMIT 1
        """
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute(conflict_query, (
            doctor_id, appt_date_obj,
            start_time_obj, start_time_obj, # Check new start
            end_time_obj, end_time_obj,     # Check new end
            start_time_obj, end_time_obj    # Check new envelops old
            ))
        if cursor.fetchone():
             current_app.logger.warning(f"Conflict detected trying to book {appt_date_str} {start_time_str} for Doc {doctor_id}")
             flash("Sorry, that time slot was just booked. Please select another time.", "warning")
             return None # Indicate conflict

        # --- Proceed with Insertion ---
        query = """
            INSERT INTO appointments
            (patient_id, doctor_id, appointment_date, start_time, end_time,
             appointment_type, status, reason, location_id, created_by, updated_by,
             created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        """
        status = 'scheduled'
        # Ensure current_user.id is correctly mapped to the user_id column
        creator_id = getattr(current_user, 'user_id', None) # Safely get user_id
        if creator_id is None: raise ValueError("Could not determine creator ID.")

        # Ensure appt_type_name matches one of the ENUM values in the DB
        # Add validation if needed, or rely on DB constraint
        valid_appt_types = ['initial', 'follow-up', 'consultation', 'urgent', 'routine', 'telehealth', 'nutrition_consult']
        # Basic mapping/validation (adjust as needed)
        db_appt_type = appt_type_name.lower().replace(' ', '_').replace('_consultation','').replace('_visit','')
        if db_appt_type not in valid_appt_types:
            db_appt_type = 'consultation' # Default if mapping fails
            current_app.logger.warning(f"Could not map appointment type '{appt_type_name}' to DB enum, using default.")


        params = (
            patient_id, doctor_id, appt_date_obj, start_time_obj, end_time_obj,
            db_appt_type, status, reason if reason else None, # Ensure NULL if empty
            location_id, # Assuming location_id is passed or None
            creator_id, creator_id # created_by and updated_by
        )
        cursor.execute(query, params)
        conn.commit()
        new_appointment_id = cursor.lastrowid
        current_app.logger.info(f"Appointment {new_appointment_id} created for patient {patient_id} with doctor {doctor_id}.")

    except ValueError as ve:
         current_app.logger.error(f"Data validation error creating appointment: {ve}")
         if conn: conn.rollback() # Rollback if error occurred after connection
         return None
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB Error creating appointment: {err}")
        if conn: conn.rollback()
        # Check for specific errors like FK violations if needed
        return None
    except Exception as e:
        current_app.logger.error(f"Unexpected error creating appointment: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return new_appointment_id


def get_patient_appointments(patient_id):
    """Fetches upcoming and past appointments for a patient."""
    appointments = {'upcoming': [], 'past': []}
    conn = None; cursor = None
    today = datetime.date.today()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                a.appointment_type, a.status, a.reason, a.notes,
                u.first_name AS doctor_first_name, u.last_name AS doctor_last_name,
                dept.name AS department_name, -- Correct alias
                l.name AS location_name
            FROM appointments a
            JOIN users u ON a.doctor_id = u.user_id
            LEFT JOIN doctors doc ON a.doctor_id = doc.user_id
            LEFT JOIN departments dept ON doc.department_id = dept.department_id -- Correct alias
            LEFT JOIN locations l ON a.location_id = l.location_id
            WHERE a.patient_id = %s
            ORDER BY a.appointment_date DESC, a.start_time DESC
        """
        cursor.execute(query, (patient_id,))
        results = cursor.fetchall()

        for appt in results:
             # Format date/time using the Jinja filter function (if needed here)
             appt['display_date'] = appt['appointment_date'].strftime('%b %d, %Y') # Example format
             appt['display_time'] = format_timedelta_as_time(appt['start_time']) # Use helper directly
             appt['doctor_full_name'] = f"Dr. {appt['doctor_first_name']} {appt['doctor_last_name']}"
             # Map status to badge class for template
             appt['status_badge_class'] = map_status_to_badge_class(appt['status'])

             # Classify as upcoming or past
             if appt['appointment_date'] >= today and appt['status'] not in ['completed', 'canceled', 'no-show']:
                 appointments['upcoming'].append(appt)
             else:
                 appointments['past'].append(appt)

        # Sort upcoming ascending (since query is DESC)
        appointments['upcoming'].reverse()

    except Exception as e:
        current_app.logger.error(f"Error fetching appointments for patient {patient_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return appointments

def get_appointment_details(appointment_id, user_id, user_type):
    """Fetches details for a specific appointment, verifying user access."""
    appointment = None; conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                a.*, -- Select all from appointments
                u_pat.first_name AS patient_first_name,
                u_pat.last_name AS patient_last_name,
                u_pat.email AS patient_email, u_pat.phone AS patient_phone,
                u_doc.first_name AS doctor_first_name,
                u_doc.last_name AS doctor_last_name,
                s.name as specialization_name,
                l.name AS location_name, l.address AS location_address
            FROM appointments a
            JOIN users u_pat ON a.patient_id = u_pat.user_id
            JOIN users u_doc ON a.doctor_id = u_doc.user_id
            LEFT JOIN doctors doc ON a.doctor_id = doc.user_id
            LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
            LEFT JOIN locations l ON a.location_id = l.location_id
            WHERE a.appointment_id = %s
        """
        params = [appointment_id]

        # Authorization check
        if user_type == 'patient':
             query += " AND a.patient_id = %s"
             params.append(user_id)
        elif user_type == 'doctor':
             query += " AND a.doctor_id = %s"
             params.append(user_id)
        elif user_type == 'admin':
             pass # Admins can view any appointment (no extra WHERE clause)
        else:
             current_app.logger.warning(f"Unauthorized attempt to view appointment {appointment_id} by user {user_id} with type {user_type}")
             return None # Invalid user type for this check

        cursor.execute(query, tuple(params))
        appointment = cursor.fetchone()

        if appointment:
             # Format for display
            appointment['display_date'] = appointment['appointment_date'].strftime('%A, %B %d, %Y')
            appointment['display_start_time'] = format_timedelta_as_time(appointment['start_time'])
            appointment['display_end_time'] = format_timedelta_as_time(appointment['end_time'])
            appointment['doctor_full_name'] = f"Dr. {appointment['doctor_first_name']} {appointment['doctor_last_name']}"
            appointment['patient_full_name'] = f"{appointment['patient_first_name']} {appointment['patient_last_name']}"
            appointment['status_badge_class'] = map_status_to_badge_class(appointment['status'])

    except Exception as e:
        current_app.logger.error(f"Error fetching appointment details {appointment_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return appointment

def update_appointment_status(appointment_id, new_status, user_id, user_type, reason=None, is_reschedule=False):
    """Updates the status of an appointment, adding followup if needed."""
    conn = None; cursor = None; success = False
    try:
        conn = get_db_connection()
        conn.start_transaction() # Use transaction
        cursor = conn.cursor()

        # Build the SET clause
        set_clauses = ["status = %s", "updated_by = %s", "updated_at = NOW()"]
        params = [new_status, user_id]
        change_note = f"\nStatus changed to {new_status} by user {user_id} ({user_type})"
        if reason: change_note += f". Reason: {reason}"
        set_clauses.append("notes = CONCAT(COALESCE(notes, ''), %s)")
        params.append(change_note)
        if is_reschedule: set_clauses.append("reschedule_count = reschedule_count + 1")
        set_sql = ", ".join(set_clauses)

        # Build the WHERE clause for authorization
        where_sql = "WHERE appointment_id = %s"
        params.append(appointment_id)
        if user_type == 'patient':
             where_sql += " AND patient_id = %s"
             params.append(user_id)
        elif user_type == 'doctor':
             where_sql += " AND doctor_id = %s"
             params.append(user_id)
        elif user_type != 'admin': # If not admin, fail
            current_app.logger.error(f"Invalid user type '{user_type}' attempted status update on appt {appointment_id}.")
            conn.rollback()
            return False

        # Prevent updating already completed/canceled appointments unless admin?
        # Add condition: AND status NOT IN ('completed', 'canceled', 'no-show') ?

        query = f"UPDATE appointments SET {set_sql} {where_sql}"
        cursor.execute(query, tuple(params))

        if cursor.rowcount > 0:
            success = True
            current_app.logger.info(f"Appointment {appointment_id} status updated to {new_status} by user {user_id}.")

            # Add followup record for cancellations/no-shows
            if new_status in ['canceled', 'no-show']:
                 followup_query = """
                     INSERT INTO appointment_followups (appointment_id, followup_status, notes, updated_by, created_at, updated_at)
                     VALUES (%s, 'pending', %s, %s, NOW(), NOW())
                     ON DUPLICATE KEY UPDATE
                        followup_status = IF(followup_status != 'resolved' AND followup_status != 'ignored', VALUES(followup_status), followup_status), -- Don't overwrite resolved/ignored
                        notes = CONCAT(COALESCE(notes, ''), '\n', VALUES(notes)),
                        updated_at = NOW(),
                        updated_by = VALUES(updated_by)
                 """
                 followup_notes = f"Appointment marked as {new_status} on {datetime.date.today()}."
                 cursor.execute(followup_query, (appointment_id, followup_notes, user_id))
                 current_app.logger.info(f"Follow-up record created/updated for appointment {appointment_id} due to status {new_status}.")

            conn.commit()
            # TODO: Send notifications?
        else:
            current_app.logger.warning(f"Failed to update status for appointment {appointment_id}. No rows affected (permission issue or already updated?). User: {user_id}")
            conn.rollback() # Rollback if no rows were updated

    except Exception as e:
        current_app.logger.error(f"Error updating appointment {appointment_id} status: {e}", exc_info=True)
        if conn: conn.rollback()
        success = False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return success


# --- Public Facing Routes ---

# Removed '/schedule' route - scheduling starts from doctor list or similar

# Route for Step 2: Selecting Date/Time/Reason for a specific doctor
@appointment_bp.route('/schedule/doctor/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
# @roles_required('patient') # Use decorator if available
def schedule_appointment_datetime(doctor_id):
    # Manual Role Check
    if getattr(current_user, 'user_type', None) != 'patient':
         flash("Only patients can schedule appointments this way.", "warning")
         return redirect(url_for('home.index')) # Redirect non-patients

    doctor = get_doctor_details(doctor_id)
    if not doctor:
        flash('Selected doctor not found or is unavailable.', 'danger')
        return redirect(url_for('doctor.list_doctors')) # Redirect to doctor list

    appointment_types_list = get_appointment_types() # Fetch types for dropdown

    if request.method == 'POST':
        selected_date = request.form.get('appointment_date')
        selected_time = request.form.get('appointment_time') # Expecting HH:MM
        appointment_type = request.form.get('appointment_type')
        reason = request.form.get('reason', '').strip()
        patient_phone = request.form.get('patient_phone') # Get phone if asked on form

        # --- Basic Validation ---
        errors = []
        if not selected_date: errors.append("Please select a date.")
        if not selected_time: errors.append("Please select an available time.")
        if not appointment_type: errors.append("Please select an appointment type.")
        if not patient_phone: errors.append("Please provide your phone number.") # Example validation

        # Date/Time validation (e.g., prevent booking in past)
        try:
            appt_dt_str = f"{selected_date} {selected_time}"
            appt_dt = datetime.datetime.strptime(appt_dt_str, '%Y-%m-%d %H:%M')
            if appt_dt < datetime.datetime.now():
                 errors.append("Cannot schedule appointments in the past.")
        except ValueError:
             if selected_date and selected_time: # Only error if both were provided but invalid format
                 errors.append("Invalid date or time format selected.")

        if errors:
             for error in errors: flash(error, 'warning')
             # Re-render form with errors and previous selections
             return render_template(
                'appointment_form.html', # Ensure template name is correct
                doctor=doctor,
                appointment_types=appointment_types_list,
                step=2, # Indicate step
                selected_date=selected_date,
                selected_appointment_type=appointment_type,
                reason_value=reason,
                phone_value=patient_phone # Pass back phone too
             )

        # --- Backend Slot Availability Check ---
        available_now = get_available_slots(doctor_id, selected_date)
        if selected_time not in available_now:
             flash(f'Sorry, the time slot {format_timedelta_as_time(selected_time)} is no longer available for {selected_date}. Please choose another.', 'danger')
             return render_template(
                'appointment_form.html', # Re-render form
                doctor=doctor,
                appointment_types=appointment_types_list,
                step=2,
                selected_date=selected_date,
                selected_appointment_type=appointment_type,
                reason_value=reason,
                phone_value=patient_phone
             )

        # --- Optional: Update Patient's Phone if provided and different ---
        if patient_phone and getattr(current_user, 'phone', None) != patient_phone:
             # Update user's phone number in DB (implement update_user_phone function)
             # update_user_phone(current_user.id, patient_phone)
             current_app.logger.info(f"User {current_user.id} updated phone number via appointment form.")
             # Update the current_user object if possible, or re-fetch user data

        # --- Create Appointment ---
        patient_id = current_user.id # Get patient's ID from logged-in user
        new_appt_id = create_appointment_record(
            patient_id, doctor_id, selected_date, selected_time,
            appointment_type, reason
        )

        if new_appt_id:
            flash('Appointment scheduled successfully!', 'success')
            # TODO: Send confirmation notification (email, SMS?)
            return redirect(url_for('.view_appointment_detail', appointment_id=new_appt_id)) # Redirect to detail view
        else:
            # Error already logged in create_appointment_record
            flash('Failed to schedule appointment due to a conflict or database error. Please try again.', 'danger')
            # Re-render form
            return render_template(
                'appointment_form.html',
                doctor=doctor,
                appointment_types=appointment_types_list,
                step=2,
                selected_date=selected_date,
                selected_appointment_type=appointment_type,
                reason_value=reason,
                phone_value=patient_phone
            )

    # GET Request: Show the form for date/time selection
    today_date_str = datetime.date.today().isoformat()
    return render_template(
        'appointment_form.html', # Ensure template name is correct
        doctor=doctor,
        appointment_types=appointment_types_list,
        step=2, # Indicate it's step 2
        today_date=today_date_str # Pass today's date for min attribute in date picker
    )


# AJAX Endpoint for fetching doctor availability
@appointment_bp.route('/availability/<int:doctor_id>/<string:date_str>')
@login_required # Protect this endpoint
def get_doctor_availability_json(doctor_id, date_str):
    """ AJAX endpoint to fetch available slots. """
    try:
        datetime.datetime.strptime(date_str, '%Y-%m-%d') # Basic format validation
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

    # Add permission check if needed (e.g., only patients can check?)
    # if getattr(current_user, 'user_type', None) != 'patient':
    #     return jsonify({'error': 'Access denied'}), 403

    slots = get_available_slots(doctor_id, date_str)
    return jsonify({'available_slots': slots})


# View List of User's Appointments
@appointment_bp.route('/')
@login_required
# @roles_required('patient', 'doctor') # Allow both, logic below differentiates
def view_my_appointments():
    """Displays a list of upcoming and past appointments for the logged-in user."""
    user_id = current_user.id
    user_type = getattr(current_user, 'user_type', None)
    appointments = {'upcoming': [], 'past': []}
    view_title = "My Appointments"

    if user_type == 'patient':
        appointments = get_patient_appointments(user_id)
        view_title = "My Appointments"
    elif user_type == 'doctor':
        # TODO: Implement get_doctor_appointments(doctor_id) function
        # appointments = get_doctor_appointments(user_id)
        flash("Doctor appointment view not fully implemented yet.", 'info')
        view_title = "Your Schedule"
    else:
         flash("Invalid user type for viewing appointments.", "warning")
         return redirect(url_for('home.index')) # Or login page


    return render_template('my_appointments.html', # Ensure template exists
                           upcoming_appointments=appointments.get('upcoming', []),
                           past_appointments=appointments.get('past', []),
                           view_title=view_title)


# View Details of a Specific Appointment
@appointment_bp.route('/<int:appointment_id>')
@login_required
# Role check done inside function
def view_appointment_detail(appointment_id):
    """Displays details for a specific appointment."""
    user_id = current_user.id
    user_type = getattr(current_user, 'user_type', None)

    appointment = get_appointment_details(appointment_id, user_id, user_type)

    if not appointment:
        flash('Appointment not found or you do not have permission to view it.', 'danger')
        # Redirect back to list view or home
        if user_type == 'patient' or user_type == 'doctor':
             return redirect(url_for('.view_my_appointments'))
        else: # e.g. admin trying to view non-existent
             return redirect(url_for('home.index')) # Or admin dashboard

    # Render a detail template (e.g., appointment_detail.html)
    return render_template('appointment_detail.html', appointment=appointment)


# Cancel Appointment (POST request)
@appointment_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
# Role check done inside function
def cancel_appointment(appointment_id):
    """Handles the cancellation of an appointment."""
    user_id = current_user.id
    user_type = getattr(current_user, 'user_type', None)

    # Basic check - allow patient, doctor, admin
    if user_type not in ['patient', 'doctor', 'admin']:
         flash("You do not have permission to cancel appointments.", "warning")
         return redirect(url_for('home.index')) # Or relevant dashboard

    # Fetch details first to check current status and verify ownership if not admin
    # No need to pass user_id/type here if update_appointment_status does the check
    # appointment = get_appointment_details(appointment_id, user_id, user_type)
    # if not appointment:
    #      flash('Appointment not found or permission denied.', 'danger')
    #      return redirect(url_for('.view_my_appointments'))

    # Add check for status if needed (e.g., prevent cancelling 'completed')
    # if appointment['status'] in ['completed', 'canceled', 'no-show']:
    #     flash(f'Cannot cancel appointment with status: {appointment["status"]}.', 'warning')
    #     return redirect(request.referrer or url_for('.view_my_appointments'))

    reason = request.form.get('cancellation_reason', f'Cancelled by {user_type}.')

    success = update_appointment_status(appointment_id, 'canceled', user_id, user_type, reason)

    if success:
        flash('Appointment cancelled successfully.', 'success')
        # TODO: Send cancellation notification
    else:
        flash('Failed to cancel appointment. It might have been already cancelled or modified.', 'danger')

    # Redirect back to where the user came from or the list view
    return redirect(request.referrer or url_for('.view_my_appointments'))


# Reschedule Appointment (Initiation Step)
@appointment_bp.route('/<int:appointment_id>/reschedule', methods=['GET']) # Changed to GET for initiation
@login_required
# @roles_required('patient') # Usually patient initiates
def reschedule_appointment_start(appointment_id):
    """Initiates the reschedule process by marking old and redirecting."""
    user_id = current_user.id
    user_type = getattr(current_user, 'user_type', None)
    if user_type != 'patient': # Only patients can reschedule this way
        flash("Only patients can reschedule appointments.", "warning")
        # Redirect doctors/admins appropriately
        return redirect(url_for('home.index'))

    # Get original appointment to find doctor and check status
    original_appointment = get_appointment_details(appointment_id, user_id, user_type)
    if not original_appointment:
        flash('Appointment not found or permission denied.', 'danger')
        return redirect(url_for('.view_my_appointments'))

    # Prevent rescheduling completed/cancelled etc.
    if original_appointment['status'] not in ['scheduled', 'confirmed']:
         flash(f'Cannot reschedule appointment with status: {original_appointment["status"]}. Please schedule a new one if needed.', 'warning')
         return redirect(url_for('.view_my_appointments'))

    # Mark the original as 'rescheduled'
    reason = "Patient initiated reschedule."
    success = update_appointment_status(appointment_id, 'rescheduled', user_id, user_type, reason, is_reschedule=True)

    if success:
        flash('Original appointment marked for reschedule. Please select a new date and time below.', 'info')
        # Redirect to the datetime selection step for the *same doctor*
        # Pass original appt ID if needed later (e.g., for audit or linking)
        return redirect(url_for('.schedule_appointment_datetime', doctor_id=original_appointment['doctor_id'])) # , original_appt_id=appointment_id ?
    else:
        flash('Failed to initiate reschedule process. Please try cancelling and rebooking.', 'danger')
        return redirect(url_for('.view_my_appointments'))


# Convenience route to start scheduling with a specific doctor
@appointment_bp.route('/schedule-with/<int:doctor_id>')
@login_required
# @roles_required('patient') # Use decorator if available
def schedule_with_doc(doctor_id):
    """Entry point for scheduling from a doctor's profile/listing."""
    if getattr(current_user, 'user_type', None) != 'patient':
        flash("Please log in as a patient to schedule an appointment.", "warning")
        # Maybe redirect to doctor list or login?
        return redirect(url_for('doctor.list_doctors') or url_for('home.index'))

    # Redirects to the main scheduling step for this doctor
    return redirect(url_for('.schedule_appointment_datetime', doctor_id=doctor_id))