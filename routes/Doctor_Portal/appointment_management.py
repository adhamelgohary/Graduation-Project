# routes/Doctor_Portal/appointment_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, timedelta, time
import math
import json
import logging # Use standard logging

from .utils import (
    check_doctor_authorization,
    check_provider_authorization,      # Import if used
    check_doctor_or_dietitian_authorization, # Import if used
    is_doctor_authorized_for_patient, # Import if used
    get_provider_id,
    get_enum_values,                 # Import if used
    get_all_simple,                  # Import if used
    calculate_age,                   # Import if used
    allowed_file,                    # Import if used
    generate_secure_filename,
    can_modify_appointment         # Import if used
)

# Configure logger
logger = logging.getLogger(__name__)

# --- Import necessary functions from other modules ---
try:
    # Import location fetching from availability module (or location module if moved)
    from .availability_management import get_all_provider_locations
except ImportError:
    logger.error("CRITICAL: Failed to import availability management functions into appointments.", exc_info=True)
    def get_all_provider_locations(provider_id): logger.error("Dummy get_all_provider_locations called."); return []


# --- Blueprint Definition ---
appointments_bp = Blueprint(
    'appointments',
    __name__,
    url_prefix='/portal/appointments',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 20
VALID_SORT_COLUMNS = { # Map user-facing keys to actual DB columns (UPDATED location sort)
    'date': 'a.appointment_date', 'patient': 'p_user.last_name', 'type': 'a.appointment_type',
    'status': 'a.status', 'doctor': 'd_user.last_name',
    'location': 'dl.location_name' # <<< UPDATED Sort column (using doctor_locations alias 'dl')
}
DEFAULT_SORT_COLUMN = 'date'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE = {}
DEFAULT_APPOINTMENT_DURATIONS = { # Default durations in minutes
    'initial': 60, 'follow-up': 30, 'consultation': 45, 'urgent': 30,
    'routine': 20, 'telehealth': 30, 'physical': 45, 'other': 30,
    'nutrition_consult': 45 # Added from schema
}


# --- Helper Functions (Specific to Appointments or Utilities) ---

def get_enum_values(table_name, column_name):
    """Fetches and caches ENUM values for a given column."""
    # Keep as is
    cache_key = f"{table_name}_{column_name}"
    # ... (implementation as before) ...
    if cache_key in ENUM_CACHE: return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB conn failed")
        cursor = conn.cursor(); db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name)); result = cursor.fetchone()
        if result and result[0]: enum_str = result[0]; enum_content = enum_str[enum_str.find("(")+1:enum_str.rfind(")")]; values = [val.strip().strip("'\"") for val in enum_content.split(",")]
        ENUM_CACHE[cache_key] = values; return values
    except (mysql.connector.Error, ConnectionError, IndexError, TypeError) as e: logger.error(f"Error get ENUM {table_name}.{column_name}: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_col, name_col, order_by=None, where_clause=None, params=None):
    """Utility to fetch ID/Name pairs for dropdowns."""
    # Keep as is
    conn = None; cursor = None; items = []
    # ... (implementation as before) ...
    order_clause = f"ORDER BY {order_by}" if order_by else f"ORDER BY {name_col}"
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB conn failed")
        cursor = conn.cursor(dictionary=True)
        query = f"SELECT {id_col}, {name_col} as name FROM {table_name} {where_sql} {order_clause}"
        cursor.execute(query, params or []); items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e: logger.error(f"Error get simple list {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

def get_appointment_duration(appointment_type):
    """Gets the duration in minutes for a given appointment type."""
    # Keep as is
    return DEFAULT_APPOINTMENT_DURATIONS.get(str(appointment_type).lower(), 30)

# *** MAJOR UPDATE: is_slot_available ***
def is_slot_available(cursor, doctor_id, doctor_location_id, appt_date, start_time, end_time, exclude_appointment_id=None):
    """
    Checks if a specific time slot at a specific doctor location is available.
    Considers: Location-specific overrides, General overrides, Location-specific weekly availability, Conflicting appointments at that location.
    Requires an active cursor from the calling function.
    """
    try:
        appt_date_obj = appt_date if isinstance(appt_date, date) else datetime.strptime(str(appt_date), '%Y-%m-%d').date()
        start_time_obj = start_time if isinstance(start_time, time) else datetime.strptime(str(start_time), '%H:%M:%S').time() # Handle seconds if present
        end_time_obj = end_time if isinstance(end_time, time) else datetime.strptime(str(end_time), '%H:%M:%S').time()

        # Ensure doctor_location_id is valid integer for queries
        if doctor_location_id is None:
            return False, "Location is required to check availability."
        current_location_id = int(doctor_location_id)

        # DB schema day of week (0=Sun, 1=Mon...) vs Python (0=Mon, 1=Tue...)
        schema_day_of_week = (appt_date_obj.weekday() + 1) % 7

        # 1. Check for blocking overrides (specific location OR general)
        sql_override = """
            SELECT 1 FROM doctor_availability_overrides
            WHERE doctor_id = %(did)s
              AND override_date = %(date)s
              AND is_unavailable = TRUE
              AND (doctor_location_id IS NULL OR doctor_location_id = %(dlid)s) -- General or specific location override
              AND (start_time IS NULL OR (%(start)s < end_time AND %(end)s > start_time)) -- Full day or overlap
            LIMIT 1
        """
        params_override = {'did': doctor_id, 'date': appt_date_obj, 'dlid': current_location_id, 'start': start_time_obj, 'end': end_time_obj}
        cursor.execute(sql_override, params_override)
        if cursor.fetchone():
            logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Blocked by override.")
            return False, "Provider is unavailable due to an override for this time/location."

        # 2. Check for conflicting appointments at this SPECIFIC location
        sql_appt_conflict = """
            SELECT COUNT(appointment_id) as count FROM appointments
            WHERE doctor_id = %(did)s
              AND appointment_date = %(date)s
              AND doctor_location_id = %(dlid)s -- Must match location
              AND status NOT IN ('canceled', 'no-show')
              AND (%(start)s < end_time AND %(end)s > start_time)
        """
        params_appt = {'did': doctor_id, 'date': appt_date_obj, 'dlid': current_location_id, 'start': start_time_obj, 'end': end_time_obj}
        if exclude_appointment_id:
            sql_appt_conflict += " AND appointment_id != %(ex_id)s"
            params_appt['ex_id'] = exclude_appointment_id
        # Note: Still doesn't consider provider_daily_limits here. Add check if needed.
        cursor.execute(sql_appt_conflict, params_appt)
        conflict_count = cursor.fetchone()['count']
        if conflict_count > 0:
             logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Conflict (count={conflict_count}, excluding {exclude_appointment_id}).")
             return False, "Time slot conflicts with an existing appointment at this location."

        # 3. Check if an *available* override covers this time (general or specific location)
        sql_avail_override = """
            SELECT 1 FROM doctor_availability_overrides
            WHERE doctor_id = %(did)s
              AND override_date = %(date)s
              AND is_unavailable = FALSE
              AND (doctor_location_id IS NULL OR doctor_location_id = %(dlid)s) -- General or specific location override
              AND (%(start)s >= start_time AND %(end)s <= end_time) -- Slot must be WITHIN the available override time
            LIMIT 1
        """
        # Using same params_override from step 1
        cursor.execute(sql_avail_override, params_override)
        if cursor.fetchone():
            logger.debug(f"Slot check success P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Available via override.")
            return True, "Slot available (Override)."

        # 4. Check location-specific weekly availability
        sql_location_avail = """
            SELECT 1 FROM doctor_location_availability
            WHERE doctor_location_id = %(dlid)s
              AND day_of_week = %(dow)s
              AND (%(start)s >= start_time AND %(end)s <= end_time) -- Slot must be WITHIN the defined weekly slot
            LIMIT 1
        """
        params_loc_avail = {'dlid': current_location_id, 'dow': schema_day_of_week, 'start': start_time_obj, 'end': end_time_obj}
        cursor.execute(sql_location_avail, params_loc_avail)
        if cursor.fetchone():
            logger.debug(f"Slot check success P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Available via location schedule.")
            return True, "Slot available (Location Schedule)."

        # 5. If none of the above, it's not available
        logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: No matching availability.")
        return False, "Time slot is outside the provider's configured availability for this location."

    except Exception as e:
        logger.error(f"Error checking slot availability P:{doctor_id} L:{doctor_location_id} D:{appt_date} T:{start_time}-{end_time}: {e}", exc_info=True)
        return False, "Could not verify slot availability due to an internal error."


# --- Core Appointment Data Fetching ---

# *** UPDATED get_paginated_appointments ***
def get_paginated_appointments(provider_user_id_int, page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
    """Fetches paginated appointments for a specific provider."""
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    if sort_by == 'date': sort_column_sql = "a.appointment_date, a.start_time"
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn failed")
        cursor = conn.cursor(dictionary=True)

        # Use alias 'dl' for doctor_locations join
        sql_select = "SELECT SQL_CALC_FOUND_ROWS a.*, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name, d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name, dl.location_name" # <<< UPDATED location name source
        sql_from = """
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            JOIN users d_user ON a.doctor_id = d_user.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id -- <<< UPDATED JOIN
        """
        sql_where = " WHERE a.doctor_id = %s"
        params = [provider_user_id_int]

        # Apply Filters (Date Range, Search, Status, Type, Location)
        start_date = valid_filters.get('start_date'); end_date = valid_filters.get('end_date')
        if start_date: sql_where += " AND a.appointment_date >= %s"; params.append(start_date)
        if end_date: sql_where += " AND a.appointment_date <= %s"; params.append(end_date)
        if search_term:
            search_like = f"%{search_term}%"; sql_where += " AND (p_user.first_name LIKE %s OR p_user.last_name LIKE %s OR a.reason LIKE %s OR p_user.email LIKE %s OR dl.location_name LIKE %s)"; params.extend([search_like] * 5) # Added location search
        statuses = valid_filters.get('status')
        if statuses and isinstance(statuses, list) and len(statuses) > 0: placeholders = ','.join(['%s'] * len(statuses)); sql_where += f" AND a.status IN ({placeholders})"; params.extend(statuses)
        app_type = valid_filters.get('appointment_type')
        if app_type: sql_where += " AND a.appointment_type = %s"; params.append(app_type)
        # Add location filter if needed
        filter_location_id = valid_filters.get('doctor_location_id')
        if filter_location_id: sql_where += " AND a.doctor_location_id = %s"; params.append(filter_location_id)

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        # Format date/time
        for item in result['items']:
            if isinstance(item.get('start_time'), timedelta): item['start_time_str'] = str(item['start_time'])[:5]
            if isinstance(item.get('end_time'), timedelta): item['end_time_str'] = str(item['end_time'])[:5]
            if isinstance(item.get('appointment_date'), date): item['appointment_date_str'] = item['appointment_date'].isoformat()
            # location_name should come from the join now
            if item.get('location_name') is None: item['location_name'] = 'N/A' # Handle if location was deleted (SET NULL)

        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error fetching paginated appointments P:{provider_user_id_int}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

# *** UPDATED get_appointment_details ***
def get_appointment_details(appointment_id, provider_user_id_int):
    """Fetches full details of a specific appointment, checking provider access."""
    conn = None; cursor = None; details = None
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn failed")
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT a.*,
                   p.user_id as patient_user_id, p.date_of_birth, p.gender,
                   p.insurance_policy_number, p.insurance_group_number, p.insurance_expiration,
                   p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                   p_user.email as patient_email, p_user.phone as patient_phone,
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name,
                   ip.provider_name as insurance_provider_name,
                   dl.location_name, dl.address as location_address, -- <<< UPDATED location fetch
                   cr_user.username as created_by_username,
                   up_user.username as updated_by_username
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN patients p ON a.patient_id = p.user_id
            JOIN users d_user ON a.doctor_id = d_user.user_id
            LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id -- <<< UPDATED JOIN
            LEFT JOIN users cr_user ON a.created_by = cr_user.user_id
            LEFT JOIN users up_user ON a.updated_by = up_user.user_id
            WHERE a.appointment_id = %s AND a.doctor_id = %s -- Assuming doctor_id check is sufficient for provider access
        """
        cursor.execute(sql, (appointment_id, provider_user_id_int))
        details = cursor.fetchone()
        if details:
            # Format times/dates/age (keep existing formatting logic)
            if isinstance(details.get('start_time'), timedelta): details['start_time_str'] = str(details['start_time'])[:5]
            if isinstance(details.get('end_time'), timedelta): details['end_time_str'] = str(details['end_time'])[:5]
            if isinstance(details.get('appointment_date'), date): details['appointment_date_str'] = details['appointment_date'].isoformat()
            if details.get('location_name') is None: details['location_name'] = 'N/A'
            if details.get('date_of_birth') and isinstance(details['date_of_birth'], date): today = date.today(); details['patient_age'] = today.year - details['date_of_birth'].year - ((today.month, today.day) < (details['date_of_birth'].month, details['date_of_birth'].day))
            else: details['patient_age'] = None

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error fetching appointment details ID {appointment_id}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details


# --- Routes ---

@appointments_bp.route('/', methods=['GET'])
@login_required
def list_appointments():
    # (Keep existing logic, but add location filter capability)
    if not check_provider_authorization(current_user): flash("Access denied.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    # ... get pagination, search, sort params ...#
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    start_date_str = request.args.get('start_date', ''); end_date_str = request.args.get('end_date', '')
    view_mode = request.args.get('view', 'upcoming')
    filter_statuses = request.args.getlist('status')
    filter_type = request.args.get('appointment_type', '')
    # *** NEW: Get location filter ***
    filter_location_id = request.args.get('doctor_location_id', type=int)

    # ... date calculation logic (keep as is) ...
    # ... sort param validation (keep as is) ...
    start_date, end_date = None, None; today = date.today(); effective_start_date_str, effective_end_date_str = start_date_str, end_date_str
    # ... (date calculation based on view_mode) ...
    try: # Date/View mode logic
        if   view_mode == 'today': start_date, end_date = today, today
        elif view_mode == 'week': start_of_week = today - timedelta(days=today.weekday()); start_date, end_date = start_of_week, start_of_week + timedelta(days=6)
        elif view_mode == 'month': start_date = today.replace(day=1); next_m = (start_date + timedelta(days=32)).replace(day=1); end_date = next_m-timedelta(days=1)
        elif view_mode == 'upcoming': start_date = today; end_date = None
        elif view_mode == 'past': start_date = None; end_date = today - timedelta(days=1)
        elif view_mode == 'custom':
             if start_date_str: start_date = date.fromisoformat(start_date_str)
             if end_date_str: end_date = date.fromisoformat(end_date_str)
        else: view_mode = 'upcoming'; start_date=today; end_date=None
        if start_date and end_date and end_date < start_date: raise ValueError("End date < start date.")
        effective_start_date_str=start_date.isoformat() if start_date else ''; effective_end_date_str=end_date.isoformat() if end_date else ''
        if view_mode=='upcoming': effective_end_date_str=''; 
        if view_mode=='past': effective_start_date_str=''
    except ValueError as e: flash(f"Invalid date: {e}"); view_mode='upcoming'; start_date=today; end_date=None; effective_start_date_str=today.isoformat(); effective_end_date_str=''

    # Validate sort params
    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    # Filters for the DB function
    filters = {
        'start_date': start_date, 'end_date': end_date,
        'status': filter_statuses, 'appointment_type': filter_type,
        'doctor_location_id': filter_location_id # <<< Pass location filter
    }

    result = get_paginated_appointments( # Call updated function
        provider_user_id_int=provider_user_id, page=page, per_page=ITEMS_PER_PAGE,
        search_term=search_term, sort_by=sort_by, sort_dir=sort_dir, filters=filters
    )

    # Fetch data for filter dropdowns
    appointment_types = get_enum_values('appointments', 'appointment_type')
    appointment_statuses = get_enum_values('appointments', 'status')
    # *** Get doctor's locations for the filter dropdown ***
    provider_locations = get_all_provider_locations(provider_user_id)

    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0

    # Pass necessary filter data back to template
    return render_template(
        'Doctor_Portal/Appointments/appointment_list.html',
        appointments=result['items'], total_items=total_items, total_pages=total_pages,
        search_term=search_term, current_page=page, sort_by=sort_by, sort_dir=sort_dir,
        filter_statuses=filter_statuses, filter_type=filter_type,
        start_date_str=effective_start_date_str, end_date_str=effective_end_date_str,
        view_mode=view_mode,
        appointment_types=appointment_types, appointment_statuses=appointment_statuses,
        provider_locations=provider_locations, # <<< Pass locations for filter
        filter_location_id=filter_location_id, # <<< Pass selected filter value
        valid_sort_columns=VALID_SORT_COLUMNS.keys()
    )

@appointments_bp.route('/calendar', methods=['GET'])
@login_required
def calendar_view():
    # Keep as is
    if not check_provider_authorization(current_user): flash("Access denied.", "danger"); return redirect(url_for('doctor_main.dashboard'))
    provider_id = get_provider_id(current_user); return render_template('Doctor_Portal/Appointments/calendar_view.html', provider_id=provider_id)

@appointments_bp.route('/<int:appointment_id>', methods=['GET'])
@login_required
def view_appointment(appointment_id):
    # Call updated get_appointment_details
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    details = get_appointment_details(appointment_id, provider_user_id) # Uses updated query
    if not details: flash("Appointment not found or access denied.", "warning"); return redirect(url_for('.list_appointments'))
    appointment_statuses = get_enum_values('appointments', 'status')
    return render_template('Doctor_Portal/Appointments/appointment_detail.html', appointment=details, appointment_statuses=appointment_statuses)

# *** UPDATED create_appointment ***
@appointments_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_appointment():
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user); # ... handle None ...

    # Fetch data for dropdowns
    appointment_types = get_enum_values('appointments', 'appointment_type')
    patients = get_all_simple('users', 'user_id', "CONCAT(last_name, ', ', first_name, ' (ID:', user_id, ')')", where_clause="user_type='patient' AND account_status='active'", order_by="last_name, first_name")
    doctors = [{'user_id': provider_user_id, 'name': f"Dr. {current_user.last_name}, {current_user.first_name}"}]
    # *** Use correct function to get doctor's locations ***
    locations = get_all_provider_locations(provider_user_id)
    if not locations: flash("Warning: Please add a practice location in Settings before creating appointments.", "warning")

    today_iso = date.today().isoformat()

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        form_data = request.form.to_dict()
        try:
            patient_id = request.form.get('patient_id', type=int)
            doctor_id = provider_user_id # Doctor is the current user
            appt_date_str = request.form.get('appointment_date')
            start_time_str = request.form.get('start_time')
            appointment_type = request.form.get('appointment_type')
            # *** Use doctor_location_id ***
            doctor_location_id = request.form.get('doctor_location_id', type=int)
            reason = request.form.get('reason', '').strip() or None
            notes = request.form.get('notes', '').strip() or None

            # Validation
            if not patient_id: errors.append("Patient is required.")
            if not appointment_type: errors.append("Appointment Type is required.")
            if not doctor_location_id: errors.append("Location is required.") # Validate location selection
            # ... other basic validations ...
            appt_date = None; start_time = None; end_time = None
            if not appt_date_str or not start_time_str: errors.append("Date and Start Time are required.")
            else: # Date/Time validation and calculation
                try:
                    appt_date = date.fromisoformat(appt_date_str); start_time = time.fromisoformat(start_time_str)
                    if datetime.combine(appt_date, start_time) < datetime.now() - timedelta(minutes=5): errors.append("Cannot book appointments in the past.")
                    duration_minutes = get_appointment_duration(appointment_type)
                    end_time = (datetime.combine(appt_date, start_time) + timedelta(minutes=duration_minutes)).time()
                except ValueError: errors.append("Invalid Date or Time format.")

            if errors: raise ValueError("Validation Failed")

            # *** Availability check using updated function ***
            conn = get_db_connection()
            if not conn: raise ConnectionError("DB Conn failed")
            cursor = conn.cursor(dictionary=True) # Use dictionary for is_slot_available if it needs it
            is_available, availability_message = is_slot_available(cursor, doctor_id, doctor_location_id, appt_date, start_time, end_time)
            if not is_available:
                errors.append(f"Slot unavailable at selected location: {availability_message}")
                raise ValueError("Availability Check Failed")

            # DB Insert using doctor_location_id
            sql = """INSERT INTO appointments (patient_id, doctor_id, appointment_date, start_time, end_time, appointment_type, status, reason, notes, doctor_location_id, created_by, updated_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""" # <<< UPDATED column name
            params = (patient_id, doctor_id, appt_date, start_time, end_time, appointment_type, 'confirmed', reason, notes, doctor_location_id, provider_user_id, provider_user_id) # <<< UPDATED param
            if cursor.is_connected(): cursor.close() # Close potential dict cursor
            cursor = conn.cursor() # Use standard cursor for insert
            cursor.execute(sql, params)
            conn.commit()
            new_appointment_id = cursor.lastrowid
            flash(f"Appointment created successfully (ID: {new_appointment_id}).", "success")
            return redirect(url_for('.view_appointment', appointment_id=new_appointment_id))

        except ValueError: 
            for err in errors: flash(err, 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            if conn and conn.is_connected(): conn.rollback()
            logger.error(f"Error creating appointment P:{provider_user_id}: {err}", exc_info=True)
            flash("Database error creating appointment.", "danger")
        except Exception as e:
             if conn and conn.is_connected(): conn.rollback()
             logger.error(f"Error creating appointment P:{provider_user_id}: {e}", exc_info=True)
             flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        # Re-render form on POST error
        return render_template('Doctor_Portal/Appointments/create_appointment_form.html', form_data=form_data, patients=patients, doctors=doctors, locations=locations, appointment_types=appointment_types, errors=errors, today_iso=today_iso)

    # Initial GET request
    return render_template('Doctor_Portal/Appointments/create_appointment_form.html', patients=patients, doctors=doctors, locations=locations, appointment_types=appointment_types, today_iso=today_iso)

@appointments_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    # Keep as is (only updates status)
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    # ... (implementation as before) ...
    conn = None; cursor = None; success = False; appt_date_str = None
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn Failed")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, appointment_date FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, provider_user_id))
        appt = cursor.fetchone()
        if not appt: flash("Not found/denied.", "warning")
        elif appt['status'] in ('completed', 'canceled', 'no-show'): flash(f"Cannot cancel: Status is '{appt['status']}'.", "warning")
        else:
            sql_update = "UPDATE appointments SET status = 'canceled', updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
            if cursor.is_connected(): cursor.close()
            cursor = conn.cursor(); cursor.execute(sql_update, (provider_user_id, appointment_id)); conn.commit()
            if cursor.rowcount > 0: flash("Canceled.", "success"); success = True; appt_date_str = appt['appointment_date'].isoformat() if appt.get('appointment_date') else None
            else: flash("Failed cancel.", "danger")
    except (mysql.connector.Error, ConnectionError) as err: logger.error(f"DB Err cancel appt {appointment_id}: {err}"); flash("DB error.", "danger")
    except Exception as e: logger.error(f"Err cancel appt {appointment_id}: {e}"); flash("Error.", "danger")
    finally:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    # Redirect logic
    redirect_url = request.referrer or url_for('.list_appointments')
    if success and request.referrer and f'/appointments/{appointment_id}' in request.referrer: redirect_url = url_for('.list_appointments', view='custom', start_date=appt_date_str, end_date=appt_date_str) if appt_date_str else url_for('.list_appointments')
    return redirect(redirect_url)

# *** UPDATED reschedule_appointment ***
@appointments_bp.route('/<int:appointment_id>/reschedule', methods=['GET', 'POST'])
@login_required
def reschedule_appointment(appointment_id):
    if not check_provider_authorization(current_user): abort(403)
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    conn = None; cursor = None;
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn failed")
        cursor = conn.cursor(dictionary=True)
        # Fetch appointment details - JOINING doctor_locations
        sql_fetch = """
           SELECT a.*, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name, dl.location_name
           FROM appointments a
           JOIN users p_user ON a.patient_id = p_user.user_id
           LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id -- <<< UPDATED JOIN
           WHERE a.appointment_id = %s AND a.doctor_id = %s
        """
        cursor.execute(sql_fetch, (appointment_id, provider_user_id))
        appointment = cursor.fetchone()

        # Check existence and status (keep as is)
        if not appointment: flash("Not found/denied.", "warning"); return redirect(url_for('.list_appointments'))
        if appointment['status'] in ('completed', 'canceled', 'no-show'): flash(f"Cannot reschedule: Status '{appointment['status']}'.", "warning"); return redirect(url_for('.view_appointment', appointment_id=appointment_id))

        # Format existing date/time (keep as is)
        if appointment.get('appointment_date'): appointment['appointment_date_str'] = appointment['appointment_date'].isoformat()
        if appointment.get('start_time'): appointment['start_time_str'] = str(appointment['start_time'])[:5] # HH:MM

        # Get locations for dropdown (keep as is)
        locations = get_all_provider_locations(provider_user_id)
        today_iso = date.today().isoformat() # For min date

        if request.method == 'POST':
            errors = []
            form_data = request.form.to_dict()
            try:
                new_date_str = request.form.get('appointment_date')
                new_time_str = request.form.get('start_time')
                # *** Use doctor_location_id ***
                new_doctor_location_id = request.form.get('doctor_location_id', type=int)
                reason = request.form.get('reason', appointment.get('reason', '')).strip() or None
                notes = request.form.get('notes', appointment.get('notes', '')).strip() or None

                # Validation
                if not new_doctor_location_id: errors.append("Location is required.") # Validate new location
                # ... date/time validation (keep as is) ...
                new_date = None; new_start_time = None; new_end_time = None
                if not new_date_str or not new_time_str: errors.append("New Date and Start Time required.")
                else:
                    try: # Date/Time validation
                        new_date = date.fromisoformat(new_date_str); new_start_time = time.fromisoformat(new_time_str)
                        if datetime.combine(new_date, new_start_time) < datetime.now() - timedelta(minutes=5): errors.append("Cannot reschedule into the past.")
                        duration = get_appointment_duration(appointment['appointment_type'])
                        new_end_time = (datetime.combine(new_date, new_start_time) + timedelta(minutes=duration)).time()
                    except ValueError: errors.append("Invalid Date/Time.")

                if errors: raise ValueError("Validation Failed")

                # *** Availability Check using updated function & new location ID ***
                is_available, availability_message = is_slot_available(cursor, provider_user_id, new_doctor_location_id, new_date, new_start_time, new_end_time, exclude_appointment_id=appointment_id)
                if not is_available:
                    errors.append(f"New slot unavailable: {availability_message}")
                    raise ValueError("Availability Check Failed")

                # DB Update using doctor_location_id
                sql_update = "UPDATE appointments SET appointment_date=%s, start_time=%s, end_time=%s, doctor_location_id=%s, status=%s, reason=%s, notes=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE appointment_id=%s AND doctor_id=%s" # <<< ADDED doctor_location_id
                params = (new_date, new_start_time, new_end_time, new_doctor_location_id, 'confirmed', reason, notes, provider_user_id, appointment_id, provider_user_id) # <<< ADDED param
                if cursor.is_connected(): cursor.close()
                cursor = conn.cursor() # Use fresh standard cursor
                cursor.execute(sql_update, params)
                conn.commit()
                flash("Appointment rescheduled successfully.", "success")
                return redirect(url_for('.view_appointment', appointment_id=appointment_id))

            except ValueError: 
                for err in errors: flash(err, 'danger')
            except (mysql.connector.Error, ConnectionError) as err: # DB Error handling
                 if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
                 logger.error(f"DB Err reschedule appt {appointment_id} P:{provider_user_id}: {err}", exc_info=True)
                 flash("Database error rescheduling.", "danger")
            except Exception as e: # Unexpected error handling
                 if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
                 logger.error(f"Err reschedule appt {appointment_id} P:{provider_user_id}: {e}", exc_info=True)
                 flash("Unexpected error rescheduling.", "danger")

            # Re-render form on POST error
            appointment.update(form_data) # Update with attempted values
            appointment['appointment_date_str'] = new_date_str
            appointment['start_time_str'] = new_time_str
            appointment['doctor_location_id'] = new_doctor_location_id # Ensure selected location persists
            return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html', appointment=appointment, locations=locations, errors=errors, today_iso=today_iso)

        # Initial GET request
        return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html', appointment=appointment, locations=locations, today_iso=today_iso)

    except ConnectionError as ce: flash("DB conn error.", "danger"); return redirect(url_for('.list_appointments'))
    except Exception as e: logger.error(f"Error loading reschedule page {appointment_id}: {e}", exc_info=True); flash("Unexpected error.", "danger"); return redirect(url_for('.list_appointments'))
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@appointments_bp.route('/<int:appointment_id>/update_status', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    # Keep as is (only updates status)
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Auth req."), 403
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    # ... (implementation as before) ...
    new_status = request.json.get('status')
    available_statuses = get_enum_values('appointments', 'status')
    if not new_status or new_status not in available_statuses: return jsonify(success=False, message="Invalid status."), 400
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        if not can_modify_appointment(cursor, appointment_id, provider_user_id): return jsonify(success=False, message="Denied."), 403
        sql_update = "UPDATE appointments SET status = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
        cursor.execute(sql_update, (new_status, provider_user_id, appointment_id)); conn.commit()
        if cursor.rowcount > 0: return jsonify(success=True, message=f"Status updated.", new_status=new_status)
        else: cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s", (appointment_id,)); status_code = 400 if cursor.fetchone() else 404; return jsonify(success=False, message="Update failed."), status_code
    except mysql.connector.Error as err: logger.error(f"DB Err update status {appointment_id}: {err}"); return jsonify(success=False, message=f"DB error: {err.msg}"), 500
    except Exception as e: logger.error(f"Err update status {appointment_id}: {e}"); return jsonify(success=False, message="Error."), 500
    finally: # ... close conn ...
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@appointments_bp.route('/<int:appointment_id>/update_notes', methods=['POST'])
@login_required
def update_appointment_notes(appointment_id):
    # Keep as is (only updates notes)
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Auth req."), 403
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    # ... (implementation as before) ...
    new_notes = request.json.get('notes', None);
    if new_notes is not None: new_notes = new_notes.strip() or None
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        if not can_modify_appointment(cursor, appointment_id, provider_user_id): return jsonify(success=False, message="Denied."), 403
        sql_update = "UPDATE appointments SET notes = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP WHERE appointment_id = %s"
        cursor.execute(sql_update, (new_notes, provider_user_id, appointment_id)); conn.commit()
        if cursor.rowcount > 0: return jsonify(success=True, message="Notes updated.")
        else: cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s", (appointment_id,)); status_code = 400 if cursor.fetchone() else 404; return jsonify(success=False, message="Update failed."), status_code
    except mysql.connector.Error as err: logger.error(f"DB Err update notes {appointment_id}: {err}"); return jsonify(success=False, message=f"DB error: {err.msg}"), 500
    except Exception as e: logger.error(f"Err update notes {appointment_id}: {e}"); return jsonify(success=False, message="Error."), 500
    finally: # ... close conn ...
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# *** UPDATED appointment_data_feed ***
@appointments_bp.route('/feed', methods=['GET'])
@login_required
def appointment_data_feed():
    """Provides appointment data formatted for FullCalendar."""
    if not check_provider_authorization(current_user): return jsonify([])
    provider_user_id = get_provider_id(current_user); # ... handle None ...
    start_str = request.args.get('start'); end_str = request.args.get('end')
    if not start_str or not end_str: return jsonify({"error": "Start/end dates required"}), 400
    try: # Date parsing
        start_date = date.fromisoformat(start_str.split('T')[0]); end_date = date.fromisoformat(end_str.split('T')[0])
    except ValueError: return jsonify({"error": "Invalid date format"}), 400

    conn = None; cursor = None; events = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB conn failed")
        cursor = conn.cursor(dictionary=True)
        # Join appointments with doctor_locations
        sql = """
            SELECT a.appointment_id as id, CONCAT(p_user.last_name, ', ', p_user.first_name) as title_patient,
                   a.appointment_type, a.appointment_date, a.start_time, a.end_time, a.status,
                   dl.location_name -- <<< Get location name from doctor_locations
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id -- <<< UPDATED JOIN
            WHERE a.doctor_id = %s AND a.appointment_date >= %s AND a.appointment_date < %s
              AND a.status NOT IN ('canceled')
        """
        cursor.execute(sql, (provider_user_id, start_date, end_date))
        appointments = cursor.fetchall()

        status_colors = {'confirmed': '#198754', 'completed': '#6c757d', 'no-show': '#ffc107', 'rescheduled': '#fd7e14', 'pending': '#0dcaf0'}; default_color = '#0d6efd'

        for appt in appointments:
            if isinstance(appt.get('start_time'), timedelta) and isinstance(appt.get('end_time'), timedelta): # Check times valid
                 start_dt_str = f"{appt['appointment_date'].isoformat()}T{str(appt['start_time'])}"; end_dt_str = f"{appt['appointment_date'].isoformat()}T{str(appt['end_time'])}"
            else: continue

            event = { 'id': appt['id'], 'title': f"{appt['title_patient']} ({appt['appointment_type']}{' @ ' + appt['location_name'] if appt.get('location_name') else ''})", 'start': start_dt_str, 'end': end_dt_str, 'color': status_colors.get(appt['status'], default_color), 'url': url_for('.view_appointment', appointment_id=appt['id']), 'extendedProps': { 'status': appt['status'], 'type': appt['appointment_type'], 'location': appt.get('location_name', 'N/A') } }
            events.append(event)
        return jsonify(events)

    except (mysql.connector.Error, ConnectionError) as err: logger.error(f"DB Error appt feed: {err}"); return jsonify({"error": "DB error"}), 500
    except Exception as e: logger.error(f"Error appt feed: {e}", exc_info=True); return jsonify({"error": "Error"}), 500
    finally: # Close connection
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()