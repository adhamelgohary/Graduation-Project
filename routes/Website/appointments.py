# your_project/routes/Website/appointment_routes.py
import sys
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, time, timedelta
import calendar
import mysql.connector
import os 
from db import get_db_connection

_project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _project_root_path not in sys.path:
    sys.path.append(_project_root_path)
from utils.template_helpers import map_status_to_badge_class 

appointment_bp = Blueprint('appointment', __name__, url_prefix='/appointments', template_folder='../../templates/Website')

PYTHON_DOW_MAP = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday'}
DB_DOW_MAP = {0: 'Sunday', 1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}

def python_dow_to_db_dow(py_dow):
    return (py_dow + 1) % 7

def db_dow_to_python_dow(db_dow):
    return (db_dow - 1 + 7) % 7

def get_doctor_details_for_scheduling(doctor_id):
    conn = None; cursor = None; doctor_details = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection()
        if not conn:
            getattr(logger, 'error', print)(f"DB Connection failed for get_doctor_details_for_scheduling (Dr ID: {doctor_id})")
            return None
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = """
            SELECT u.user_id, u.first_name, u.last_name, 
                   doc.profile_photo_url as profile_photo_db_path, -- *** CORRECTED: Fetches from doctors.profile_photo_url ***
                   s.name as specialization_name,
                   COALESCE(dept_direct.name, dept_spec.name) as department_name
            FROM users u
            JOIN doctors doc ON u.user_id = doc.user_id -- 'doc' is alias for doctors table
            LEFT JOIN specializations s ON doc.specialization_id = s.specialization_id
            LEFT JOIN departments dept_direct ON doc.department_id = dept_direct.department_id
            LEFT JOIN departments dept_spec ON s.department_id = dept_spec.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_id,))
        doctor_details = cursor.fetchone()

        if doctor_details:
            path_relative_to_static_from_db = doctor_details.get('profile_photo_db_path')
            getattr(logger, 'debug', print)(f"  Doctor {doctor_id} (Scheduling) - profile_photo_db_path: '{path_relative_to_static_from_db}'")
            
            doctor_details['profile_photo_display_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')

            if path_relative_to_static_from_db:
                if current_app and current_app.static_folder:
                    full_abs_path_to_check = os.path.join(current_app.static_folder, path_relative_to_static_from_db)
                    if not os.path.exists(full_abs_path_to_check):
                        getattr(logger, 'warning', print)(f"  Doctor {doctor_id} (Scheduling) - Profile image file NOT FOUND at '{full_abs_path_to_check}' (DB path: '{path_relative_to_static_from_db}'). Using default.")
                    else:
                        doctor_details['profile_photo_display_url'] = url_for('static', filename=path_relative_to_static_from_db)
                        getattr(logger, 'info', print)(f"  Doctor {doctor_id} (Scheduling) - Successfully generated profile_photo_display_url: '{doctor_details['profile_photo_display_url']}' using DB path.")
                else:
                    doctor_details['profile_photo_display_url'] = url_for('static', filename=path_relative_to_static_from_db)
                    getattr(logger, 'info', print)(f"  Doctor {doctor_id} (Scheduling) - Generated profile_photo_display_url (no existence check): '{doctor_details['profile_photo_display_url']}' using DB path.")
            else:
                getattr(logger, 'warning', print)(f"  Doctor {doctor_id} (Scheduling) - No profile picture path in DB. Using default.")
        else:
            getattr(logger, 'warning', print)(f"No doctor details found for doctor_id {doctor_id} in get_doctor_details_for_scheduling.")

        return doctor_details
    except Exception as e:
        getattr(logger, 'error', print)(f"Exception in get_doctor_details_for_scheduling (Dr ID: {doctor_id}): {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_active_appointment_types():
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = "SELECT type_id, type_name, default_duration_minutes FROM appointment_types WHERE is_active = TRUE ORDER BY type_name;"
        cursor.execute(query)
        return cursor.fetchall()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_doctor_scheduling_setup(doctor_id):
    conn = None; cursor = None
    scheduling_setup = {'locations': [], 'all_unique_working_days_db': []} 
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = """
            SELECT
                dl.doctor_location_id, dl.location_name, dl.address,
                GROUP_CONCAT(DISTINCT dla.day_of_week ORDER BY dla.day_of_week ASC SEPARATOR ',') as working_days_db_str
            FROM doctor_locations dl
            LEFT JOIN doctor_location_availability dla ON dl.doctor_location_id = dla.doctor_location_id
            WHERE dl.doctor_id = %s AND dl.is_active = TRUE
            GROUP BY dl.doctor_location_id, dl.location_name, dl.address
            ORDER BY dl.is_primary DESC, dl.location_name ASC;
        """
        cursor.execute(query, (doctor_id,))
        results = cursor.fetchall()
        locations_map = {}
        for row in results:
            loc_id = row['doctor_location_id']
            if loc_id not in locations_map:
                locations_map[loc_id] = {
                    'location_id': loc_id, 'name': row['location_name'],
                    'address': row['address'], 'working_days_db': []
                }
            if row['working_days_db_str']: 
                try:
                    days_db = [int(d.strip()) for d in row['working_days_db_str'].split(',') if d.strip().isdigit()]
                    locations_map[loc_id]['working_days_db'].extend(days_db)
                except ValueError as ve:
                    current_app.logger.error(f"ValueError parsing working_days_db_str '{row['working_days_db_str']}' for loc_id {loc_id}: {ve}")

        valid_locations_with_days = [loc_data for loc_data in locations_map.values() if loc_data['working_days_db']]
        scheduling_setup['locations'] = valid_locations_with_days
        unique_days_set = set()
        for loc_data in valid_locations_with_days:
            unique_days_set.update(loc_data['working_days_db'])
        scheduling_setup['all_unique_working_days_db'] = sorted(list(unique_days_set))
        return scheduling_setup
    except Exception as e:
        current_app.logger.error(f"[SchedulingSetup] EXCEPTION for doctor_id {doctor_id}: {e}", exc_info=True)
        return scheduling_setup 
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def generate_time_slots(start_time_obj, end_time_obj, slot_duration_minutes=30):
    if not isinstance(start_time_obj, time):
        if isinstance(start_time_obj, timedelta): start_time_obj = (datetime.min + start_time_obj).time()
        else: return [] 
    if not isinstance(end_time_obj, time):
        if isinstance(end_time_obj, timedelta): end_time_obj = (datetime.min + end_time_obj).time()
        else: return [] 
    
    slots = []
    current_dt = datetime.combine(date.min, start_time_obj)
    end_dt_limit = datetime.combine(date.min, end_time_obj)
    while current_dt < end_dt_limit:
        potential_end_slot_dt = current_dt + timedelta(minutes=slot_duration_minutes)
        if potential_end_slot_dt <= end_dt_limit:
            slots.append(current_dt.time())
        current_dt += timedelta(minutes=slot_duration_minutes)
    return slots

def calculate_end_time(start_time_obj, duration_minutes):
    if isinstance(start_time_obj, str):
        try: start_time_obj = datetime.strptime(start_time_obj, '%H:%M').time()
        except ValueError: start_time_obj = datetime.strptime(start_time_obj, '%H:%M:%S').time()
    elif not isinstance(start_time_obj, time):
        current_app.logger.error(f"Invalid start_time_obj type for calculate_end_time: {type(start_time_obj)}")
        raise ValueError("Invalid start time type")
        
    start_datetime = datetime.combine(date.min, start_time_obj)
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    return end_datetime.time()

def format_time_for_display(time_obj_or_str):
    if isinstance(time_obj_or_str, timedelta):
        total_seconds = int(time_obj_or_str.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        try: return time(hours % 24, minutes).strftime('%I:%M %p') 
        except ValueError: return str(time_obj_or_str) 
    if isinstance(time_obj_or_str, time):
        return time_obj_or_str.strftime('%I:%M %p')
    if isinstance(time_obj_or_str, str):
        try: return datetime.strptime(time_obj_or_str, '%H:%M:%S').strftime('%I:%M %p')
        except ValueError:
            try: return datetime.strptime(time_obj_or_str, '%H:%M').strftime('%I:%M %p')
            except ValueError: return time_obj_or_str 
    return str(time_obj_or_str)

def get_doctor_available_slots(doctor_id, target_date_str, selected_location_id=None):
    conn = None; cursor = None
    slot_interval = current_app.config.get('APPOINTMENT_SLOT_INTERVAL_MINUTES', 30)

    try:
        target_date_obj = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        if target_date_obj < date.today():
            return {"error": "Cannot fetch availability for past dates.", "available_slots": [], "slot_count": 0}
    except ValueError:
        return {"error": "Invalid date format.", "available_slots": [], "slot_count": 0}

    db_day_of_week_for_query = python_dow_to_db_dow(target_date_obj.weekday())

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        all_potential_slots_for_location = []

        loc_availability_query = """
            SELECT dla.start_time, dla.end_time
            FROM doctor_location_availability dla
            WHERE dla.doctor_location_id = %s AND dla.day_of_week = %s;
        """
        cursor.execute(loc_availability_query, (selected_location_id, db_day_of_week_for_query))
        base_avail_periods = cursor.fetchall()

        for avail_period in base_avail_periods:
            start_t, end_t = avail_period['start_time'], avail_period['end_time']
            if isinstance(start_t, timedelta): start_t = (datetime.min + start_t).time()
            if isinstance(end_t, timedelta): end_t = (datetime.min + end_t).time()
            all_potential_slots_for_location.extend(generate_time_slots(start_t, end_t, slot_interval))
        
        if not all_potential_slots_for_location:
             return {"available_slots": [], "slot_count": 0}

        cursor.execute("""
            SELECT start_time, end_time FROM appointments
            WHERE doctor_id = %s AND appointment_date = %s AND doctor_location_id = %s
            AND status NOT IN ('canceled', 'rescheduled', 'no-show')
        """, (doctor_id, target_date_str, selected_location_id))
        booked_slots_info = cursor.fetchall()

        cursor.execute("""
            SELECT start_time, end_time, is_unavailable FROM doctor_availability_overrides
            WHERE doctor_id = %s AND override_date = %s
            AND (doctor_location_id = %s OR doctor_location_id IS NULL)
        """, (doctor_id, target_date_str, selected_location_id))
        overrides = cursor.fetchall()

        current_location_slots_set = set(all_potential_slots_for_location)

        for override in overrides: 
            if override['is_unavailable']:
                o_start_t, o_end_t = override['start_time'], override['end_time']
                if o_start_t is None and o_end_t is None:
                    current_location_slots_set.clear(); break
                if o_start_t and o_end_t:
                    if isinstance(o_start_t, timedelta): o_start_t = (datetime.min + o_start_t).time()
                    if isinstance(o_end_t, timedelta): o_end_t = (datetime.min + o_end_t).time()
                    slots_to_remove = {s for s in current_location_slots_set if s >= o_start_t and (datetime.combine(date.min, s) + timedelta(minutes=slot_interval)).time() <= o_end_t}
                    current_location_slots_set.difference_update(slots_to_remove)
        
        if not current_location_slots_set: return {"available_slots": [], "slot_count": 0}

        for booked in booked_slots_info: 
            b_start_t, b_end_t = booked['start_time'], booked['end_time']
            if isinstance(b_start_t, timedelta): b_start_t = (datetime.min + b_start_t).time()
            if isinstance(b_end_t, timedelta): b_end_t = (datetime.min + b_end_t).time()
            slots_to_remove = set()
            for slot_start_time in current_location_slots_set:
                slot_end_datetime = datetime.combine(date.min, slot_start_time) + timedelta(minutes=slot_interval)
                if slot_start_time < b_end_t and slot_end_datetime.time() > b_start_t:
                    slots_to_remove.add(slot_start_time)
            current_location_slots_set.difference_update(slots_to_remove)

        for override in overrides: 
            if not override['is_unavailable'] and override['start_time'] and override['end_time']:
                o_start_t, o_end_t = override['start_time'], override['end_time']
                if isinstance(o_start_t, timedelta): o_start_t = (datetime.min + o_start_t).time()
                if isinstance(o_end_t, timedelta): o_end_t = (datetime.min + o_end_t).time()
                current_location_slots_set.update(generate_time_slots(o_start_t, o_end_t, slot_interval))
        
        cursor.execute("""
            SELECT max_appointments FROM doctor_location_daily_caps
            WHERE doctor_id = %s AND doctor_location_id = %s AND day_of_week = %s
        """, (doctor_id, selected_location_id, db_day_of_week_for_query))
        daily_cap_row = cursor.fetchone()
        if daily_cap_row:
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments
                WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s
                AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            """, (doctor_id, selected_location_id, target_date_str))
            current_booking_count = cursor.fetchone()['count']
            if current_booking_count >= daily_cap_row['max_appointments']:
                current_location_slots_set.clear()
        
        final_slots_list = sorted(list(current_location_slots_set))
        return {
            "available_slots": [s.strftime('%H:%M') for s in final_slots_list],
            "slot_count": len(final_slots_list)
        }
    except Exception as e:
        current_app.logger.error(f"Error in get_doctor_available_slots for Dr {doctor_id}, Date {target_date_str}, Loc {selected_location_id}: {e}", exc_info=True)
        return {"error": "Could not retrieve slots.", "available_slots": [], "slot_count": 0}
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_upcoming_dates_for_dow(doctor_id, db_day_of_week_target, selected_location_id, limit=10):
    if not (0 <= db_day_of_week_target <= 6): return []
    if not selected_location_id: return []

    py_dow_target = db_dow_to_python_dow(db_day_of_week_target)
    upcoming_dates_with_status = []
    check_date = date.today()
    days_to_add = (py_dow_target - check_date.weekday() + 7) % 7
    current_valid_date = check_date + timedelta(days=days_to_add)

    for _ in range(limit):
        if current_valid_date >= date.today():
            date_str = current_valid_date.strftime('%Y-%m-%d')
            slot_data = get_doctor_available_slots(doctor_id, date_str, selected_location_id)
            has_slots = slot_data.get("slot_count", 0) > 0
            
            upcoming_dates_with_status.append({
                "date": date_str,
                "has_slots": has_slots,
                "is_today": date_str == date.today().strftime('%Y-%m-%d')
            })
        current_valid_date += timedelta(weeks=1)
    return upcoming_dates_with_status

@appointment_bp.route('/schedule/with/<int:doctor_id>', methods=['GET'])
@login_required
def schedule_with_doc(doctor_id):
    if current_user.user_type != 'patient':
        flash("Only patients can schedule appointments.", "danger")
        return redirect(url_for('doctor.list_doctors', _external=True) if 'doctor.list_doctors' in current_app.view_functions else url_for('website_home.index'))

    doctor = get_doctor_details_for_scheduling(doctor_id) 
    if not doctor:
        flash("Doctor not found.", "danger")
        return redirect(url_for('doctor.list_doctors', _external=True) if 'doctor.list_doctors' in current_app.view_functions else url_for('website_home.index'))

    scheduling_info = get_doctor_scheduling_setup(doctor_id)
    appointment_types = get_active_appointment_types()
    display_days_map = {
        str(db_dow): DB_DOW_MAP.get(db_dow, f"Day {db_dow}") 
        for db_dow in scheduling_info.get('all_unique_working_days_db', [])
    }
    
    original_appointment_id = request.args.get('original_appointment_id', type=int)
    is_reschedule = bool(original_appointment_id)
    page_title = "Reschedule Appointment" if is_reschedule else "Schedule Appointment"

    form_data_from_query = {
        'location_id': request.args.get('location_id'),
        'day_of_week_db': request.args.get('day_db'), 
        'appointment_date': request.args.get('date'),
        'appointment_time': request.args.get('time'),
        'appointment_type_id': request.args.get('appointment_type_id'),
        'patient_phone': request.args.get('phone', current_user.phone or ''),
        'reason': request.args.get('reason', ''),
        'errors': request.args.getlist('errors') 
    }

    return render_template(
        'Website/Appointments/appointment_form.html', 
        doctor=doctor, 
        scheduling_info=scheduling_info,
        display_days_map=display_days_map,
        appointment_types=appointment_types,
        today_date_iso=date.today().isoformat(), 
        is_reschedule=is_reschedule,
        original_appointment_id=original_appointment_id,
        page_title=page_title,
        form_data_initial=form_data_from_query 
    )

@appointment_bp.route('/dates-for-day/<int:doctor_id>/<int:db_day_of_week>', methods=['GET'])
@login_required
def get_dates_for_day_ajax(doctor_id, db_day_of_week):
    selected_location_id = request.args.get('location_id', type=int)
    if not selected_location_id:
        return jsonify({'error': 'Location ID is required to fetch dates.'}), 400

    dates_with_status = get_upcoming_dates_for_dow(doctor_id, db_day_of_week, selected_location_id, limit=12)
    
    if not dates_with_status: 
        if not (0 <= db_day_of_week <= 6):
             return jsonify({'error': 'Invalid day specified.'}), 404
        return jsonify({'error': 'No upcoming dates found for this selection.'}), 404 
    
    return jsonify({'available_dates_with_status': dates_with_status})


@appointment_bp.route('/availability/<int:doctor_id>/<string:date_str>', methods=['GET'])
@login_required
def get_availability_ajax(doctor_id, date_str):
    selected_location_id = request.args.get('location_id', type=int)
    if not selected_location_id:
        return jsonify({"error": "Location ID is required.", "available_slots": [], "slot_count": 0}), 400
    try:
        datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format.", "available_slots": [], "slot_count": 0}), 400

    availability = get_doctor_available_slots(doctor_id, date_str, selected_location_id)
    return jsonify(availability)


@appointment_bp.route('/schedule/confirm/<int:doctor_id>', methods=['POST'])
@login_required
def schedule_appointment_datetime(doctor_id):
    if current_user.user_type != 'patient':
        flash("Only patients can schedule appointments.", "danger")
        return redirect(url_for('doctor.list_doctors', _external=True) if 'doctor.list_doctors' in current_app.view_functions else url_for('website_home.index'))

    form_data = request.form.to_dict()
    app_date_str = form_data.get('appointment_date')
    app_time_str = form_data.get('appointment_time')
    location_id_str = form_data.get('location_id')
    appointment_type_id_str = form_data.get('appointment_type_id')
    patient_phone = form_data.get('patient_phone',"").strip()
    reason = form_data.get('reason', '').strip()
    day_of_week_db_str = form_data.get('day_of_week_db') 

    original_appointment_id_from_form = None
    if form_data.get('original_appointment_id'):
        try:
            original_appointment_id_from_form = int(form_data.get('original_appointment_id'))
        except ValueError:
            current_app.logger.warning(f"Invalid original_appointment_id: {form_data.get('original_appointment_id')}")

    errors = []
    location_id, appointment_type_id = None, None
    appointment_date_obj, appointment_time_obj = None, None

    try: location_id = int(location_id_str) if location_id_str else None
    except ValueError: errors.append("Invalid location selected.")
    if not location_id: errors.append("Location is required.")

    try: appointment_type_id = int(appointment_type_id_str) if appointment_type_id_str else None
    except ValueError: errors.append("Invalid appointment type selected.")
    if not appointment_type_id: errors.append("Appointment type is required.")
    
    if app_date_str:
        try:
            appointment_date_obj = datetime.strptime(app_date_str, '%Y-%m-%d').date()
            if appointment_date_obj < date.today(): errors.append("Cannot schedule appointments in the past.")
        except ValueError: errors.append("Invalid date format for appointment.")
    else: errors.append("Appointment date is required.")
    
    if app_time_str:
        try: appointment_time_obj = datetime.strptime(app_time_str, '%H:%M').time()
        except ValueError: errors.append("Invalid time format for appointment.")
    else: errors.append("Appointment time is required.")
    
    if not patient_phone: errors.append("Phone number is required.")

    if errors:
        for error_msg in errors: flash(error_msg, 'danger')
        redirect_url_params = {'doctor_id': doctor_id, 'errors': errors}
        if original_appointment_id_from_form:
            redirect_url_params['original_appointment_id'] = original_appointment_id_from_form
        
        redirect_url_params['location_id'] = location_id_str
        redirect_url_params['day_db'] = day_of_week_db_str 
        redirect_url_params['date'] = app_date_str
        redirect_url_params['time'] = app_time_str
        redirect_url_params['appointment_type_id'] = appointment_type_id_str
        redirect_url_params['phone'] = patient_phone
        redirect_url_params['reason'] = reason
        
        return redirect(url_for('.schedule_with_doc', **redirect_url_params))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute("SELECT default_duration_minutes FROM appointment_types WHERE type_id = %s AND is_active = TRUE", (appointment_type_id,))
        type_details = cursor.fetchone()
        if not type_details:
            flash("Selected appointment type is invalid or inactive.", "danger")
            return redirect(url_for('.schedule_with_doc', doctor_id=doctor_id, original_appointment_id=original_appointment_id_from_form, **form_data))

        duration = type_details['default_duration_minutes']
        end_time_obj = calculate_end_time(appointment_time_obj, duration)

        clash_check_params = (doctor_id, location_id, appointment_date_obj, end_time_obj, appointment_time_obj) 
        cursor.execute("""
            SELECT appointment_id FROM appointments
            WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s
            AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            AND (start_time < %s AND end_time > %s) 
            LIMIT 1 
        """, clash_check_params)
        if cursor.fetchone():
            flash("The selected time slot is no longer available. Please choose a different time.", "warning")
            return redirect(url_for('.schedule_with_doc', doctor_id=doctor_id, original_appointment_id=original_appointment_id_from_form, **form_data))
        
        db_day_of_week_for_cap = python_dow_to_db_dow(appointment_date_obj.weekday())
        cursor.execute("""
            SELECT max_appointments FROM doctor_location_daily_caps
            WHERE doctor_id = %s AND doctor_location_id = %s AND day_of_week = %s
        """, (doctor_id, location_id, db_day_of_week_for_cap))
        cap_row = cursor.fetchone()
        if cap_row:
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointments
                WHERE doctor_id = %s AND doctor_location_id = %s AND appointment_date = %s
                AND status NOT IN ('canceled', 'rescheduled', 'no-show')
            """, (doctor_id, location_id, appointment_date_obj))
            current_booking_count = cursor.fetchone()['count']
            if current_booking_count >= cap_row['max_appointments']:
                flash(f"The doctor's daily appointment cap for this location/day has been reached.", "warning")
                return redirect(url_for('.schedule_with_doc', doctor_id=doctor_id, original_appointment_id=original_appointment_id_from_form, **form_data))

        insert_query = """
            INSERT INTO appointments (patient_id, doctor_id, appointment_date, start_time, end_time,
                                      appointment_type_id, status, reason, doctor_location_id, created_by, updated_by, reschedule_count)
            VALUES (%s, %s, %s, %s, %s, %s, 'scheduled', %s, %s, %s, %s, %s)
        """
        reschedule_count = 0 
        cursor.execute(insert_query, (current_user.id, doctor_id, appointment_date_obj, appointment_time_obj,
                                      end_time_obj, appointment_type_id, reason, location_id,
                                      current_user.id, current_user.id, reschedule_count))
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
        current_app.logger.error(f"DB error scheduling for Dr {doctor_id}: {err}", exc_info=True)
        flash(f"A database error occurred: {err}. Please try again.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error scheduling for Dr {doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred. Please try again.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    return redirect(url_for('.schedule_with_doc', doctor_id=doctor_id, original_appointment_id=original_appointment_id_from_form, **form_data))

def get_appointment_details_for_view(appointment_id, user_id, user_type):
    conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.end_time,
                apt.type_name as appointment_type_name, 
                a.status, a.reason, a.notes, a.reschedule_count,
                pat_user.first_name as patient_first_name, pat_user.last_name as patient_last_name,
                pat_user.email as patient_email, pat_user.phone as patient_phone,
                doc_user.user_id as doctor_id, doc_user.first_name as doctor_first_name, 
                doc_user.last_name as doctor_last_name,
                d.profile_photo_url as doctor_profile_photo_db_path, -- *** CORRECTED: Fetches from doctors.profile_photo_url ***
                spec.name as specialization_name,
                dl.location_name, dl.address as location_address
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id
            JOIN users pat_user ON a.patient_id = pat_user.user_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            JOIN doctors d ON a.doctor_id = d.user_id -- 'd' is alias for doctors table
            LEFT JOIN specializations spec ON d.specialization_id = spec.specialization_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            WHERE a.appointment_id = %s
        """
        params = [appointment_id]
        if user_type == 'patient': 
            query += " AND a.patient_id = %s"
            params.append(user_id)
        elif user_type == 'doctor': 
            query += " AND a.doctor_id = %s"
            params.append(user_id)
        elif user_type != 'admin': 
            return None 
        
        cursor.execute(query, tuple(params))
        appointment = cursor.fetchone()

        if appointment:
            appointment['display_date'] = appointment['appointment_date'].strftime('%A, %B %d, %Y')
            appointment['display_start_time'] = format_time_for_display(appointment['start_time'])
            appointment['display_end_time'] = format_time_for_display(appointment['end_time'])
            appointment['doctor_full_name'] = f"Dr. {appointment['doctor_first_name']} {appointment['doctor_last_name']}"
            appointment['patient_full_name'] = f"{appointment['patient_first_name']} {appointment['patient_last_name']}"
            appointment['status_badge_class'] = map_status_to_badge_class(appointment['status'])

            doc_photo_db_path = appointment.get('doctor_profile_photo_db_path')
            appointment['doctor_profile_photo_display_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')
            if doc_photo_db_path:
                if current_app and current_app.static_folder:
                    full_abs_path_to_check = os.path.join(current_app.static_folder, doc_photo_db_path)
                    if not os.path.exists(full_abs_path_to_check):
                        getattr(logger, 'warning', print)(f"Doctor profile image file NOT FOUND for appt {appointment_id} at '{full_abs_path_to_check}' (DB path: '{doc_photo_db_path}'). Using default.")
                    else:
                        appointment['doctor_profile_photo_display_url'] = url_for('static', filename=doc_photo_db_path)
                else: 
                     appointment['doctor_profile_photo_display_url'] = url_for('static', filename=doc_photo_db_path)
        return appointment
    except Exception as e:
        getattr(logger, 'error', print)(f"Error in get_appointment_details_for_view (Appt ID: {appointment_id}): {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_appointments_for_user(user_id, user_type):
    conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        base_query = """
            SELECT
                a.appointment_id, a.appointment_date, a.start_time, a.status,
                apt.type_name as appointment_type_name, 
                dl.location_name,
                doc_details.profile_photo_url as doctor_profile_photo_db_path, -- *** CORRECTED ***
                pat_user.profile_picture as patient_profile_photo_db_path, 
                CASE 
                    WHEN %s = 'patient' THEN CONCAT('Dr. ', doc_user.first_name, ' ', doc_user.last_name)
                    WHEN %s = 'doctor' THEN CONCAT(pat_user.first_name, ' ', pat_user.last_name)
                    ELSE 'N/A' 
                END as other_party_name,
                CASE 
                    WHEN %s = 'patient' THEN s.name 
                    ELSE 'Patient Visit' 
                END as context_info 
            FROM appointments a
            LEFT JOIN appointment_types apt ON a.appointment_type_id = apt.type_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            JOIN users doc_user ON a.doctor_id = doc_user.user_id
            LEFT JOIN doctors doc_details ON doc_user.user_id = doc_details.user_id -- 'doc_details' is alias for doctors
            LEFT JOIN specializations s ON doc_details.specialization_id = s.specialization_id
            JOIN users pat_user ON a.patient_id = pat_user.user_id
        """
        
        params = [user_type, user_type, user_type] 
        if user_type == 'patient': 
            where_clause = "WHERE a.patient_id = %s"
            params.append(user_id)
        elif user_type == 'doctor': 
            where_clause = "WHERE a.doctor_id = %s"
            params.append(user_id)
        elif user_type == 'admin':
            where_clause = "" 
        else: 
            return [] 

        query = base_query + " " + where_clause + " ORDER BY a.appointment_date DESC, a.start_time DESC"
        cursor.execute(query, tuple(params))
        appointments = cursor.fetchall()
        today_date_obj = date.today()

        for appt in appointments:
            appt['display_date'] = appt['appointment_date'].strftime('%Y-%m-%d')
            appt['display_time'] = format_time_for_display(appt['start_time'])
            appt['status_badge_class'] = map_status_to_badge_class(appt['status'])
            appt['appointment_type_display'] = appt.get('appointment_type_name', 'N/A')
            if appt['appointment_date'] >= today_date_obj and appt['status'] not in ['completed', 'canceled', 'no-show', 'rescheduled']:
                appt['category'] = 'upcoming'
            else:
                appt['category'] = 'past'
            
            other_party_photo_db_path = None
            if user_type == 'patient':
                other_party_photo_db_path = appt.get('doctor_profile_photo_db_path')
            elif user_type == 'doctor':
                other_party_photo_db_path = appt.get('patient_profile_photo_db_path') # Assumes patients have profile_picture in users
            
            appt['other_party_photo_display_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')
            if other_party_photo_db_path:
                if current_app and current_app.static_folder:
                    full_abs_path_to_check = os.path.join(current_app.static_folder, other_party_photo_db_path)
                    if not os.path.exists(full_abs_path_to_check):
                        getattr(logger, 'warning', print)(f"Other party profile image file NOT FOUND for appt {appt['appointment_id']} at '{full_abs_path_to_check}' (DB path: '{other_party_photo_db_path}'). Using default.")
                    else:
                        appt['other_party_photo_display_url'] = url_for('static', filename=other_party_photo_db_path)
                else:
                    appt['other_party_photo_display_url'] = url_for('static', filename=other_party_photo_db_path)
        return appointments
    except Exception as e:
        getattr(logger, 'error', print)(f"Error in get_appointments_for_user (User ID: {user_id}, Type: {user_type}): {e}", exc_info=True)
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@appointment_bp.route('/my-appointments')
@login_required
def view_my_appointments():
    appointments = get_appointments_for_user(current_user.id, current_user.user_type)
    upcoming_appointments = [appt for appt in appointments if appt['category'] == 'upcoming']
    past_appointments = [appt for appt in appointments if appt['category'] == 'past']
    return render_template('Website/Appointments/my_appointments.html', 
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
    return render_template('Website/Appointments/appointment_detail.html', appointment=appointment)

@appointment_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT appointment_id, patient_id, doctor_id, status, appointment_date FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appointment = cursor.fetchone()

        if not appointment: 
            flash("Appointment not found.", "danger")
            return redirect(url_for('.view_my_appointments'))

        can_cancel = False
        if current_user.user_type == 'patient' and appointment['patient_id'] == current_user.id: can_cancel = True
        
        if not can_cancel: 
            flash("You do not have permission to cancel this appointment.", "danger")
            return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))

        if appointment['status'] not in ['scheduled', 'confirmed']: 
            flash(f"This appointment cannot be canceled (Status: {appointment['status']}).", "warning")
            return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))
        
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

@appointment_bp.route('/<int:appointment_id>/reschedule/start', methods=['GET'])
@login_required
def reschedule_appointment_start(appointment_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT a.appointment_id, a.patient_id, a.doctor_id, a.status,
                   a.doctor_location_id, a.appointment_type_id, a.reason
            FROM appointments a
            WHERE a.appointment_id = %s
        """, (appointment_id,))
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
        
        cursor.execute("""
            UPDATE appointments SET status = 'rescheduled',
                                 reschedule_count = COALESCE(reschedule_count, 0) + 1, 
                                 updated_by = %s,
                                 updated_at = CURRENT_TIMESTAMP
            WHERE appointment_id = %s
        """, (current_user.id, appointment_id))
        conn.commit()
        flash("Original appointment marked for reschedule. Please book a new appointment time.", "info")

        return redirect(url_for('.schedule_with_doc',
                                doctor_id=original_appointment['doctor_id'],
                                original_appointment_id=original_appointment['appointment_id'],
                                location_id=original_appointment.get('doctor_location_id'),
                                appointment_type_id=original_appointment.get('appointment_type_id'),
                                reason=original_appointment.get('reason', ''),
                                phone=current_user.phone or '' 
                                ))
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        flash(f"Database error: {err}", "danger")
    except Exception as e:
        if conn: conn.rollback()
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.view_appointment_detail', appointment_id=appointment_id))

@appointment_bp.route('/missed-appointment-followup/<int:appointment_id>', methods=['POST'])
@login_required
def flag_for_followup(appointment_id):
    if current_user.user_type not in ['admin', 'doctor']: return jsonify({"error": "Unauthorized"}), 403
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT status FROM appointments WHERE appointment_id = %s", (appointment_id,))
        appt = cursor.fetchone()
        if not appt or appt['status'] not in ['no-show', 'canceled']: return jsonify({"error": "Appointment not eligible"}), 400
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