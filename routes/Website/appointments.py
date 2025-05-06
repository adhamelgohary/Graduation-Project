# your_project/routes/Website/appointment_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user # current_user.id will be used
from datetime import datetime, date, time, timedelta
import calendar # For day names
import mysql.connector
from db import get_db_connection # Adjust import as per your project structure
from utils.template_helpers import map_status_to_badge_class # Assuming it's in utils/

appointment_bp = Blueprint('appointment', __name__, url_prefix='/appointments', template_folder='../../templates/Website')

# --- Constants for Day of Week Mapping ---
# Python: Monday is 0 and Sunday is 6
# DB Schema: Sunday is 0 and Saturday is 6 (doctor_location_availability.day_of_week)
PYTHON_DOW_MAP = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
DB_DOW_MAP = {0: 'Sunday', 1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
# Helper to convert Python's date.weekday() (Mon=0, Sun=6) to DB's DOW (Sun=0, Sat=6)
def python_dow_to_db_dow(py_dow):
    return (py_dow + 1) % 7

# Helper to convert DB's DOW to Python's date.weekday()
def db_dow_to_python_dow(db_dow):
    # If DB Sun (0) -> Python Sun (6)
    # If DB Mon (1) -> Python Mon (0)
    # ...
    # If DB Sat (6) -> Python Sat (5)
    return (db_dow - 1 + 7) % 7


# --- Helper Functions ---

def get_doctor_details_for_scheduling(doctor_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = """
            SELECT u.user_id, u.first_name, u.last_name, u.profile_picture as profile_photo_url,
                   s.name as specialization_name,
                   COALESCE(dept_direct.name, dept_spec.name) as department_name
            FROM users u
            JOIN doctors doc ON u.user_id = doc.user_id
            LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
            LEFT JOIN departments dept_direct ON doc.department_id = dept_direct.department_id
            LEFT JOIN departments dept_spec ON s.department_id = dept_spec.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_id,))
        doctor = cursor.fetchone()
        return doctor
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_active_appointment_types():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = "SELECT type_id, type_name, default_duration_minutes FROM appointment_types WHERE is_active = TRUE ORDER BY type_name;"
        cursor.execute(query)
        types = cursor.fetchall()
        return types
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_doctor_scheduling_setup(doctor_id):
    conn = None
    cursor = None
    # Initialize with empty set for working days before it's populated
    scheduling_setup = {'locations': [], 'all_unique_working_days_db': set()}
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        current_app.logger.info(f"[SchedulingSetup] Fetching for doctor_id: {doctor_id}") # Log input

        query = """
            SELECT
                dl.doctor_location_id,
                dl.location_name,
                dl.address,
                dl.is_active, -- Select is_active for debugging
                GROUP_CONCAT(DISTINCT dla.day_of_week ORDER BY dla.day_of_week ASC) as working_days_db_str
            FROM doctor_locations dl
            LEFT JOIN doctor_location_availability dla ON dl.doctor_location_id = dla.doctor_location_id
            WHERE dl.doctor_id = %s AND dl.is_active = TRUE  -- Filter for active locations here
            GROUP BY dl.doctor_location_id, dl.location_name, dl.address, dl.is_active
            ORDER BY dl.is_primary DESC, dl.location_name ASC;
        """
        # The WHERE dl.is_active = TRUE was already there in the original query.

        cursor.execute(query, (doctor_id,))
        results = cursor.fetchall()
        current_app.logger.info(f"[SchedulingSetup] Raw DB results for doctor_id {doctor_id}: {results}") # Log raw results

        locations_map = {}
        for row in results:
            loc_id = row['doctor_location_id']
            # No need to check row['is_active'] again here if the SQL query already filters it.
            # But good for logging if you want to see if inactive ones were somehow fetched.
            # current_app.logger.debug(f"[SchedulingSetup] Processing row: {row}")

            if loc_id not in locations_map:
                locations_map[loc_id] = {
                    'location_id': loc_id,
                    'name': row['location_name'],
                    'address': row['address'],
                    'working_days_db': []
                }

            if row['working_days_db_str']: # Only if there are defined working days
                days_db = [int(d) for d in row['working_days_db_str'].split(',')]
                locations_map[loc_id]['working_days_db'].extend(days_db)
                # Removed adding to scheduling_setup['all_unique_working_days_db'] here,
                # will do it after filtering locations.
            # else:
                # current_app.logger.debug(f"[SchedulingSetup] Location {loc_id} has no working_days_db_str.")


        # Filter locations to only include those that ended up with actual working_days_db
        valid_locations_with_days = [
            loc_data for loc_data in locations_map.values() if loc_data['working_days_db']
        ]
        scheduling_setup['locations'] = valid_locations_with_days
        current_app.logger.info(f"[SchedulingSetup] Valid locations with days for Dr {doctor_id}: {valid_locations_with_days}")


        # Recalculate all_unique_working_days_db based on these *valid* filtered locations
        unique_days_set = set()
        for loc_data in valid_locations_with_days:
            unique_days_set.update(loc_data['working_days_db'])
        scheduling_setup['all_unique_working_days_db'] = sorted(list(unique_days_set))
        current_app.logger.info(f"[SchedulingSetup] Final unique working DB DOWs for Dr {doctor_id}: {scheduling_setup['all_unique_working_days_db']}")

        return scheduling_setup
    except Exception as e: # Catch all exceptions for robust logging
        current_app.logger.error(f"[SchedulingSetup] EXCEPTION for doctor_id {doctor_id}: {e}", exc_info=True)
        # Return the initialized empty structure or raise the error depending on desired behavior
        return scheduling_setup # Or: raise e
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def get_upcoming_dates_for_dow(db_day_of_week_target, limit=10):
    if not (0 <= db_day_of_week_target <= 6):
        current_app.logger.warning(f"Invalid db_day_of_week_target: {db_day_of_week_target}")
        return []

    py_dow_target = db_dow_to_python_dow(db_day_of_week_target)
    upcoming_dates = []
    # Start from today
    check_date = date.today()
    
    # Find the first occurrence of the target day of week on or after today
    days_to_add = (py_dow_target - check_date.weekday() + 7) % 7
    current_valid_date = check_date + timedelta(days=days_to_add)

    for _ in range(limit):
        # Ensure we don't add dates if they somehow became past (shouldn't happen with this logic)
        if current_valid_date >= date.today():
            upcoming_dates.append(current_valid_date.strftime('%Y-%m-%d'))
        current_valid_date += timedelta(weeks=1) # Move to the same day next week
        
    return upcoming_dates


def calculate_end_time(start_time_obj, duration_minutes):
    if isinstance(start_time_obj, str):
        try:
            start_time_obj = datetime.strptime(start_time_obj, '%H:%M').time()
        except ValueError: # Handle cases like 'HH:MM:SS' if that's what DB returns for TIME
            start_time_obj = datetime.strptime(start_time_obj, '%H:%M:%S').time()

    start_datetime = datetime.combine(date.min, start_time_obj)
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    return end_datetime.time()

def format_time_for_display(time_obj):
    if isinstance(time_obj, timedelta): # MySQL TIME can come as timedelta
        # Convert timedelta to a time object
        hours, remainder = divmod(time_obj.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        try:
            return time(hours, minutes).strftime('%I:%M %p')
        except ValueError: # handle case like 24:00:00 if it occurs
            return str(time_obj) # fallback
    if isinstance(time_obj, time):
        return time_obj.strftime('%I:%M %p')
    if isinstance(time_obj, str): # If it's already a string like "HH:MM" or "HH:MM:SS"
        try:
            return datetime.strptime(time_obj, '%H:%M:%S').strftime('%I:%M %p')
        except ValueError:
            try:
                return datetime.strptime(time_obj, '%H:%M').strftime('%I:%M %p')
            except ValueError:
                return time_obj # Fallback
    return str(time_obj)

def get_active_appointment_types(): # This function is already suitable
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        # Query includes type_id, type_name, default_duration_minutes
        query = "SELECT type_id, type_name, default_duration_minutes FROM appointment_types WHERE is_active = TRUE ORDER BY type_name;"
        cursor.execute(query)
        types = cursor.fetchall()
        return types
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- For displaying appointment details ---
def get_appointment_details_for_view(appointment_id, user_id, user_type):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                apt.type_name as appointment_type_name, -- <<< FETCH type_name VIA JOIN
                a.status, a.reason, a.notes, a.reschedule_count,
                pat_user.first_name as patient_first_name, pat_user.last_name as patient_last_name,
                pat_user.email as patient_email, pat_user.phone as patient_phone,
                doc_user.user_id as doctor_id, doc_user.first_name as doctor_first_name, doc_user.last_name as doctor_last_name,
                spec.name as specialization_name,
                dl.location_name, dl.address as location_address
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id -- <<< JOIN
            JOIN users pat_user ON a.patient_id = pat_user.user_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            JOIN doctors d ON a.doctor_id = d.user_id
            LEFT JOIN specializations spec ON d.specialization_id = spec.specialization_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            WHERE a.appointment_id = %s
        """
        # ... (rest of the permission logic as before) ...
        if user_type == 'patient': query += " AND a.patient_id = %s"; params = (appointment_id, user_id)
        elif user_type == 'doctor': query += " AND a.doctor_id = %s"; params = (appointment_id, user_id)
        elif user_type == 'admin': params = (appointment_id,)
        else: return None
        cursor.execute(query, params)
        appointment = cursor.fetchone()
        if appointment:
            appointment['display_date'] = appointment['appointment_date'].strftime('%A, %B %d, %Y')
            appointment['display_start_time'] = format_time_for_display(appointment['start_time'])
            appointment['display_end_time'] = format_time_for_display(appointment['end_time'])
            appointment['doctor_full_name'] = f"Dr. {appointment['doctor_first_name']} {appointment['doctor_last_name']}"
            appointment['patient_full_name'] = f"{appointment['patient_first_name']} {appointment['patient_last_name']}"
            appointment['status_badge_class'] = map_status_to_badge_class(appointment['status'])
            # appointment['appointment_type'] is now appointment['appointment_type_name']
        return appointment
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_appointments_for_user(user_id, user_type):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        base_query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.status,
                apt.type_name as appointment_type_name, -- <<< FETCH type_name VIA JOIN
                dl.location_name,
                CASE WHEN %s = 'patient' THEN CONCAT('Dr. ', doc_user.first_name, ' ', doc_user.last_name)
                     WHEN %s = 'doctor' THEN CONCAT(pat_user.first_name, ' ', pat_user.last_name)
                     ELSE 'N/A' END as other_party_name,
                CASE WHEN %s = 'patient' THEN s.name ELSE 'Patient Visit' END as context_info
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id -- <<< JOIN
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            JOIN doctors doc_details ON doc_user.user_id = doc_details.user_id
            LEFT JOIN specializations s ON doc_details.specialization_id = s.specialization_id
            JOIN users pat_user ON a.patient_id = pat_user.user_id
        """
        # ... (rest of the function as before, the display will use appointment_type_name) ...
        if user_type == 'patient': where_clause = "WHERE a.patient_id = %s"; params = (user_type, user_type, user_type, user_id)
        elif user_type == 'doctor': where_clause = "WHERE a.doctor_id = %s"; params = (user_type, user_type, user_type, user_id)
        else: where_clause = ""; params = (user_type, user_type, user_type)
        query = base_query + " " + where_clause + " ORDER BY a.appointment_date DESC, a.start_time DESC"
        cursor.execute(query, params); appointments = cursor.fetchall()
        today_date_obj = date.today()
        for appt in appointments: # appt is a dictionary
            appt['display_date'] = appt['appointment_date'].strftime('%Y-%m-%d')
            appt['display_time'] = format_time_for_display(appt['start_time'])
            appt['status_badge_class'] = map_status_to_badge_class(appt['status'])
            # Use appointment_type_name for display in template
            appt['appointment_type_display'] = appt.get('appointment_type_name', 'N/A')
            if appt['appointment_date'] >= today_date_obj and appt['status'] not in ['completed', 'canceled', 'no-show', 'rescheduled']:
                appt['category'] = 'upcoming'
            else:
                appt['category'] = 'past'
        return appointments
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def generate_time_slots(start_time_obj, end_time_obj, slot_duration_minutes=30):
    # ... (ensure start_time_obj and end_time_obj are actual time objects)
    if isinstance(start_time_obj, timedelta): start_time_obj = (datetime.min + start_time_obj).time()
    if isinstance(end_time_obj, timedelta): end_time_obj = (datetime.min + end_time_obj).time()
    
    slots = []
    current_dt = datetime.combine(date.min, start_time_obj)
    end_dt_limit = datetime.combine(date.min, end_time_obj)
    while current_dt < end_dt_limit:
        potential_end_slot_dt = current_dt + timedelta(minutes=slot_duration_minutes)
        if potential_end_slot_dt <= end_dt_limit:
            slots.append(current_dt.time())
        current_dt += timedelta(minutes=slot_duration_minutes)
    return slots

def get_doctor_available_slots(doctor_id, target_date_str, selected_location_id=None):
    # ... (ensure buffered=True and robust error handling) ...
    conn = None; cursor = None
    try:
        target_date_obj = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        if target_date_obj < date.today():
            return {"error": "Cannot fetch availability for past dates.", "available_slots": []}
    except ValueError:
        return {"error": "Invalid date format."}

    # DB DOW: 0=Sun, 1=Mon, ..., 6=Sat
    # Python DOW: 0=Mon, ..., 6=Sun
    db_day_of_week_for_query = python_dow_to_db_dow(target_date_obj.weekday())

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        all_potential_slots_for_location = [] # Simpler: if location_id is given, we only care about its slots

        # 1. Base availability for the specific location and day
        loc_availability_query = """
            SELECT dla.start_time, dla.end_time
            FROM doctor_location_availability dla
            WHERE dla.doctor_location_id = %s AND dla.day_of_week = %s;
        """
        cursor.execute(loc_availability_query, (selected_location_id, db_day_of_week_for_query))
        base_avail_periods = cursor.fetchall() # Could be multiple rows if doc has split shifts

        slot_interval = 30 # Default slot display interval
        for avail_period in base_avail_periods:
            start_t = avail_period['start_time']
            end_t = avail_period['end_time']
            all_potential_slots_for_location.extend(generate_time_slots(start_t, end_t, slot_interval))
        
        if not all_potential_slots_for_location: # No base availability for this day/location
             return {"available_slots": []}

        # 2. Existing appointments for that doctor, date, and location
        cursor.execute("""
            SELECT start_time, end_time FROM appointments
            WHERE doctor_id = %s AND appointment_date = %s AND doctor_location_id = %s
            AND status NOT IN ('canceled', 'rescheduled', 'no-show')
        """, (doctor_id, target_date_str, selected_location_id))
        booked_slots_info = cursor.fetchall()

        # 3. Overrides for that doctor, date, and (specific or general) location
        cursor.execute("""
            SELECT start_time, end_time, is_unavailable FROM doctor_availability_overrides
            WHERE doctor_id = %s AND override_date = %s
            AND (doctor_location_id = %s OR doctor_location_id IS NULL)
        """, (doctor_id, target_date_str, selected_location_id))
        overrides = cursor.fetchall()

        current_location_slots_set = set(all_potential_slots_for_location)

        # Apply UNAVAILABLE overrides
        for override in overrides:
            if override['is_unavailable']:
                o_start_t = override['start_time']
                o_end_t = override['end_time']
                if o_start_t is None and o_end_t is None: # Whole day override
                    current_location_slots_set.clear(); break
                if o_start_t and o_end_t:
                    if isinstance(o_start_t, timedelta): o_start_t = (datetime.min + o_start_t).time()
                    if isinstance(o_end_t, timedelta): o_end_t = (datetime.min + o_end_t).time()
                    
                    slots_to_remove = {s for s in current_location_slots_set if s >= o_start_t and (datetime.combine(date.min, s) + timedelta(minutes=slot_interval)).time() <= o_end_t}
                    current_location_slots_set.difference_update(slots_to_remove)
        
        if not current_location_slots_set: return {"available_slots": []}

        # Remove booked slots
        for booked in booked_slots_info:
            b_start_t = booked['start_time']
            b_end_t = booked['end_time']
            if isinstance(b_start_t, timedelta): b_start_t = (datetime.min + b_start_t).time()
            if isinstance(b_end_t, timedelta): b_end_t = (datetime.min + b_end_t).time()

            # Remove any slot that would overlap with this booked appointment
            # A slot [slot_start, slot_start + interval) overlaps [b_start, b_end) if:
            # slot_start < b_end AND (slot_start + interval) > b_start
            slots_to_remove = set()
            for slot_start_time in current_location_slots_set:
                slot_end_dt = datetime.combine(date.min, slot_start_time) + timedelta(minutes=slot_interval)
                if slot_start_time < b_end_t and slot_end_dt.time() > b_start_t:
                    slots_to_remove.add(slot_start_time)
            current_location_slots_set.difference_update(slots_to_remove)

        # Apply AVAILABLE overrides (add them)
        for override in overrides:
            if not override['is_unavailable'] and override['start_time'] and override['end_time']:
                o_start_t = override['start_time']
                o_end_t = override['end_time']
                if isinstance(o_start_t, timedelta): o_start_t = (datetime.min + o_start_t).time()
                if isinstance(o_end_t, timedelta): o_end_t = (datetime.min + o_end_t).time()
                current_location_slots_set.update(generate_time_slots(o_start_t, o_end_t, slot_interval))
        
        # 4. Check provider daily limits
        cursor.execute("""
            SELECT max_appointments FROM provider_daily_limits
            WHERE provider_id = %s AND doctor_location_id = %s AND limit_date = %s
        """, (doctor_id, selected_location_id, target_date_str))
        daily_limit_row = cursor.fetchone()
        if daily_limit_row:
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments
                WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s
                AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            """, (doctor_id, selected_location_id, target_date_str))
            current_booking_count = cursor.fetchone()['count']
            if current_booking_count >= daily_limit_row['max_appointments']:
                current_location_slots_set.clear()

        return {"available_slots": [s.strftime('%H:%M') for s in sorted(list(current_location_slots_set))]}

    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# --- Routes ---

@appointment_bp.route('/my-appointments')
@login_required
def view_my_appointments():
    appointments = get_appointments_for_user(current_user.id, current_user.user_type)
    upcoming_appointments = [appt for appt in appointments if appt['category'] == 'upcoming']
    past_appointments = [appt for appt in appointments if appt['category'] == 'past']
    return render_template('Appointments/my_appointments.html',
                           upcoming_appointments=upcoming_appointments,
                           past_appointments=past_appointments,
                           user_type=current_user.user_type)

@appointment_bp.route('/<int:appointment_id>')
@login_required
def view_appointment_detail(appointment_id):
    appointment = get_appointment_details_for_view(appointment_id, current_user.id, current_user.user_type)
    if not appointment:
        flash('Appointment not found or you do not have permission to view it.', 'danger')
        return redirect(url_for('.view_my_appointments'))
    return render_template('Appointments/appointment_detail.html', appointment=appointment)


# In appointments.py

@appointment_bp.route('/schedule/with/<int:doctor_id>', methods=['GET'])
@login_required
def schedule_with_doc(doctor_id):
    if current_user.user_type != 'patient':
        flash("Only patients can schedule appointments.", "danger")
        return redirect(url_for('doctor.list_doctors'))

    doctor = get_doctor_details_for_scheduling(doctor_id)
    if not doctor:
        flash("Doctor not found.", "danger")
        return redirect(url_for('doctor.list_doctors'))

    scheduling_info = get_doctor_scheduling_setup(doctor_id)
    appointment_types = get_active_appointment_types()
    display_days_map = {
        db_dow: DB_DOW_MAP.get(db_dow, f"Day {db_dow}")
        for db_dow in scheduling_info['all_unique_working_days_db']
    }
    
    # Check if we are coming from a reschedule flow
    original_appointment_id = request.args.get('original_appointment_id', type=int)
    is_reschedule = True if original_appointment_id else False
    page_title = "Reschedule Appointment" if is_reschedule else "Schedule Appointment"

    # Use query parameters for pre-filling, these might come from reschedule_appointment_start
    # or from re-rendering after a validation error.
    # The `selected_appointment_type_id` matches the form field name now.
    return render_template(
        'Appointments/appointment_form.html', # Or 'Appointments/reschedule_form.html' if you make a copy
        doctor=doctor,
        scheduling_info=scheduling_info,
        display_days_map=display_days_map,
        appointment_types=appointment_types,
        today_date=date.today().strftime('%Y-%m-%d'),
        phone_value=request.args.get('phone', current_user.phone or ''),
        reason_value=request.args.get('reason', ''), # Pre-fill reason from original appt
        selected_location_id=request.args.get('location_id'), # Pre-fill location
        selected_appointment_type_id=request.args.get('appointment_type_id'), # Pre-fill type ID
        # These are for re-rendering on validation error mainly for this form:
        selected_day_db=request.args.get('day_db'),
        selected_date=request.args.get('date'),
        selected_time=request.args.get('time'),
        # Pass reschedule context to the template
        is_reschedule=is_reschedule,
        original_appointment_id=original_appointment_id,
        page_title=page_title, # Dynamic page title
        errors = request.args.getlist('errors') # If redirecting with errors via query params (less common)
    )
@appointment_bp.route('/dates-for-day/<int:doctor_id>/<int:db_day_of_week>', methods=['GET'])
@login_required
def get_dates_for_day_ajax(doctor_id, db_day_of_week):
    # For future enhancement: you might want to pass location_id here to ensure
    # the doctor works on db_day_of_week AT THAT SPECIFIC location.
    # For now, it just generates dates for that day of the week.
    # location_id = request.args.get('location_id', type=int)

    upcoming_dates = get_upcoming_dates_for_dow(db_day_of_week, limit=12) # Get next 12 valid dates
    if not upcoming_dates:
        return jsonify({'error': 'No upcoming dates found for this day or invalid day specified.'}), 404
    return jsonify({'available_dates': upcoming_dates})


@appointment_bp.route('/availability/<int:doctor_id>/<string:date_str>', methods=['GET'])
@login_required
def get_availability_ajax(doctor_id, date_str):
    selected_location_id = request.args.get('location_id', type=int)
    if not selected_location_id:
        return jsonify({"error": "Location ID is required to fetch time slots.", "available_slots": []}), 400
    
    try:
        target_d = datetime.strptime(date_str, '%Y-%m-%d').date()
        if target_d < date.today():
            return jsonify({"error": "Cannot fetch availability for past dates.", "available_slots": []}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format for fetching availability.", "available_slots": []}), 400

    availability = get_doctor_available_slots(doctor_id, date_str, selected_location_id)
    return jsonify(availability)

# In appointments.py

@appointment_bp.route('/schedule/confirm/<int:doctor_id>', methods=['POST'])
@login_required
def schedule_appointment_datetime(doctor_id):
    if current_user.user_type != 'patient':
        flash("Only patients can schedule appointments.", "danger")
        return redirect(url_for('doctor.list_doctors'))

    form_data = request.form.to_dict()
    app_date_str = form_data.get('appointment_date')
    app_time_str = form_data.get('appointment_time')
    location_id_str = form_data.get('location_id')
    appointment_type_id_str = form_data.get('appointment_type_id')
    patient_phone = form_data.get('patient_phone')
    reason = form_data.get('reason', '').strip()

    # --- CORRECTED PART ---
    original_appointment_id_str = form_data.get('original_appointment_id') # Get as string first
    original_appointment_id_from_form = None
    if original_appointment_id_str:
        try:
            original_appointment_id_from_form = int(original_appointment_id_str)
        except ValueError:
            # Handle error if it's not a valid integer, though less likely from a hidden field
            current_app.logger.warning(f"Invalid original_appointment_id received: {original_appointment_id_str}")
            # Depending on your logic, you might want to add to errors or ignore
    # --- END CORRECTION ---


    errors = []
    location_id = None
    if location_id_str:
        try: location_id = int(location_id_str)
        except ValueError: errors.append("Invalid location selected.")
    else: errors.append("Location is required.")

    appointment_type_id = None
    if appointment_type_id_str:
        try: appointment_type_id = int(appointment_type_id_str)
        except ValueError: errors.append("Invalid appointment type selected.")
    else: errors.append("Appointment type is required.")

    appointment_date_obj = None
    if app_date_str:
        try:
            appointment_date_obj = datetime.strptime(app_date_str, '%Y-%m-%d').date()
            if appointment_date_obj < date.today(): errors.append("Cannot schedule appointments in the past.")
        except ValueError: errors.append("Invalid date format for appointment.")
    else: errors.append("Appointment date is required.")
    
    appointment_time_obj = None
    if app_time_str:
        try: appointment_time_obj = datetime.strptime(app_time_str, '%H:%M').time()
        except ValueError: errors.append("Invalid time format for appointment.")
    else: errors.append("Appointment time is required.")
    
    if not patient_phone: errors.append("Phone number is required.")


    if errors:
        for error_msg in errors: flash(error_msg, 'danger')
        doc_detail = get_doctor_details_for_scheduling(doctor_id)
        sched_info = get_doctor_scheduling_setup(doctor_id)
        disp_days_map = {db_dow: DB_DOW_MAP.get(db_dow) for db_dow in sched_info['all_unique_working_days_db']}
        app_types_list = get_active_appointment_types()
        return render_template('Appointments/appointment_form.html',
                               doctor=doc_detail,
                               scheduling_info=sched_info,
                               display_days_map=disp_days_map,
                               appointment_types=app_types_list,
                               today_date=date.today().strftime('%Y-%m-%d'),
                               selected_location_id=location_id_str,
                               selected_day_db=form_data.get('day_of_week_db'),
                               selected_date=app_date_str,
                               selected_time=app_time_str,
                               selected_appointment_type_id=appointment_type_id_str,
                               phone_value=patient_phone,
                               reason_value=reason,
                               errors=errors,
                               # Pass reschedule context back
                               is_reschedule=True if original_appointment_id_from_form else False,
                               original_appointment_id=original_appointment_id_from_form,
                               page_title="Reschedule Appointment" if original_appointment_id_from_form else "Schedule Appointment"
                               )

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute("SELECT default_duration_minutes FROM appointment_types WHERE type_id = %s AND is_active = TRUE", (appointment_type_id,))
        type_details = cursor.fetchone()
        if not type_details:
            flash("Selected appointment type is invalid or inactive.", "danger")
            # Propagate reschedule context if redirecting
            redirect_args = {'doctor_id': doctor_id, **form_data}
            if original_appointment_id_from_form:
                redirect_args['original_appointment_id'] = original_appointment_id_from_form
            return redirect(url_for('.schedule_with_doc', **redirect_args))


        duration = type_details['default_duration_minutes']
        end_time_obj = calculate_end_time(appointment_time_obj, duration)

        cursor.execute("""
            SELECT appointment_id FROM appointments
            WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s
            AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            AND (start_time < %s AND end_time > %s) 
            LIMIT 1 
        """, (doctor_id, location_id, appointment_date_obj, end_time_obj, appointment_time_obj))
        if cursor.fetchone():
            flash("The selected time slot is no longer available or clashes. Please choose a different time.", "warning")
            redirect_args = {'doctor_id': doctor_id, **form_data}
            if original_appointment_id_from_form:
                redirect_args['original_appointment_id'] = original_appointment_id_from_form
            return redirect(url_for('.schedule_with_doc', **redirect_args))

        cursor.execute("SELECT max_appointments FROM provider_daily_limits WHERE provider_id = %s AND doctor_location_id = %s AND limit_date = %s", (doctor_id, location_id, appointment_date_obj))
        limit_row = cursor.fetchone()
        if limit_row:
            cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s AND status NOT IN ('canceled', 'rescheduled', 'no-show')", (doctor_id, location_id, appointment_date_obj))
            current_booking_count = cursor.fetchone()['count']
            if current_booking_count >= limit_row['max_appointments']:
                flash(f"The doctor's daily limit for this location on {appointment_date_obj.strftime('%B %d, %Y')} has been reached.", "warning")
                redirect_args = {'doctor_id': doctor_id, **form_data}
                if original_appointment_id_from_form:
                    redirect_args['original_appointment_id'] = original_appointment_id_from_form
                return redirect(url_for('.schedule_with_doc', **redirect_args))

        insert_query = """
            INSERT INTO appointments (patient_id, doctor_id, appointment_date, start_time, end_time,
                                      appointment_type_id, status, reason, doctor_location_id, created_by, updated_by, reschedule_count)
            VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s)
        """
        initial_reschedule_count_for_new = 0
        cursor.execute(insert_query, (current_user.id, doctor_id, appointment_date_obj, appointment_time_obj,
                                      end_time_obj, appointment_type_id, reason, location_id,
                                      current_user.id, current_user.id, initial_reschedule_count_for_new))
        new_appointment_id = cursor.lastrowid
        
        if patient_phone and patient_phone != (current_user.phone or ""):
            cursor.execute("UPDATE users SET phone = %s WHERE user_id = %s", (patient_phone, current_user.id))

        conn.commit()

        if original_appointment_id_from_form:
            flash(f"Appointment successfully rescheduled! New Appointment ID: {new_appointment_id}.", "success")
        else:
            flash("Appointment scheduled successfully!", "success")
        
        return redirect(url_for('.view_appointment_detail', appointment_id=new_appointment_id))

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Database error during appointment scheduling for Dr {doctor_id}: {err}")
        flash(f"An error occurred during scheduling: {err}. Please try again.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error during appointment scheduling for Dr {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while scheduling. Please try again.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    # Fallback re-render if an exception occurred
    doc_detail_fb = get_doctor_details_for_scheduling(doctor_id)
    sched_info_fb = get_doctor_scheduling_setup(doctor_id)
    disp_days_map_fb = {db_dow: DB_DOW_MAP.get(db_dow) for db_dow in sched_info_fb['all_unique_working_days_db']}
    app_types_fb = get_active_appointment_types()
    return render_template('Appointments/appointment_form.html',
                           doctor=doc_detail_fb,
                           scheduling_info=sched_info_fb,
                           display_days_map=disp_days_map_fb,
                           appointment_types=app_types_fb,
                           today_date=date.today().strftime('%Y-%m-%d'),
                           selected_location_id=location_id_str,
                           selected_day_db=form_data.get('day_of_week_db'),
                           selected_date=app_date_str,
                           selected_time=app_time_str,
                           selected_appointment_type_id=appointment_type_id_str,
                           phone_value=patient_phone,
                           reason_value=reason,
                           errors=errors if 'errors' in locals() and errors else ["An unexpected error occurred. Please check your selections."],
                           # Pass reschedule context back on fallback
                           is_reschedule=True if original_appointment_id_from_form else False,
                           original_appointment_id=original_appointment_id_from_form,
                           page_title="Reschedule Appointment" if original_appointment_id_from_form else "Schedule Appointment"
                           )

# ... (rest of your appointments.py file: cancel_appointment, etc.) ...
@appointment_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    # ... (ensure buffered=True, use current_user.id) ...
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT appointment_id, patient_id, doctor_id, status FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appointment = cursor.fetchone()
        if not appointment: flash("Appointment not found.", "danger"); return redirect(url_for('.view_my_appointments'))
        can_cancel = False
        if current_user.user_type == 'patient' and appointment['patient_id'] == current_user.id: can_cancel = True
        elif current_user.user_type == 'doctor' and appointment['doctor_id'] == current_user.id: can_cancel = True
        elif current_user.user_type == 'admin': can_cancel = True
        if not can_cancel: flash("You do not have permission to cancel this appointment.", "danger"); return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))
        if appointment['status'] not in ['scheduled', 'confirmed']: flash(f"This appointment cannot be canceled (Status: {appointment['status']}).", "warning"); return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))
        cursor.execute("UPDATE appointments SET status = 'canceled', updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s", (current_user.id, appointment_id))
        conn.commit()
        flash("Appointment canceled successfully.", "success")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        flash(f"Database error: {err}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.view_my_appointments'))

# In appointments.py

@appointment_bp.route('/<int:appointment_id>/reschedule/start', methods=['GET'])
@login_required
def reschedule_appointment_start(appointment_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        # Fetch original appointment details needed for pre-filling the new form
        cursor.execute("""
            SELECT a.appointment_id, a.patient_id, a.doctor_id, a.status,
                   a.doctor_location_id, a.appointment_type_id, a.reason
            FROM appointments a
            WHERE a.appointment_id = %s
        """, (appointment_id,)) # Assuming appointment_type_id is used now
        original_appointment = cursor.fetchone()

        if not original_appointment:
            flash("Appointment not found.", "danger")
            return redirect(url_for('.view_my_appointments'))

        if not (current_user.user_type == 'patient' and original_appointment['patient_id'] == current_user.id):
            flash("You do not have permission to reschedule this appointment.", "danger")
            return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))

        if original_appointment['status'] not in ['scheduled', 'confirmed']:
            flash(f"This appointment cannot be rescheduled (Status: {original_appointment['status']}).", "warning")
            return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))
        
        # Mark original appointment as 'rescheduled'
        cursor.execute("""
            UPDATE appointments SET status = 'rescheduled',
                                 reschedule_count = reschedule_count + 1,
                                 updated_by = %s,
                                 updated_at = CURRENT_TIMESTAMP
            WHERE appointment_id = %s
        """, (current_user.id, appointment_id))
        conn.commit()
        flash("Original appointment marked for reschedule. Please book a new appointment time.", "info")

        # Redirect to the scheduling form, passing original details for pre-filling
        return redirect(url_for('.schedule_with_doc',
                                doctor_id=original_appointment['doctor_id'],
                                original_appointment_id=original_appointment['appointment_id'], # Keep track
                                # Pre-fill suggestions:
                                location_id=original_appointment.get('doctor_location_id'),
                                appointment_type_id=original_appointment.get('appointment_type_id'),
                                reason=original_appointment.get('reason', '')
                                # Note: Date and time are NOT pre-filled as user needs to pick new ones
                                ))
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        flash(f"Database error: {err}", "danger")
        current_app.logger.error(f"DB error in reschedule_appointment_start for appt {appointment_id}: {err}")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error in reschedule_appointment_start for appt {appointment_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id)) # Fallback


@appointment_bp.route('/missed-appointment-followup/<int:appointment_id>', methods=['POST'])
@login_required
def flag_for_followup(appointment_id):
    # ... (ensure buffered=True, use current_user.id) ...
    if current_user.user_type not in ['admin', 'doctor']: return jsonify({"error": "Unauthorized"}), 403
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT status FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appt = cursor.fetchone()
        if not appt or appt['status'] not in ['no-show', 'canceled']: return jsonify({"error": "Appointment not eligible for this type of follow-up"}), 400
        notes = request.form.get('notes', 'Needs follow-up for missed/canceled appointment.')
        cursor.execute("""
            INSERT INTO appointment_followups (appointment_id, followup_status, notes, updated_by)
            VALUES (%s, 'pending', %s, %s)
            ON DUPLICATE KEY UPDATE followup_status='pending', notes=VALUES(notes), updated_by=VALUES(updated_by), updated_at=CURRENT_TIMESTAMP
        """, (appointment_id, notes, current_user.id))
        conn.commit()
        return jsonify({"success": "Appointment flagged for follow-up"}), 200
    except mysql.connector.Error as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()