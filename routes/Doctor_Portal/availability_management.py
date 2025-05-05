# routes/Doctor_Portal/availability_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, abort # Removed flash - prefer JSON responses for AJAX
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import time, date, datetime, timedelta
import logging

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

# --- Blueprint Definition ---
availability_bp = Blueprint(
    'availability',
    __name__,
    url_prefix='/portal/availability',
    template_folder='../../templates'
)

# *** Get doctor's specific locations (Kept here as availability module depends on it) ***
def get_all_provider_locations(provider_id):
     """Fetches active locations defined by the specific provider."""
     # ... (Implementation remains the same as the previous version) ...
     conn = None; cursor = None; locations = []
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Conn failed.")
         cursor = conn.cursor(dictionary=True)
         query = "SELECT doctor_location_id, location_name, address, city, state, phone_number, is_primary FROM doctor_locations WHERE doctor_id = %s AND is_active = TRUE ORDER BY location_name ASC"
         cursor.execute(query, (provider_id,))
         locations = cursor.fetchall()
     except (mysql.connector.Error, ConnectionError) as err: logger.error(f"DB Error get provider locs P:{provider_id}: {err}")
     except Exception as e: logger.error(f"Error get provider locs P:{provider_id}: {e}", exc_info=True)
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()
     return locations

# *** Get all location slots (Keep as is) ***
def get_all_provider_location_slots(provider_id):
    """Fetches all recurring weekly availability slots for all locations of a provider."""
    # ... (Implementation remains the same as the previous version) ...
    conn = None; cursor = None; slots = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn failed.")
        cursor = conn.cursor(dictionary=True)
        query = "SELECT dla.location_availability_id, dla.day_of_week, dla.start_time, dla.end_time, dl.doctor_location_id, dl.location_name, dl.address, dl.city, dl.state FROM doctor_location_availability dla JOIN doctor_locations dl ON dla.doctor_location_id = dl.doctor_location_id WHERE dl.doctor_id = %s AND dl.is_active = TRUE ORDER BY dl.location_name, dla.day_of_week, dla.start_time"
        cursor.execute(query, (provider_id,))
        slots = cursor.fetchall()
        for slot in slots: # Format times
            if isinstance(slot.get('start_time'), timedelta): slot['start_time'] = str(slot['start_time'])[:5]
            if isinstance(slot.get('end_time'), timedelta): slot['end_time'] = str(slot['end_time'])[:5]
    except (mysql.connector.Error, ConnectionError, Exception) as e: logger.error(f"DB Error get location slots P:{provider_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return slots

# *** Get overrides (Keep as is) ***
def get_overrides(provider_id, start_date_str=None, end_date_str=None):
    """Fetches date-specific overrides for a provider, optionally within a date range."""
    # ... (Implementation remains the same as the previous version, joining doctor_locations) ...
    conn = None; cursor = None; filters = [provider_id]; sql_where_clause = ""
    # ... date filter logic ...
    try: # Validation
        start_date, end_date = None, None
        if start_date_str: start_date = date.fromisoformat(start_date_str); sql_where_clause += " AND dao.override_date >= %s"; filters.append(start_date)
        if end_date_str: end_date = date.fromisoformat(end_date_str); sql_where_clause += " AND dao.override_date <= %s"; filters.append(end_date)
    except ValueError: logger.warning(f"Invalid date format P:{provider_id}"); sql_where_clause = ""; filters = [provider_id]
    try: # DB Fetch
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Conn failed.")
        cursor = conn.cursor(dictionary=True)
        query = f"SELECT dao.override_id, dao.override_date, dao.start_time, dao.end_time, dao.is_unavailable, dao.reason, dao.doctor_location_id, dl.location_name FROM doctor_availability_overrides dao LEFT JOIN doctor_locations dl ON dao.doctor_location_id = dl.doctor_location_id AND dl.doctor_id = dao.doctor_id WHERE dao.doctor_id = %s {sql_where_clause} ORDER BY dao.override_date, dao.start_time"
        cursor.execute(query, tuple(filters)); overrides = cursor.fetchall()
        for override in overrides: # Formatting
             if isinstance(override.get('start_time'), timedelta): override['start_time'] = str(override['start_time'])[:5]
             if isinstance(override.get('end_time'), timedelta): override['end_time'] = str(override['end_time'])[:5]
             if isinstance(override.get('override_date'), date): override['override_date'] = override['override_date'].isoformat()
             if override.get('doctor_location_id') is None: override['location_name'] = None
        return overrides
    except (mysql.connector.Error, ConnectionError, Exception) as err: logger.error(f"Error getting overrides P:{provider_id}: {err}", exc_info=True); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# *** Check location weekly slot overlap (Keep as is) ***
def check_location_weekly_slot_overlap(doctor_location_id, day_of_week, new_start_time_str, new_end_time_str, exclude_id=None):
    """Checks if a new weekly slot overlaps with existing ones for the specific location."""
    # ... (Implementation remains the same as the previous version) ...
    conn = None; cursor = None; overlap = True
    try:
        new_start_time = time.fromisoformat(new_start_time_str); new_end_time = time.fromisoformat(new_end_time_str)
        if not doctor_location_id: raise ValueError("Loc ID required.")
        conn = get_db_connection(); cursor = conn.cursor()
        query = "SELECT 1 FROM doctor_location_availability WHERE doctor_location_id = %s AND day_of_week = %s AND (%s < end_time AND %s > start_time)"
        params = [doctor_location_id, day_of_week, new_start_time, new_end_time]
        if exclude_id: query += " AND location_availability_id != %s"; params.append(exclude_id)
        query += " LIMIT 1"
        cursor.execute(query, tuple(params)); overlap = cursor.fetchone() is not None
    except (ValueError, mysql.connector.Error, Exception) as e: logger.error(f"Error check weekly overlap DL_ID:{doctor_location_id}: {e}", exc_info=True); overlap = True # Fail safe
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return overlap


# *** Check override overlap (Keep as is) ***
def check_override_overlap(provider_id, override_date, doctor_location_id=None, start_time_str=None, end_time_str=None, exclude_id=None):
    """Checks if a new override overlaps with existing ones, considering location."""
    # ... (Implementation remains the same as the previous version) ...
    conn=None; cursor=None; overlap=True
    try:
        override_date_obj = date.fromisoformat(str(override_date))
        start_time_obj = time.fromisoformat(start_time_str) if start_time_str else None
        end_time_obj = time.fromisoformat(end_time_str) if end_time_str else None
        current_location_id = int(doctor_location_id) if doctor_location_id is not None else None
        conn = get_db_connection(); cursor = conn.cursor()
        location_condition = "((dao.doctor_location_id = %(current_loc_id)s AND %(current_loc_id)s IS NOT NULL) OR dao.doctor_location_id IS NULL OR %(current_loc_id)s IS NULL)"
        params = {'provider_id': provider_id, 'override_date': override_date_obj, 'current_loc_id': current_location_id}
        time_condition = " "
        if start_time_obj: time_condition = "AND (dao.start_time IS NULL OR (%(start_time)s < dao.end_time AND %(end_time)s > dao.start_time))"; params['start_time'] = start_time_obj; params['end_time'] = end_time_obj
        query = f"SELECT 1 FROM doctor_availability_overrides dao WHERE dao.doctor_id = %(provider_id)s AND dao.override_date = %(override_date)s AND {location_condition} {time_condition}"
        if exclude_id: query += " AND dao.override_id != %(exclude_id)s"; params['exclude_id'] = exclude_id
        query += " LIMIT 1"
        cursor.execute(query, params); overlap = cursor.fetchone() is not None
    except (ValueError, mysql.connector.Error, Exception) as e: logger.error(f"Err check override overlap P:{provider_id} L:{doctor_location_id} D:{override_date}: {e}", exc_info=True); overlap=True # Fail safe
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return overlap

# *** Get daily limits (Keep as is) ***
def get_daily_limits(provider_id, start_date_str=None, end_date_str=None):
    """Fetches daily appointment limits for a provider, optionally within a date range."""
     # ... (Implementation remains the same as the previous version) ...
    conn = None; cursor = None; limits = []
    filters = {'provider_id': provider_id}; sql_where_clause = ""
    # ... date filter logic ...
    try: # Validation
        if start_date_str: filters['start_date'] = date.fromisoformat(start_date_str); sql_where_clause += " AND pdl.limit_date >= %(start_date)s"
        if end_date_str: filters['end_date'] = date.fromisoformat(end_date_str); sql_where_clause += " AND pdl.limit_date <= %(end_date)s"
    except ValueError: logger.warning(f"Invalid date P:{provider_id}"); sql_where_clause = ""; filters={'provider_id':provider_id}
    try: # DB Fetch
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        query = f"SELECT pdl.provider_daily_limit_id, pdl.limit_date, pdl.max_appointments, pdl.doctor_location_id, dl.location_name FROM provider_daily_limits pdl JOIN doctor_locations dl ON pdl.doctor_location_id = dl.doctor_location_id WHERE pdl.provider_id = %(provider_id)s AND dl.doctor_id = %(provider_id)s {sql_where_clause} ORDER BY pdl.limit_date ASC, dl.location_name ASC"
        cursor.execute(query, filters); limits = cursor.fetchall()
        for limit in limits:
             if isinstance(limit.get('limit_date'), date): limit['limit_date'] = limit['limit_date'].isoformat()
        return limits
    except (mysql.connector.Error, Exception) as e: logger.error(f"DB Error get daily limits P:{provider_id}: {e}", exc_info=True); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# *** Add or update daily limit (Keep as is) ***
def add_or_update_daily_limit(provider_id, doctor_location_id, limit_date_str, max_appointments):
    """Adds a new daily limit or updates an existing one using ON DUPLICATE KEY UPDATE."""
    # ... (Implementation remains the same as the previous version) ...
    conn = None; cursor = None; result_row = None; success=False; message=""
    try:
        limit_date_obj = date.fromisoformat(limit_date_str); max_appts_int = int(max_appointments); doc_loc_id_int = int(doctor_location_id)
        if max_appts_int < 0: raise ValueError("Max appointments non-negative.")
        if not doc_loc_id_int: raise ValueError("Location required.")
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True); conn.start_transaction()
        cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s", (doc_loc_id_int, provider_id))
        if not cursor.fetchone(): conn.rollback(); raise ValueError(f"Invalid/unauthorized Loc ID: {doc_loc_id_int}")
        query = "INSERT INTO provider_daily_limits (provider_id, doctor_location_id, limit_date, max_appointments, created_at, updated_at) VALUES (%(pid)s, %(dlid)s, %(date)s, %(max)s, NOW(), NOW()) ON DUPLICATE KEY UPDATE max_appointments = VALUES(max_appointments), updated_at = NOW()"
        params = {'pid': provider_id, 'dlid': doc_loc_id_int, 'date': limit_date_obj, 'max': max_appts_int}
        cursor.execute(query, params); conn.commit()
        cursor.execute("SELECT pdl.*, dl.location_name FROM provider_daily_limits pdl JOIN doctor_locations dl ON pdl.doctor_location_id = dl.doctor_location_id WHERE pdl.provider_id = %s AND pdl.doctor_location_id = %s AND pdl.limit_date = %s", (provider_id, doc_loc_id_int, limit_date_obj))
        result_row = cursor.fetchone()
        if result_row:
            if isinstance(result_row.get('limit_date'), date): result_row['limit_date'] = result_row['limit_date'].isoformat()
            success=True; message="Daily limit saved."
        else: logger.error(f"Failed retrieve limit P:{provider_id} L:{doc_loc_id_int} D:{limit_date_str}"); message="Failed retrieve saved limit."
    except ValueError as ve: message=str(ve)
    except mysql.connector.Error as err:
        logger.error(f"DB Err save limit P:{provider_id} L:{doctor_location_id}: {err}", exc_info=True)
        msg = f"DB error: {err.msg}" if hasattr(err, 'msg') and err.msg else "DB error."
        if err.errno == 1452:
            msg = "Invalid Location."
        message = msg
    except Exception as e: logger.error(f"Error save limit P:{provider_id} L:{doctor_location_id}: {e}", exc_info=True); message="Unexpected error."
    finally:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback() # Rollback if commit didn't happen or after fetch failure
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return success, message, result_row


# *** Delete daily limit (Keep as is) ***
def delete_daily_limit(limit_id, provider_id):
    """Deletes a specific daily limit entry, ensuring ownership."""
    # ... (Implementation remains the same as the previous version) ...
    conn = None; cursor = None; success=False; message=""
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = "DELETE FROM provider_daily_limits WHERE provider_daily_limit_id = %s AND provider_id = %s"
        cursor.execute(query, (limit_id, provider_id)); rows_affected = cursor.rowcount; conn.commit()
        if rows_affected == 0:
             cursor.execute("SELECT 1 FROM provider_daily_limits WHERE provider_daily_limit_id = %s", (limit_id,))
             if cursor.fetchone(): message="Cannot delete: Not owned."
             else: message="Limit not found."
        else: success=True; message="Daily limit deleted."
    except mysql.connector.Error as err: logger.error(f"DB Err del limit ID {limit_id} P:{provider_id}: {err}"); message=f"DB error: {err.msg}"
    except Exception as e: logger.error(f"Error del limit ID {limit_id} P:{provider_id}: {e}", exc_info=True); message="Unexpected error."
    finally:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return success, message


# --- AJAX Handlers (Keep as is - using updated helper functions) ---

@availability_bp.route('/weekly', methods=['POST'])
@login_required
def add_weekly_slot_route():
    # ... (Implementation remains the same as the previous version, using updated helpers) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    conn = None; cursor = None
    try:
        doctor_location_id = request.form.get('doctor_location_id', type=int)
        day_of_week = request.form.get('day_of_week', type=int)
        start_time_str = request.form.get('start_time'); end_time_str = request.form.get('end_time')
        if doctor_location_id is None: raise ValueError("Location req.")
        # ... other validation ...
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s", (doctor_location_id, provider_id))
        if not cursor.fetchone(): return jsonify(success=False, message="Invalid loc."), 403
        cursor.close()
        if check_location_weekly_slot_overlap(doctor_location_id, day_of_week, start_time_str, end_time_str): return jsonify(success=False, message="Overlap."), 400
        cursor = conn.cursor(dictionary=True)
        query = "INSERT INTO doctor_location_availability (doctor_location_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (doctor_location_id, day_of_week, start_time_str, end_time_str)); conn.commit(); new_slot_id = cursor.lastrowid
        cursor.execute("SELECT location_name FROM doctor_locations WHERE doctor_location_id = %s", (doctor_location_id,)); loc_info = cursor.fetchone(); location_name = loc_info.get('location_name', 'Unk') if loc_info else 'Unk'
        return jsonify(success=True, message="Slot added.", slot={"location_availability_id": new_slot_id, "doctor_location_id": doctor_location_id, "location_name": location_name, "day_of_week": day_of_week, "start_time": start_time_str, "end_time": end_time_str}), 201
    except ValueError as ve: return jsonify(success=False, message=str(ve)), 400
    except mysql.connector.Error as err: # ... handle DB error ...
        logger.error(f"DB Err add weekly P:{provider_id} L:{request.form.get('doctor_location_id')}: {err}")
        if err.errno == 1452:
            return jsonify(success=False, message="Invalid Loc"), 400
        return jsonify(success=False, message="DB error"), 500
    except Exception as e: # ... handle unexpected error ...
        logger.error(f"Err add weekly P:{provider_id} L:{request.form.get('doctor_location_id')}: {e}", exc_info=True); return jsonify(success=False, message="Error"), 500
    finally: # ... close conn ...
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


# Note: 'id' here refers to 'location_availability_id'
@availability_bp.route('/weekly/<int:location_availability_id>', methods=['DELETE'])
@login_required
def delete_weekly_slot_route(location_availability_id):
    # ... (Implementation remains the same as the previous version, using updated helpers) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = "DELETE dla FROM doctor_location_availability dla JOIN doctor_locations dl ON dla.doctor_location_id = dl.doctor_location_id WHERE dla.location_availability_id = %s AND dl.doctor_id = %s"
        cursor.execute(query, (location_availability_id, provider_id))
        if cursor.rowcount == 0:
            cursor.execute("SELECT 1 FROM doctor_location_availability WHERE location_availability_id = %s", (location_availability_id,))
            status_code = 403 if cursor.fetchone() else 404; return jsonify(success=False, message="Not found/auth."), status_code
        conn.commit(); return jsonify(success=True, message="Slot deleted."), 200
    except mysql.connector.Error as err: logger.error(f"DB Err del weekly ID {location_availability_id} P:{provider_id}: {err}"); return jsonify(success=False, message="DB error."), 500
    except Exception as e: logger.error(f"Err del weekly ID {location_availability_id} P:{provider_id}: {e}", exc_info=True); return jsonify(success=False, message="Error."), 500
    finally: # ... close conn ...
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@availability_bp.route('/override', methods=['POST'])
@login_required
def add_override_route():
    # ... (Implementation remains the same as the previous version, using updated helpers) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    conn = None; cursor = None; location_name = None
    try:
        override_date_str = request.form.get('override_date')
        doctor_location_id_str = request.form.get('doctor_location_id', '').strip(); doctor_location_id = int(doctor_location_id_str) if doctor_location_id_str else None
        # ... other form data ...
        # ... validation ...
        if doctor_location_id is not None: # Verify ownership
            conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT location_name FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s", (doctor_location_id, provider_id))
            loc_info = cursor.fetchone();
            if not loc_info: return jsonify(success=False, message="Invalid loc."), 403
            location_name = loc_info.get('location_name'); cursor.close(); conn.close() # Close check conn early
        # ... overlap check ...
        if check_override_overlap(provider_id, override_date_str, doctor_location_id, request.form.get('start_time'), request.form.get('end_time')): return jsonify(success=False, message="Overlap."), 400
        # ... DB insert ...
        conn = get_db_connection(); cursor = conn.cursor()
        query = "INSERT INTO doctor_availability_overrides (doctor_id, doctor_location_id, override_date, start_time, end_time, is_unavailable, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        # ... execute, commit ...
        # ... return JSON with location_name if available ...
        # --- Simplified Example (replace with full previous logic) ---
        cursor.execute(query, (...)); conn.commit(); new_id = cursor.lastrowid
        return jsonify(success=True, message="Override added.", override={"override_id": new_id, "doctor_location_id": doctor_location_id, "location_name": location_name, "...": "..."}), 201
        # --- End Simplified ---
    except ValueError as ve: return jsonify(success=False, message=str(ve)), 400
    except mysql.connector.Error as err: # ... handle DB error ...
        logger.error(f"DB Err add override P:{provider_id} L:{request.form.get('doctor_location_id')}: {err}")
        if err.errno == 1452:
            return jsonify(success=False, message="Invalid Loc."), 400
        return jsonify(success=False, message="DB error"), 500
    except Exception as e: # ... handle unexpected error ...
         logger.error(f"Err add override P:{provider_id} L:{request.form.get('doctor_location_id')}: {e}", exc_info=True); return jsonify(success=False, message="Error."), 500
    finally: # ... close conn ...
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@availability_bp.route('/override/<int:override_id>', methods=['DELETE'])
@login_required
def delete_override_route(override_id):
    # ... (Implementation remains the same as the previous version) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        query = "DELETE FROM doctor_availability_overrides WHERE override_id = %s AND doctor_id = %s"
        cursor.execute(query, (override_id, provider_id))
        if cursor.rowcount == 0: # Check ownership/existence
            cursor.execute("SELECT 1 FROM doctor_availability_overrides WHERE override_id = %s", (override_id,))
            status_code = 403 if cursor.fetchone() else 404; return jsonify(success=False, message="Not found/auth."), status_code
        conn.commit(); return jsonify(success=True, message="Override deleted."), 200
    except mysql.connector.Error as err: logger.error(f"DB Err del override ID {override_id} P:{provider_id}: {err}"); return jsonify(success=False, message="DB error."), 500
    except Exception as e: logger.error(f"Err del override ID {override_id} P:{provider_id}: {e}", exc_info=True); return jsonify(success=False, message="Error."), 500
    finally: # ... close conn ...
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@availability_bp.route('/limits/save', methods=['POST'])
@login_required
def save_daily_limit_route():
    # ... (Implementation remains the same as the previous version, using updated helpers) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    limit_date_str = request.form.get('limit_date')
    doctor_location_id = request.form.get('doctor_location_id', type=int)
    max_appointments = request.form.get('max_appointments')
    if not limit_date_str or doctor_location_id is None or max_appointments is None: return jsonify(success=False, message="Fields required."), 400
    success, message, result_row = add_or_update_daily_limit(provider_id, doctor_location_id, limit_date_str, max_appointments)
    status_code = 200 if success else 400; # Set default error code
    if not success and ("Database error" in message or "unexpected" in message.lower()): status_code = 500
    elif not success and ("Invalid or unauthorized Location" in message): status_code = 403
    return jsonify(success=success, message=message, limit=result_row if success else None), status_code


@availability_bp.route('/limits/<int:limit_id>', methods=['DELETE'])
@login_required
def delete_daily_limit_route(limit_id):
    # ... (Implementation remains the same as the previous version) ...
    if not check_provider_authorization(current_user): return jsonify(success=False, message="Denied."), 403
    provider_id = get_provider_id(current_user); #... handle None ...
    success, message = delete_daily_limit(limit_id, provider_id)
    status_code = 200 if success else 404 # Default to Not Found
    if not success: # Adjust code based on message
        if "not owned" in message.lower(): status_code = 403
        elif "Database error" in message.lower(): status_code = 500
        elif "unexpected" in message.lower(): status_code = 500
    return jsonify(success=success, message=message), status_code