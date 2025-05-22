# routes/Doctor_Portal/appointment_management.py

from datetime import date, datetime, time, timedelta
import json
import logging
import math

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
import mysql.connector

from db import get_db_connection

# Configure logger
logger = logging.getLogger(__name__)
# Example: If you want to see logs in console during development
# logging.basicConfig(level=logging.DEBUG)
# logger.setLevel(logging.DEBUG)


# --- Attempt to import REAL functions ---
try:
    # Utils that are generally expected to be present
    from .utils import (
        check_doctor_authorization,
        get_provider_id,
        get_enum_values as get_enum_values_util, # Renamed to avoid conflict
        get_all_simple,
        can_modify_appointment
    )
    # CRITICAL: This function MUST come from your availability_management module
    # and it MUST query the database for the doctor's actual locations.
    from .availability_management import get_all_provider_locations

except (ImportError, ValueError) as e1:
    logger.warning(
        f"Relative import attempt failed (e.g., for 'availability_management' or 'utils'): {e1}. "
        "Trying non-relative import."
    )
    
    try:
        from .utils import (
            check_doctor_authorization,
            get_provider_id,
            get_enum_values as get_enum_values_util,
            get_all_simple,
            can_modify_appointment
        )
        from availability_management import get_all_provider_locations
    except ImportError as e2:
        logger.error(f"Non-relative import attempt also failed: {e2}")
        raise ImportError("Critical functions could not be imported. Application cannot start.")
    
    from availability_management import get_all_provider_locations


# --- Blueprint Definition ---
appointments_bp = Blueprint(
    'appointments',
    __name__,
    url_prefix='/portal/appointments',
    template_folder='../../templates' # Adjust relative path if your templates are elsewhere
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 20
VALID_SORT_COLUMNS = {
    'date': 'a.appointment_date',
    'patient': 'p_user.last_name',
    'type': 'at.type_name',
    'status': 'a.status',
    'doctor': 'd_user.last_name', # Should always be current_user for doctor portal view
    'location': 'dl.location_name'
}
DEFAULT_SORT_COLUMN = 'date'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE_APPT = {} # Specific cache for this blueprint's ENUM needs

TERMINAL_APPT_STATUSES = ['completed', 'canceled', 'no-show', 'rescheduled']


# --- Helper Functions ---

def get_enum_values_appt_specific(table_name, column_name):
    """Fetches and caches ENUM values (e.g., for 'appointments.status')."""
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE_APPT:
        return ENUM_CACHE_APPT[cache_key]

    conn = None
    cursor = None
    values = []
    try:
        conn = get_db_connection()
        if not conn:
            logger.error(f"DB connection failed for ENUM fetch: {table_name}.{column_name}")
            return [] # Return empty on connection failure
        cursor = conn.cursor()
        db_name = conn.database # Get the current database name
        query = """
            SELECT COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0] and result[0].lower().startswith("enum("):
            enum_str = result[0]
            # Correctly parse ENUM string: "enum('val1','val2','val3')"
            enum_content = enum_str[enum_str.find("(")+1:enum_str.rfind(")")]
            values = [val.strip().strip("'\"") for val in enum_content.split(",")]
        ENUM_CACHE_APPT[cache_key] = values
        return values
    except (mysql.connector.Error, ConnectionError, IndexError, TypeError) as e:
        logger.error(f"Error getting ENUM values for {table_name}.{column_name}: {e}", exc_info=True)
        return [] # Return empty list on error
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def get_all_appointment_types():
    """Fetches all active appointment types (id, name, duration) from the database."""
    conn = None
    cursor = None
    types = []
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("DB connection failed for get_all_appointment_types.")
            return []
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT type_id as id, type_name as name, default_duration_minutes
            FROM appointment_types
            WHERE is_active = TRUE
            ORDER BY type_name
        """
        cursor.execute(query)
        types = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        logger.error(f"Database error getting appointment types: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error getting appointment types: {e}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return types

def is_slot_available(cursor, doctor_id, doctor_location_id, appt_date, start_time, end_time, exclude_appointment_id=None):
    """Checks if a specific time slot at a specific doctor location is available."""
    try:
        # Input validation and type conversion
        appt_date_obj = appt_date if isinstance(appt_date, date) else datetime.strptime(str(appt_date), '%Y-%m-%d').date()
        start_time_obj = start_time if isinstance(start_time, time) else datetime.strptime(str(start_time), '%H:%M:%S').time()
        end_time_obj = end_time if isinstance(end_time, time) else datetime.strptime(str(end_time), '%H:%M:%S').time()

        if start_time_obj >= end_time_obj:
            return False, "Start time must be before end time."
        if doctor_location_id is None: # This is a critical check
            logger.error("is_slot_available called with doctor_location_id=None.")
            return False, "Practice location is required to check availability."

        current_location_id = int(doctor_location_id)
        # Python: Mon=0, Sun=6. DB Schema: Sun=0, Sat=6
        schema_day_of_week = (appt_date_obj.weekday() + 1) % 7

        # 1. Check Blocking Overrides (Location specific or General for the doctor)
        sql_override = """
            SELECT 1 FROM doctor_availability_overrides
            WHERE doctor_id = %(did)s AND override_date = %(date)s AND is_unavailable = TRUE
            AND (doctor_location_id IS NULL OR doctor_location_id = %(dlid)s)
            AND (start_time IS NULL OR (%(start)s < end_time AND %(end)s > start_time))
            LIMIT 1
        """
        params_override = {
            'did': doctor_id, 'date': appt_date_obj,
            'dlid': current_location_id,
            'start': start_time_obj, 'end': end_time_obj
        }
        cursor.execute(sql_override, params_override)
        if cursor.fetchone():
            logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Blocked by override.")
            return False, "Provider is unavailable at this time due to an override."

        # 2. Check Appointment Conflicts at Specific Location
        sql_appt_conflict = """
            SELECT COUNT(appointment_id) as count FROM appointments
            WHERE doctor_id = %(did)s AND appointment_date = %(date)s
            AND doctor_location_id = %(dlid)s
            AND status NOT IN ('canceled', 'no-show', 'rescheduled')
            AND (%(start)s < end_time AND %(end)s > start_time)
        """
        params_appt = {
            'did': doctor_id, 'date': appt_date_obj,
            'dlid': current_location_id,
            'start': start_time_obj, 'end': end_time_obj
        }
        if exclude_appointment_id:
            sql_appt_conflict += " AND appointment_id != %(ex_id)s"
            params_appt['ex_id'] = exclude_appointment_id
        cursor.execute(sql_appt_conflict, params_appt)
        conflict_count = cursor.fetchone()['count']
        if conflict_count > 0:
             logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Conflict (count={conflict_count}, excluding {exclude_appointment_id}).")
             return False, "This time slot conflicts with another appointment at this location."

        # 3. Check If Covered by Available Override (Location specific or General for the doctor)
        sql_avail_override = """
            SELECT 1 FROM doctor_availability_overrides
            WHERE doctor_id = %(did)s AND override_date = %(date)s AND is_unavailable = FALSE
            AND (doctor_location_id IS NULL OR doctor_location_id = %(dlid)s)
            AND (%(start)s >= start_time AND %(end)s <= end_time)
            LIMIT 1
        """
        cursor.execute(sql_avail_override, params_override)
        if cursor.fetchone():
            logger.debug(f"Slot check success P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Available via override.")
            return True, "Slot available due to a special availability override."

        # 4. Check Location Weekly Schedule for the specific doctor_location_id
        sql_location_avail = """
            SELECT 1 FROM doctor_location_availability
            WHERE doctor_location_id = %(dlid)s AND day_of_week = %(dow)s
            AND (%(start)s >= start_time AND %(end)s <= end_time)
            LIMIT 1
        """
        params_loc_avail = {
            'dlid': current_location_id, 'dow': schema_day_of_week,
            'start': start_time_obj, 'end': end_time_obj
        }
        cursor.execute(sql_location_avail, params_loc_avail)
        if cursor.fetchone():
            logger.debug(f"Slot check success P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: Available via location schedule.")
            return True, "Slot available based on the location's standard schedule."

        logger.debug(f"Slot check fail P:{doctor_id} L:{current_location_id} D:{appt_date_obj} T:{start_time_obj}-{end_time_obj}: No matching availability rule.")
        return False, "The selected time slot is outside the provider's scheduled availability for this location."

    except Exception as e:
        logger.error(f"Error checking slot availability P:{doctor_id} L:{doctor_location_id} D:{appt_date} T:{start_time}-{end_time}: {e}", exc_info=True)
        return False, "An internal error occurred while checking availability. Please try again."


# --- Core Appointment Data Fetching ---
def get_paginated_appointments(provider_user_id_int, page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
    conn = None
    cursor = None
    result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    if sort_by == 'date': # Combined sort for date and time
        sort_column_sql = "a.appointment_date, a.start_time"
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True) # buffered for FOUND_ROWS
        sql_select = """
            SELECT SQL_CALC_FOUND_ROWS
                   a.appointment_id, a.patient_id, a.doctor_id, a.appointment_date,
                   a.start_time, a.end_time, a.status, a.reason, a.notes,
                   a.doctor_location_id, a.created_at, a.updated_at,
                   a.created_by, a.updated_by, a.appointment_type_id,
                   at.type_name,
                   p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name,
                   dl.location_name
        """
        sql_from = """
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            JOIN users d_user ON a.doctor_id = d_user.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
        """
        sql_where = " WHERE a.doctor_id = %s"
        params = [provider_user_id_int]

        # Add Filters
        start_date = valid_filters.get('start_date')
        end_date = valid_filters.get('end_date')
        if start_date:
            sql_where += " AND a.appointment_date >= %s"
            params.append(start_date)
        if end_date:
            sql_where += " AND a.appointment_date <= %s"
            params.append(end_date)

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += """ AND (p_user.first_name LIKE %s OR p_user.last_name LIKE %s
                              OR a.reason LIKE %s OR at.type_name LIKE %s
                              OR dl.location_name LIKE %s)"""
            params.extend([search_like, search_like, search_like, search_like, search_like])

        statuses = valid_filters.get('status')
        if statuses and isinstance(statuses, list) and len(statuses) > 0:
            placeholders = ','.join(['%s'] * len(statuses))
            sql_where += f" AND a.status IN ({placeholders})"
            params.extend(statuses)

        filter_type_id = valid_filters.get('appointment_type_id')
        if filter_type_id:
            sql_where += " AND a.appointment_type_id = %s"
            params.append(filter_type_id)

        filter_location_id = valid_filters.get('doctor_location_id')
        if filter_location_id:
            sql_where += " AND a.doctor_location_id = %s"
            params.append(filter_location_id)

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(query, tuple(params))
        items = cursor.fetchall()

        for item in items: # Format dates/times and handle nulls post-fetch
            item['type_name'] = item.get('type_name', 'Unknown Type')
            item['start_time_str'] = str(item['start_time'])[:5] if isinstance(item.get('start_time'), timedelta) else 'N/A'
            item['end_time_str'] = str(item['end_time'])[:5] if isinstance(item.get('end_time'), timedelta) else 'N/A'
            item['appointment_date_str'] = item['appointment_date'].isoformat() if isinstance(item.get('appointment_date'), date) else 'N/A'
            item['location_name'] = item.get('location_name', 'N/A')
        result['items'] = items

        cursor.execute("SELECT FOUND_ROWS() as total")
        total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0

    except Exception as err:
        logger.error(f"Error fetching paginated appointments for provider {provider_user_id_int}: {err}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return result

def get_appointment_details(appointment_id, provider_user_id_int):
    conn = None
    cursor = None
    details = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT a.*,
                   at.type_name, at.default_duration_minutes,
                   p.user_id as patient_user_id, p.date_of_birth, p.gender,
                   p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                   p_user.email as patient_email, p_user.phone as patient_phone,
                   d_user.first_name as doctor_first_name, d_user.last_name as doctor_last_name,
                   ip.provider_name as insurance_provider_name,
                   dl.location_name, dl.address as location_address,
                   cr_user.username as created_by_username,
                   up_user.username as updated_by_username
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN patients p ON a.patient_id = p.user_id
            JOIN users d_user ON a.doctor_id = d_user.user_id
            LEFT JOIN insurance_providers ip ON p.insurance_provider_id = ip.id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
            LEFT JOIN users cr_user ON a.created_by = cr_user.user_id
            LEFT JOIN users up_user ON a.updated_by = up_user.user_id
            WHERE a.appointment_id = %s AND a.doctor_id = %s
        """
        cursor.execute(sql, (appointment_id, provider_user_id_int))
        details = cursor.fetchone()
        if details:
             details['type_name'] = details.get('type_name', 'Unknown Type')
             details['default_duration_minutes'] = details.get('default_duration_minutes', 30)
             details['start_time_str'] = str(details['start_time'])[:5] if isinstance(details.get('start_time'), timedelta) else 'N/A'
             details['end_time_str'] = str(details['end_time'])[:5] if isinstance(details.get('end_time'), timedelta) else 'N/A'
             details['appointment_date_str'] = details['appointment_date'].isoformat() if isinstance(details.get('appointment_date'), date) else 'N/A'
             details['location_name'] = details.get('location_name', 'N/A')
             details['location_address'] = details.get('location_address', 'N/A')
             if details.get('date_of_birth') and isinstance(details['date_of_birth'], date):
                 today = date.today()
                 details['patient_age'] = today.year - details['date_of_birth'].year - ((today.month, today.day) < (details['date_of_birth'].month, details['date_of_birth'].day))
             else:
                 details['patient_age'] = None

    except Exception as err:
        logger.error(f"Error fetching appointment details ID {appointment_id} for provider {provider_user_id_int}: {err}", exc_info=True)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return details

# --- Routes ---

@appointments_bp.route('/', methods=['GET'])
@login_required
def list_appointments():
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Provider information is missing. Please re-login or contact support.", "danger")
        return redirect(url_for('auth.login')) # Or a generic portal dashboard

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    view_mode = request.args.get('view', 'upcoming') # Default view
    filter_statuses = request.args.getlist('status') # Can be multiple
    filter_type_id = request.args.get('appointment_type_id', type=int)
    filter_location_id = request.args.get('doctor_location_id', type=int)

    start_date, end_date = None, None
    today = date.today()
    effective_start_date_str, effective_end_date_str = '', ''
    try:
        if view_mode == 'today':
            start_date, end_date = today, today
        elif view_mode == 'week':
            start_of_week = today - timedelta(days=today.weekday()) # Monday as start
            start_date, end_date = start_of_week, start_of_week + timedelta(days=6)
        elif view_mode == 'month':
            start_date = today.replace(day=1)
            next_month_start = (start_date + timedelta(days=32)).replace(day=1)
            end_date = next_month_start - timedelta(days=1)
        elif view_mode == 'upcoming':
            start_date = today
            end_date = None # No specific end date
        elif view_mode == 'past':
            start_date = None # No specific start date
            end_date = today - timedelta(days=1)
        elif view_mode == 'custom':
            if start_date_str: start_date = date.fromisoformat(start_date_str)
            if end_date_str: end_date = date.fromisoformat(end_date_str)
            if start_date and end_date and end_date < start_date:
                flash("End date cannot be before start date for custom range. Showing upcoming.", "warning")
                view_mode = 'upcoming'; start_date = today; end_date = None

        if start_date: effective_start_date_str = start_date.isoformat()
        if end_date: effective_end_date_str = end_date.isoformat()

    except ValueError as e:
        flash(f"Invalid date format or range: {e}. Showing upcoming appointments.", "warning")
        view_mode='upcoming'; start_date=today; end_date=None
        effective_start_date_str = today.isoformat()

    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    filters = {
        'start_date': start_date, 'end_date': end_date,
        'status': filter_statuses if filter_statuses else None,
        'appointment_type_id': filter_type_id,
        'doctor_location_id': filter_location_id
    }
    result = get_paginated_appointments(provider_user_id, page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and result['total'] > 0 else 0

    # Data for filter dropdowns
    all_appointment_types_list = get_all_appointment_types()
    appointment_statuses_enum = get_enum_values_appt_specific('appointments', 'status')
    # Critical: get_all_provider_locations MUST be the real, database-backed function
    provider_locations_list = get_all_provider_locations(provider_user_id)
    if not provider_locations_list:
         flash("Warning: No practice locations found. Please add locations in settings to filter by them or create appointments.", "info")


    return render_template('Doctor_Portal/Appointments/appointment_list.html',
        appointments=result['items'], total_items=result['total'], total_pages=total_pages,
        search_term=search_term, current_page=page, sort_by=sort_by, sort_dir=sort_dir,
        filter_statuses=filter_statuses, filter_type_id=filter_type_id, filter_location_id=filter_location_id,
        start_date_str=effective_start_date_str, end_date_str=effective_end_date_str, view_mode=view_mode,
        appointment_types=all_appointment_types_list,
        appointment_statuses=appointment_statuses_enum,
        provider_locations=provider_locations_list,
        valid_sort_columns=list(VALID_SORT_COLUMNS.keys()))

@appointments_bp.route('/calendar', methods=['GET'])
@login_required
def calendar_view():
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Could not identify provider for calendar view.", "danger")
        return redirect(url_for('auth.login')) # Or a generic portal dashboard
    return render_template('Doctor_Portal/Appointments/calendar_view.html', provider_id=provider_id)

@appointments_bp.route('/<int:appointment_id>', methods=['GET'])
@login_required
def view_appointment(appointment_id):
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Could not identify provider.", "danger")
        return redirect(url_for('auth.login'))

    details = get_appointment_details(appointment_id, provider_user_id)
    if not details:
        flash("Appointment not found or access denied.", "warning")
        return redirect(url_for('.list_appointments'))

    appointment_statuses_enum = get_enum_values_appt_specific('appointments', 'status')
    is_editable = details.get('status') not in TERMINAL_APPT_STATUSES

    return render_template('Doctor_Portal/Appointments/appointment_detail.html',
                           appointment=details,
                           appointment_statuses=appointment_statuses_enum,
                           is_editable=is_editable)

@appointments_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_appointment():
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Could not identify provider.", "danger")
        return redirect(url_for('auth.login'))

    all_appointment_types_list = get_all_appointment_types()
    patients_list = get_all_simple(
        'users', 'user_id', "CONCAT(last_name, ', ', first_name, ' (ID:', user_id, ')')",
        where_clause="user_type='patient' AND account_status='active'",
        order_by="last_name, first_name"
    )
    doctors_list = [{'user_id': provider_user_id, 'name': f"Dr. {current_user.last_name}, {current_user.first_name}"}]
    # CRITICAL: Use the real function for locations
    locations_list = get_all_provider_locations(provider_user_id)
    if not locations_list and request.method == 'GET': # Only flash on initial load if no locations
        flash("Warning: No practice locations found. You must add a location in settings before creating appointments.", "warning")

    appointment_type_durations = {str(appt_type['id']): appt_type['default_duration_minutes'] for appt_type in all_appointment_types_list}
    today_iso = date.today().isoformat()
    form_data = {} # Initialize for GET

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        form_data = request.form.to_dict() # Repopulate form_data on POST attempt

        patient_id = request.form.get('patient_id', type=int)
        doctor_id = provider_user_id # Doctor is always the current logged-in user
        appt_date_str = request.form.get('appointment_date')
        start_time_str = request.form.get('start_time')
        appointment_type_id_str = request.form.get('appointment_type_id')
        doctor_location_id_str = request.form.get('doctor_location_id')
        reason = form_data.get('reason', '').strip() or None
        notes = form_data.get('notes', '').strip() or None

        # --- Validation ---
        if not patient_id: errors.append("Patient is required.")
        if not appointment_type_id_str: errors.append("Appointment type is required.")
        appointment_type_id = int(appointment_type_id_str) if appointment_type_id_str and appointment_type_id_str.isdigit() else None
        if appointment_type_id is None or str(appointment_type_id) not in appointment_type_durations:
            errors.append("Invalid appointment type selected.")

        if not doctor_location_id_str: errors.append("Practice location is required.")
        doctor_location_id = int(doctor_location_id_str) if doctor_location_id_str and doctor_location_id_str.isdigit() else None
        # Validate selected location against the provider's actual locations
        if doctor_location_id is None or not any(loc['doctor_location_id'] == doctor_location_id for loc in locations_list):
             if not any(e.startswith("Invalid practice location") for e in errors): errors.append("Invalid practice location selected.")
        elif not locations_list: # If locations_list is empty, this means no locations exist for the provider
            errors.append("No practice locations available. Please add one in settings.")


        appt_date, start_time, end_time = None, None, None
        if not appt_date_str or not start_time_str:
            errors.append("Appointment date and start time are required.")
        else:
            try:
                appt_date = date.fromisoformat(appt_date_str)
                start_time = time.fromisoformat(start_time_str)
                if datetime.combine(appt_date, start_time) < datetime.now() - timedelta(minutes=1):
                    errors.append("Cannot schedule appointments in the past.")

                if appointment_type_id and str(appointment_type_id) in appointment_type_durations:
                    duration_minutes = appointment_type_durations[str(appointment_type_id)]
                    end_time = (datetime.combine(appt_date, start_time) + timedelta(minutes=duration_minutes)).time()
                elif not any(e.startswith("Invalid appointment type") for e in errors): # Avoid duplicate if type already invalid
                    errors.append("Could not determine appointment duration due to invalid type.")
            except ValueError:
                errors.append("Invalid date or time format for appointment.")

        if errors:
            for err_msg in errors: flash(err_msg, 'danger')
        else: # Proceed to availability check and DB insert if no validation errors
            try:
                # --- Availability Check ---
                conn_check = get_db_connection()
                if not conn_check: raise ConnectionError("DB connection failed for availability check.")
                cursor_check = conn_check.cursor(dictionary=True)
                is_avail, msg = is_slot_available(cursor_check, doctor_id, doctor_location_id, appt_date, start_time, end_time)
                if cursor_check: cursor_check.close()
                if conn_check and conn_check.is_connected(): conn_check.close()

                if not is_avail:
                    flash(f"Selected slot is not available: {msg}", 'danger')
                else:
                    # --- DB Insert ---
                    conn = get_db_connection()
                    if not conn: raise ConnectionError("DB connection failed for insert.")
                    conn.start_transaction()
                    cursor = conn.cursor()
                    sql = """
                        INSERT INTO appointments (patient_id, doctor_id, appointment_date, start_time, end_time,
                                                  appointment_type_id, status, reason, notes,
                                                  doctor_location_id, created_by, updated_by, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    """
                    # Default status for new appointments created by doctor can be 'confirmed'
                    params = (patient_id, doctor_id, appt_date, start_time, end_time,
                              appointment_type_id, 'confirmed', reason, notes,
                              doctor_location_id, provider_user_id, provider_user_id)
                    cursor.execute(sql, params)
                    new_id = cursor.lastrowid
                    conn.commit()
                    flash(f"Appointment (ID: {new_id}) created successfully for {appt_date_str} at {start_time_str}.", "success")
                    return redirect(url_for('.view_appointment', appointment_id=new_id))

            except (mysql.connector.Error, ConnectionError) as db_err:
                logger.error(f"Database error during appointment creation for provider {provider_user_id}: {db_err}", exc_info=True)
                flash("A database error occurred. Please try again.", "danger")
                if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            except Exception as e:
                logger.error(f"Unexpected error during appointment creation for provider {provider_user_id}: {e}", exc_info=True)
                flash("An unexpected error occurred. Please try again.", "danger")
                if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            finally:
                if 'cursor' in locals() and cursor: cursor.close()
                if 'conn' in locals() and conn and conn.is_connected(): conn.close()
                if 'cursor_check' in locals() and cursor_check: cursor_check.close()
                if 'conn_check' in locals() and conn_check and conn_check.is_connected(): conn_check.close()

        # Re-render form on POST error or if availability check failed
        return render_template(
            'Doctor_Portal/Appointments/create_appointment_form.html',
            form_data=form_data,
            patients=patients_list,
            doctors=doctors_list,
            locations=locations_list,
            appointment_types=all_appointment_types_list,
            errors=errors if 'errors' in locals() and errors else [], # Pass errors if they exist
            today_iso=today_iso
        )

    # Initial GET request
    return render_template(
        'Doctor_Portal/Appointments/create_appointment_form.html',
        patients=patients_list,
        doctors=doctors_list,
        locations=locations_list,
        appointment_types=all_appointment_types_list,
        today_iso=today_iso,
        form_data=form_data,
        errors=None
    )

@appointments_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Provider information missing.", "danger")
        return redirect(request.referrer or url_for('.list_appointments'))

    conn = None; cursor = None; success = False; appt_date_str_for_redirect = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status, appointment_date FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, provider_user_id))
        appt = cursor.fetchone()

        if not appt:
            flash("Appointment not found or access denied.", "warning")
        elif appt['status'] in TERMINAL_APPT_STATUSES:
            flash(f"Cannot cancel appointment: Current status is '{appt['status']}'.", "warning")
        else:
            appt_date_str_for_redirect = appt.get('appointment_date').isoformat() if appt.get('appointment_date') else None
            if cursor.is_connected(): cursor.close() # Close dict cursor
            cursor = conn.cursor() # Non-dict cursor for update
            conn.start_transaction()
            cursor.execute("UPDATE appointments SET status = 'canceled', updated_by = %s, updated_at = NOW() WHERE appointment_id = %s",
                           (provider_user_id, appointment_id))
            conn.commit()
            if cursor.rowcount > 0:
                flash("Appointment canceled successfully.", "success")
                success = True
            else:
                flash("Failed to cancel appointment. It might have been modified by another process.", "warning")
                if conn.in_transaction: conn.rollback()

    except Exception as err:
        logger.error(f"Error canceling appointment {appointment_id} for provider {provider_user_id}: {err}", exc_info=True)
        flash("An error occurred while canceling the appointment.", "danger")
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    redirect_url = request.referrer or url_for('.list_appointments')
    if success and request.referrer and f'/appointments/{appointment_id}' in request.referrer:
        redirect_url = url_for('.list_appointments', view='custom', start_date=appt_date_str_for_redirect, end_date=appt_date_str_for_redirect) if appt_date_str_for_redirect else url_for('.list_appointments')
    return redirect(redirect_url)


@appointments_bp.route('/<int:appointment_id>/reschedule', methods=['GET', 'POST'])
@login_required
def reschedule_appointment(appointment_id):
    if not check_doctor_authorization(current_user):
        abort(403)
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        flash("Provider information missing.", "danger")
        return redirect(url_for('auth.login'))

    conn = None; cursor = None; appointment = None; form_data = {} # Initialize form_data
    try:
        conn_fetch = get_db_connection()
        cursor_fetch = conn_fetch.cursor(dictionary=True)
        sql_fetch = """
            SELECT a.*,
                   at.type_name, at.default_duration_minutes,
                   p_user.first_name as p_fname, p_user.last_name as p_lname,
                   dl.location_name
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
            WHERE a.appointment_id = %s AND a.doctor_id = %s
        """
        cursor_fetch.execute(sql_fetch, (appointment_id, provider_user_id))
        appointment = cursor_fetch.fetchone()
        if cursor_fetch: cursor_fetch.close()
        if conn_fetch and conn_fetch.is_connected(): conn_fetch.close()


        if not appointment:
            flash("Appointment not found or access denied.", "warning")
            return redirect(url_for('.list_appointments'))

        if appointment['status'] in TERMINAL_APPT_STATUSES:
            flash(f"Cannot reschedule appointment: Status is '{appointment['status']}'.", "warning")
            return redirect(url_for('.view_appointment', appointment_id=appointment_id))

        # Prepare for template (GET or POST error)
        appointment['appointment_date_str'] = appointment['appointment_date'].isoformat() if appointment.get('appointment_date') else ''
        appointment['start_time_str'] = str(appointment['start_time'])[:5] if isinstance(appointment.get('start_time'), timedelta) else ''
        appointment['default_duration_minutes'] = appointment.get('default_duration_minutes') or 30

        locations_list = get_all_provider_locations(provider_user_id) # CRITICAL: Real locations
        today_iso = date.today().isoformat()
        errors = []

        if request.method == 'POST':
            form_data = request.form.to_dict() # Capture POST data for repopulation
            new_date_str = form_data.get('appointment_date')
            new_time_str = form_data.get('start_time')
            new_location_id_str = form_data.get('doctor_location_id')
            reason = form_data.get('reason', appointment.get('reason', '')).strip() or None
            notes = form_data.get('notes', appointment.get('notes', '')).strip() or None

            # --- Validation ---
            if not new_location_id_str: errors.append("New practice location is required.")
            new_location_id = int(new_location_id_str) if new_location_id_str and new_location_id_str.isdigit() else None
            if new_location_id is None or not any(loc['doctor_location_id'] == new_location_id for loc in locations_list):
                errors.append("Invalid new practice location selected.")

            new_date, new_start_time, new_end_time = None, None, None
            if not new_date_str or not new_time_str:
                errors.append("New appointment date and start time are required.")
            else:
                try:
                    new_date = date.fromisoformat(new_date_str)
                    new_start_time = time.fromisoformat(new_time_str)
                    if datetime.combine(new_date, new_start_time) < datetime.now() - timedelta(minutes=1):
                        errors.append("Cannot reschedule appointments into the past.")

                    duration = appointment['default_duration_minutes'] # Use original duration
                    new_end_time = (datetime.combine(new_date, new_start_time) + timedelta(minutes=duration)).time()
                except ValueError:
                    errors.append("Invalid new date or time format.")

            if errors:
                for err_msg in errors: flash(err_msg, 'danger')
            else: # Proceed if basic validation passes
                try:
                    # --- Availability Check ---
                    conn_check = get_db_connection()
                    if not conn_check: raise ConnectionError("DB connection failed for availability check.")
                    cursor_check = conn_check.cursor(dictionary=True)
                    is_avail, msg = is_slot_available(cursor_check, provider_user_id, new_location_id, new_date, new_start_time, new_end_time, exclude_appointment_id=appointment_id)
                    if cursor_check: cursor_check.close()
                    if conn_check and conn_check.is_connected(): conn_check.close()

                    if not is_avail:
                        flash(f"New slot is not available: {msg}", 'danger')
                    else:
                        # --- DB Update ---
                        conn = get_db_connection()
                        if not conn: raise ConnectionError("DB connection failed for update.")
                        conn.start_transaction()
                        cursor = conn.cursor()
                        sql_upd = """
                            UPDATE appointments
                            SET appointment_date=%s, start_time=%s, end_time=%s, doctor_location_id=%s,
                                status='confirmed', reason=%s, notes=%s,
                                updated_by=%s, updated_at=NOW(), reschedule_count = reschedule_count + 1
                            WHERE appointment_id=%s AND doctor_id=%s
                              AND status NOT IN ('completed','canceled','no-show','rescheduled')
                        """
                        params_upd = (new_date, new_start_time, new_end_time, new_location_id,
                                  reason, notes, provider_user_id,
                                  appointment_id, provider_user_id)
                        cursor.execute(sql_upd, params_upd)

                        if cursor.rowcount == 0:
                            conn.rollback()
                            flash("Update failed. The appointment status might have changed or it no longer exists.", "warning")
                        else:
                            conn.commit()
                            flash("Appointment rescheduled successfully.", "success")
                            return redirect(url_for('.view_appointment', appointment_id=appointment_id))

                except (mysql.connector.Error, ConnectionError) as db_err:
                    logger.error(f"Database error rescheduling appointment {appointment_id}: {db_err}", exc_info=True)
                    flash("A database error occurred. Please try again.", "danger")
                    if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
                except Exception as e:
                    logger.error(f"Unexpected error rescheduling appointment {appointment_id}: {e}", exc_info=True)
                    flash(f"An error occurred: {str(e)}", "danger")
                    if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
                finally:
                    if 'cursor' in locals() and cursor: cursor.close()
                    if 'conn' in locals() and conn and conn.is_connected(): conn.close()
                    if 'cursor_check' in locals() and cursor_check: cursor_check.close()
                    if 'conn_check' in locals() and conn_check and conn_check.is_connected(): conn_check.close()


            # --- Re-render on POST Error or failed availability ---
            # Merge submitted form_data back into appointment dict for repopulation
            # This ensures the form shows the user's attempted changes.
            appointment.update(form_data)
            # Ensure date/time strings are also updated for the form from form_data
            appointment['appointment_date_str'] = new_date_str or appointment['appointment_date_str']
            appointment['start_time_str'] = new_time_str or appointment['start_time_str']
            # Ensure doctor_location_id from form is used for repopulation.
            # It might be None if invalid, template should handle this gracefully (e.g. select prompt)
            appointment['doctor_location_id'] = new_location_id

            return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html',
                                   appointment=appointment, locations=locations_list,
                                   errors=errors, today_iso=today_iso, form_data=form_data)

        # --- GET Request ---
        return render_template('Doctor_Portal/Appointments/reschedule_appointment_form.html',
                               appointment=appointment, locations=locations_list,
                               errors=errors, today_iso=today_iso, form_data=form_data) # Pass form_data for initial GET consistency

    except Exception as e: # Catch errors during initial GET or appointment fetching
        logger.error(f"Error loading reschedule page for appointment {appointment_id}: {e}", exc_info=True)
        flash("An error occurred while loading the reschedule page.", "danger")
        return redirect(url_for('.list_appointments'))
    # No finally needed here as conn_fetch/cursor_fetch are closed within the try


# routes/Doctor_Portal/appointment_management.py

# ... (other imports and functions) ...

# routes/Doctor_Portal/appointment_management.py

# ... (other imports and functions) ...

@appointments_bp.route('/<int:appointment_id>/update_status', methods=['POST'])
@login_required
def update_appointment_status(appointment_id):
    if not check_doctor_authorization(current_user):
        return jsonify(success=False, message="Authorization required."), 403
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        return jsonify(success=False, message="Provider not found."), 400

    new_status = request.json.get('status')
    available_statuses = get_enum_values_appt_specific('appointments', 'status')
    if not new_status or new_status not in available_statuses:
        return jsonify(success=False, message="Invalid status provided."), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            logger.error(f"DB Connection failed for update_appointment_status (Appt ID: {appointment_id})")
            return jsonify(success=False, message="Database connection error."), 500

        # Fetch current status
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT status FROM appointments WHERE appointment_id = %s AND doctor_id = %s",
                       (appointment_id, provider_user_id))
        appt = cursor.fetchone()
        cursor.close() # Close this cursor

        if not appt:
            return jsonify(success=False, message="Appointment not found or access denied."), 404

        # ... (your status validation logic) ...
        if appt['status'] in TERMINAL_APPT_STATUSES and appt['status'] != new_status:
            if new_status not in TERMINAL_APPT_STATUSES:
                return jsonify(success=False, message=f"Appointment status is '{appt['status']}' and cannot be changed to a non-terminal state like '{new_status}'."), 400
        if appt['status'] == new_status:
            return jsonify(success=True, message="Status is already set to the desired value.", new_status=new_status), 200


        # Perform the update - if autocommit is False, this will start a transaction
        cursor = conn.cursor() # Get a new cursor for the DML operation
        
        # REMOVED: conn.start_transaction() - The UPDATE will start one if autocommit is false.
        
        cursor.execute("UPDATE appointments SET status=%s, updated_by=%s, updated_at=NOW() WHERE appointment_id=%s AND doctor_id=%s",
                       (new_status, provider_user_id, appointment_id, provider_user_id))
        
        if cursor.rowcount > 0:
            conn.commit() # Commit the transaction started by the UPDATE
            return jsonify(success=True, message="Appointment status updated successfully.", new_status=new_status)
        else:
            # No rows affected could mean appointment not found with that doctor_id, or status was already as desired
            # or it was already in a terminal state that prevented update by some other logic (not present here but possible in complex systems)
            conn.rollback() # Rollback if no rows were updated (though not strictly necessary if no transaction was started)
            logger.warning(f"Update status for appointment {appointment_id} affected 0 rows. Current status in DB may differ or WHERE clause didn't match.")
            return jsonify(success=False, message="Failed to update status. Appointment may not exist or conditions not met."), 409

    except mysql.connector.Error as db_err:
        logger.error(f"DB error updating status for appointment {appointment_id} to {new_status}: {db_err}", exc_info=True)
        if conn and conn.is_connected(): # Check if conn exists before checking in_transaction
            try:
                # Only rollback if a transaction was indeed active.
                # Hard to tell definitively without checking conn.in_transaction if available,
                # or by assuming any DML implies a transaction if autocommit is off.
                # If autocommit is on, rollback does nothing.
                # For safety with mysql.connector, explicitly check and rollback.
                if conn.in_transaction: # This attribute should exist on the connection object
                    conn.rollback()
                    logger.info(f"Rolled back transaction for appointment {appointment_id} due to DB error.")
            except Exception as rb_err:
                logger.error(f"Error during rollback attempt: {rb_err}")
        return jsonify(success=False, message=f"Database error: {db_err.msg}"), 500
    except Exception as err:
        logger.error(f"Error updating status for appointment {appointment_id} to {new_status}: {err}", exc_info=True)
        if conn and conn.is_connected():
            try:
                if conn.in_transaction:
                    conn.rollback()
                    logger.info(f"Rolled back transaction for appointment {appointment_id} due to general error.")
            except Exception as rb_err:
                logger.error(f"Error during rollback attempt: {rb_err}")
        return jsonify(success=False, message="A server error occurred while updating status."), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
# ... (rest of the file)
@appointments_bp.route('/<int:appointment_id>/update_notes', methods=['POST'])
@login_required
def update_appointment_notes(appointment_id):
    if not check_doctor_authorization(current_user):
        return jsonify(success=False, message="Authorization required."), 403
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        return jsonify(success=False, message="Provider not found."), 400

    new_notes = request.json.get('notes', '').strip() or None

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, provider_user_id))
        if not cursor.fetchone():
            return jsonify(success=False, message="Appointment not found or access denied."), 404

        if cursor.is_connected(): cursor.close() # Close dict cursor
        cursor = conn.cursor() # Standard cursor for update
        conn.start_transaction()
        cursor.execute("UPDATE appointments SET notes=%s, updated_by=%s, updated_at=NOW() WHERE appointment_id=%s",
                       (new_notes, provider_user_id, appointment_id))
        conn.commit()
        return jsonify(success=True, message="Appointment notes updated successfully.")
    except Exception as err:
        logger.error(f"Error updating notes for appointment {appointment_id}: {err}", exc_info=True)
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        return jsonify(success=False, message="A server error occurred while updating notes."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@appointments_bp.route('/feed', methods=['GET'])
@login_required
def appointment_data_feed():
    if not check_doctor_authorization(current_user):
        return jsonify([])
    provider_user_id = get_provider_id(current_user)
    if provider_user_id is None:
        return jsonify({"error": "Provider not found."}), 400

    start_str, end_str = request.args.get('start'), request.args.get('end')
    if not (start_str and end_str):
        return jsonify({"error": "Start and end date parameters are required."}), 400

    try:
        start_date = date.fromisoformat(start_str.split('T')[0])
        end_date_fc = date.fromisoformat(end_str.split('T')[0]) # FullCalendar end is exclusive for dayGrid
    except ValueError:
        return jsonify({"error": "Invalid date format for start or end date."}), 400

    conn = None; cursor = None; events = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT a.appointment_id as id,
                   CONCAT(p_user.last_name, ', ', p_user.first_name) as title_patient,
                   at.type_name,
                   a.appointment_date, a.start_time, a.end_time, a.status,
                   dl.location_name
            FROM appointments a
            JOIN users p_user ON a.patient_id = p_user.user_id
            LEFT JOIN doctor_locations dl ON a.doctor_location_id = dl.doctor_location_id
            LEFT JOIN appointment_types at ON a.appointment_type_id = at.type_id
            WHERE a.doctor_id = %s
              AND a.appointment_date >= %s
              AND a.appointment_date < %s  -- Use < for end_date as FullCalendar typically provides the start of the day *after* the range for all-day slots
              AND a.status NOT IN ('canceled')
        """
        cursor.execute(sql, (provider_user_id, start_date, end_date_fc)) # Use end_date_fc from FullCalendar
        appointments = cursor.fetchall()

        status_colors = { # Ensure these match your CSS color scheme if using class-based coloring
            'confirmed': '#198754', 'completed': '#6c757d', 'no-show': '#ffc107',
            'rescheduled': '#fd7e14', 'scheduled': '#0d6efd', 'pending': '#0dcaf0'
        }

        for appt in appointments:
            try:
                if not isinstance(appt['start_time'], timedelta) or not isinstance(appt['end_time'], timedelta):
                    logger.warning(f"Skipping appointment {appt['id']} due to invalid time data in feed.")
                    continue
                start_dt = datetime.combine(appt['appointment_date'], time.min) + appt['start_time']
                end_dt = datetime.combine(appt['appointment_date'], time.min) + appt['end_time']
                start_dt_str, end_dt_str = start_dt.isoformat(), end_dt.isoformat()
            except (TypeError, ValueError) as time_err:
                logger.warning(f"Skipping appointment {appt['id']} due to time formatting error in feed: {time_err}")
                continue

            loc_info = f" @ {appt['location_name']}" if appt.get('location_name') else ""
            type_name_display = appt.get('type_name', 'Appointment')
            event_title = f"{appt['title_patient']} ({type_name_display}{loc_info})"

            event = {
                'id': appt['id'],
                'title': event_title,
                'start': start_dt_str,
                'end': end_dt_str,
                'color': status_colors.get(appt['status'], '#6c757d'), # Default color
                'url': url_for('.view_appointment', appointment_id=appt['id']),
                'extendedProps': {
                    'status': appt['status'],
                    'type': type_name_display,
                    'location': appt.get('location_name', 'N/A')
                }
            }
            events.append(event)
        return jsonify(events)

    except Exception as err:
        logger.error(f"Error generating appointment data feed for provider {provider_user_id}: {err}", exc_info=True)
        return jsonify({"error": "A server error occurred while fetching appointment data."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()