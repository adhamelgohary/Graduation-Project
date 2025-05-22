# routes/Doctor_Portal/availability_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, abort, render_template, flash, url_for, redirect
)
from flask_login import login_required, current_user
from db import get_db_connection # Assuming your db.py provides this
from datetime import time, date, datetime, timedelta
import logging

try:
    from .utils import check_doctor_authorization, get_provider_id
except (ImportError, ValueError) as e:
    logging.getLogger(__name__).error(f"CRITICAL: Failed to import utils. Details: {e}", exc_info=True)
    def check_doctor_authorization(user): return False
    def get_provider_id(user): return None

logger = logging.getLogger(__name__)

availability_bp = Blueprint(
    'availability',
    __name__,
    url_prefix='/portal/availability',
    template_folder='../../templates' 
)

# --- Database Helper Functions (Read-only, no explicit transactions here) ---
def get_all_provider_locations(provider_id):
    conn = None; cursor = None; locations = []
    try:
        conn = get_db_connection()
        if not conn:
            logger.error(f"DB Connection failed for get_all_provider_locations P:{provider_id}")
            raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True)
        query = "SELECT doctor_location_id, location_name, address, city, state, phone_number, is_primary FROM doctor_locations WHERE doctor_id = %s AND is_active = TRUE ORDER BY location_name ASC"
        cursor.execute(query, (provider_id,))
        locations = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error get provider locs P:{provider_id}: {err}", exc_info=True)
        raise # Re-raise to be caught by the calling route
    except Exception as e:
        logger.error(f"Unexpected error in get_all_provider_locations P:{provider_id}: {e}", exc_info=True)
        raise # Re-raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return locations

def get_all_provider_location_slots(provider_id):
    conn = None; cursor = None; slots = []
    try:
        conn = get_db_connection()
        if not conn:
            logger.error(f"DB Connection failed for get_all_provider_location_slots P:{provider_id}")
            raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT dla.location_availability_id, dla.day_of_week, dla.start_time, dla.end_time,
                   dl.doctor_location_id, dl.location_name, dl.address, dl.city, dl.state
            FROM doctor_location_availability dla
            JOIN doctor_locations dl ON dla.doctor_location_id = dl.doctor_location_id
            WHERE dl.doctor_id = %s AND dl.is_active = TRUE
            ORDER BY dl.location_name, dla.day_of_week, dla.start_time
        """
        cursor.execute(query, (provider_id,))
        slots = cursor.fetchall()
        for slot in slots:
            if isinstance(slot.get('start_time'), timedelta):
                slot['start_time'] = (datetime.min + slot['start_time']).strftime('%H:%M')
            if isinstance(slot.get('end_time'), timedelta):
                slot['end_time'] = (datetime.min + slot['end_time']).strftime('%H:%M')
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error get location slots P:{provider_id}: {err}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_all_provider_location_slots P:{provider_id}: {e}", exc_info=True)
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return slots

def get_overrides(provider_id, start_date_str=None, end_date_str=None):
    conn = None; cursor = None; overrides = []
    filters = [provider_id]; sql_where_clause = ""
    try:
        if start_date_str:
            start_date = date.fromisoformat(start_date_str)
            sql_where_clause += " AND dao.override_date >= %s"; filters.append(start_date)
        if end_date_str:
            end_date = date.fromisoformat(end_date_str)
            sql_where_clause += " AND dao.override_date <= %s"; filters.append(end_date)
    except ValueError:
        logger.warning(f"Invalid date format for override filter P:{provider_id}. start: {start_date_str}, end: {end_date_str}")
        sql_where_clause = ""; filters = [provider_id]

    try:
        conn = get_db_connection()
        if not conn:
            logger.error(f"DB Connection failed for get_overrides P:{provider_id}")
            raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True)
        query = f"""
            SELECT dao.override_id, dao.override_date, dao.start_time, dao.end_time,
                   dao.is_unavailable, dao.reason, dao.doctor_location_id,
                   dl.location_name
            FROM doctor_availability_overrides dao
            LEFT JOIN doctor_locations dl ON dao.doctor_location_id = dl.doctor_location_id AND dl.doctor_id = dao.doctor_id
            WHERE dao.doctor_id = %s {sql_where_clause}
            ORDER BY dao.override_date, dao.start_time
        """
        cursor.execute(query, tuple(filters))
        overrides = cursor.fetchall()
        for override in overrides:
            if isinstance(override.get('start_time'), timedelta):
                override['start_time'] = (datetime.min + override['start_time']).strftime('%H:%M')
            if isinstance(override.get('end_time'), timedelta):
                override['end_time'] = (datetime.min + override['end_time']).strftime('%H:%M')
            if isinstance(override.get('override_date'), date):
                override['override_date'] = override['override_date'].isoformat()
            if override.get('doctor_location_id') is None and override.get('location_name') is None:
                override['location_name'] = "All Locations (General)"
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error getting overrides P:{provider_id}: {err}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_overrides P:{provider_id}: {e}", exc_info=True)
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return overrides

def check_location_weekly_slot_overlap(doctor_location_id, day_of_week, new_start_time_str, new_end_time_str, exclude_id=None):
    conn = None; cursor = None; overlap = True 
    try:
        new_start_time = time.fromisoformat(new_start_time_str)
        new_end_time = time.fromisoformat(new_end_time_str)
        if new_start_time >= new_end_time:
            raise ValueError("Start time must be before end time.")
        if not doctor_location_id:
            raise ValueError("Location ID required for weekly overlap check.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for overlap check.")
        
        with conn.cursor() as cursor_check: # Use 'with' for read-only cursor
            query = """SELECT 1 FROM doctor_location_availability
                       WHERE doctor_location_id = %s AND day_of_week = %s
                       AND (%s < end_time AND %s > start_time)"""
            params = [doctor_location_id, day_of_week, new_start_time, new_end_time]
            if exclude_id:
                query += " AND location_availability_id != %s"
                params.append(exclude_id)
            query += " LIMIT 1"
            cursor_check.execute(query, tuple(params))
            overlap = cursor_check.fetchone() is not None
    except ValueError as ve: 
        logger.warning(f"Validation error during weekly overlap check for DL_ID:{doctor_location_id}: {ve}")
        # Overlap remains true (safe default)
    except (mysql.connector.Error, ConnectionError) as db_err:
        logger.error(f"DB/Connection Error weekly overlap DL_ID:{doctor_location_id}: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error check weekly overlap DL_ID:{doctor_location_id}: {e}", exc_info=True)
    finally:
        # Cursor is auto-closed by 'with' statement
        if conn and conn.is_connected(): conn.close()
    return overlap

def check_override_overlap(provider_id, override_date_str, doctor_location_id=None, start_time_str=None, end_time_str=None, exclude_id=None):
    conn = None; cursor = None; overlap = True
    try:
        override_date_obj = date.fromisoformat(override_date_str)
        start_time_obj = time.fromisoformat(start_time_str) if start_time_str else time.min 
        end_time_obj = time.fromisoformat(end_time_str) if end_time_str else time.max     

        if start_time_str and end_time_str and start_time_obj >= end_time_obj:
             raise ValueError("Start time must be before end time for override.")

        current_location_id_int = int(doctor_location_id) if doctor_location_id is not None else None

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for override overlap check.")
        
        with conn.cursor() as cursor_check:
            params = {
                'provider_id': provider_id, 'override_date': override_date_obj,
                'start_time': start_time_obj, 'end_time': end_time_obj,
                'current_loc_id': current_location_id_int
            }
            query = """
                SELECT 1 FROM doctor_availability_overrides dao
                WHERE dao.doctor_id = %(provider_id)s
                  AND dao.override_date = %(override_date)s
                  AND ( /* Time overlap logic */
                        (dao.start_time IS NULL OR dao.end_time IS NULL) OR /* Existing is full day */
                        (%(start_time)s < COALESCE(dao.end_time, TIME('23:59:59')) AND %(end_time)s > COALESCE(dao.start_time, TIME('00:00:00')))
                      )
                  AND ( /* Location scope logic */
                        dao.doctor_location_id IS NULL OR /* Existing is general override */
                        %(current_loc_id)s IS NULL OR /* New is general override */
                        dao.doctor_location_id = %(current_loc_id)s /* Both specific to same location */
                      )
            """
            if exclude_id:
                query += " AND dao.override_id != %(exclude_id)s"
                params['exclude_id'] = exclude_id
            query += " LIMIT 1"
            cursor_check.execute(query, params)
            overlap = cursor_check.fetchone() is not None
    except ValueError as ve:
        logger.warning(f"Validation error: override overlap P:{provider_id} L:{doctor_location_id} D:{override_date_str}: {ve}")
    except (mysql.connector.Error, ConnectionError) as db_err:
        logger.error(f"DB/Conn Error override overlap P:{provider_id} L:{doctor_location_id} D:{override_date_str}: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected Err override overlap P:{provider_id} L:{doctor_location_id} D:{override_date_str}: {e}", exc_info=True)
    finally:
        if conn and conn.is_connected(): conn.close()
    return overlap

def get_location_daily_caps(provider_id):
    conn = None; cursor = None; caps_data_for_template = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Conn failed for get_location_daily_caps.")
        
        with conn.cursor(dictionary=True) as loc_cursor:
            loc_cursor.execute("SELECT doctor_location_id, location_name FROM doctor_locations WHERE doctor_id = %s AND is_active = TRUE ORDER BY location_name ASC", (provider_id,))
            locations = loc_cursor.fetchall()

        if not locations: return []

        with conn.cursor(dictionary=True) as caps_cursor:
            query_caps = "SELECT cap.cap_id, cap.doctor_location_id, cap.day_of_week, cap.max_appointments FROM doctor_location_daily_caps cap WHERE cap.doctor_id = %s"
            caps_cursor.execute(query_caps, (provider_id,))
            fetched_caps = caps_cursor.fetchall()

        caps_map = {}
        for cap_entry in fetched_caps:
            key = (cap_entry['doctor_location_id'], cap_entry['day_of_week'])
            caps_map[key] = {'cap_id': cap_entry['cap_id'], 'max_appointments': cap_entry['max_appointments']}

        for loc in locations:
            loc_id = loc['doctor_location_id']
            location_caps_for_days = [None] * 7
            for day_idx in range(7):
                cap_info = caps_map.get((loc_id, day_idx))
                if cap_info:
                    location_caps_for_days[day_idx] = cap_info
            caps_data_for_template.append({
                'doctor_location_id': loc_id, 'location_name': loc['location_name'],
                'caps': location_caps_for_days
            })
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB Error getting daily caps P:{provider_id}: {err}", exc_info=True); raise
    except Exception as e:
        logger.error(f"Unexpected error in get_location_daily_caps P:{provider_id}: {e}", exc_info=True); raise
    finally:
        if conn and conn.is_connected(): conn.close()
    return caps_data_for_template

# --- Helper Functions with Own Transaction Management ---
def add_or_update_location_daily_cap(provider_id, doctor_location_id, day_of_week, max_appointments):
    conn = None; cursor = None; operation_successful = False
    message = ""; result_cap = None
    try:
        day_of_week_int = int(day_of_week)
        max_appts_int = int(max_appointments)
        doc_loc_id_int = int(doctor_location_id)

        if not (0 <= day_of_week_int <= 6): raise ValueError("Invalid day of the week (0-6).")
        if max_appts_int < 0: raise ValueError("Max appointments must be non-negative.")
        if not doc_loc_id_int > 0 : raise ValueError("Valid Location ID is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction: 
            logger.warning(f"add_or_update_cap: Conn already in transaction. P:{provider_id}, L:{doc_loc_id_int}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")
        
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT location_name FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s AND is_active = TRUE", (doc_loc_id_int, provider_id))
        loc_data = cursor.fetchone()
        if not loc_data:
            raise ValueError(f"Invalid, inactive, or unauthorized Location ID: {doc_loc_id_int}")

        query = """
            INSERT INTO doctor_location_daily_caps (doctor_id, doctor_location_id, day_of_week, max_appointments, created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE max_appointments = VALUES(max_appointments), updated_at = NOW()
        """
        cursor.execute(query, (provider_id, doc_loc_id_int, day_of_week_int, max_appts_int))

        cursor.execute("SELECT cap_id, max_appointments FROM doctor_location_daily_caps WHERE doctor_id = %s AND doctor_location_id = %s AND day_of_week = %s", (provider_id, doc_loc_id_int, day_of_week_int))
        result_cap_data = cursor.fetchone()
        conn.commit()
        operation_successful = True
        message = "Daily appointment cap saved successfully."
        if result_cap_data:
            result_cap = {"cap_id": result_cap_data['cap_id'], "doctor_location_id": doc_loc_id_int, "location_name": loc_data['location_name'], "day_of_week": day_of_week_int, "max_appointments": result_cap_data['max_appointments']}
    except ValueError as ve: message = str(ve)
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB Error saving daily cap P:{provider_id} L:{doctor_location_id} DOW:{day_of_week}: {err}", exc_info=True)
        message = f"Database error: {err.msg}" if hasattr(err, 'msg') and err.msg else "A database error occurred."
        if hasattr(err, 'errno') and err.errno == 1452: message = "Invalid Location ID provided or referenced data missing."
    except Exception as e:
        logger.error(f"Unexpected error saving daily cap P:{provider_id} L:{doctor_location_id}: {e}", exc_info=True)
        message = "An unexpected error occurred."
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction: # Should only be true if commit failed
                    logger.info(f"add_or_update_cap: Rolling back due to failure. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error add_or_update_cap: {rb_err}", exc_info=True)
            finally: conn.close()
    return operation_successful, message, result_cap

def delete_location_daily_cap_by_details(provider_id, doctor_location_id, day_of_week):
    conn = None; cursor = None; operation_successful = False; message = ""
    try:
        day_of_week_int = int(day_of_week)
        doc_loc_id_int = int(doctor_location_id)
        if not doc_loc_id_int > 0: raise ValueError("Valid Location ID is required.")
        if not (0 <= day_of_week_int <= 6): raise ValueError("Invalid day of the week (0-6).")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction: 
            logger.warning(f"delete_cap_by_details: Conn already in transaction. P:{provider_id}, L:{doc_loc_id_int}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")

        conn.start_transaction()
        cursor = conn.cursor()
        query = "DELETE FROM doctor_location_daily_caps WHERE doctor_id = %s AND doctor_location_id = %s AND day_of_week = %s"
        cursor.execute(query, (provider_id, doc_loc_id_int, day_of_week_int))
        rows_affected = cursor.rowcount
        conn.commit()
        operation_successful = True
        message = "Daily cap for this day and location cleared." if rows_affected > 0 else "No daily cap was set for this day and location to clear."
    except ValueError as ve: message = str(ve)
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB Error clearing daily cap P:{provider_id} L:{doctor_location_id} DOW:{day_of_week}: {err}", exc_info=True)
        message = f"Database error: {str(err)}"
    except Exception as e:
        logger.error(f"Error clearing daily cap P:{provider_id} L:{doctor_location_id} DOW:{day_of_week}: {e}", exc_info=True)
        message = "An unexpected error occurred."
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction: 
                    logger.info(f"delete_cap_by_details: Rolling back. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error delete_cap_by_details: {rb_err}", exc_info=True)
            finally: conn.close()
    return operation_successful, message

# --- Route to Display Availability Management Page ---
@availability_bp.route('/', methods=['GET'])
@login_required
def manage_availability_page():
    if not check_doctor_authorization(current_user):
        logger.warning(f"Unauthorized access to availability page by user {current_user.id}")
        abort(403)

    provider_id = get_provider_id(current_user)
    if provider_id is None:
        logger.error(f"Provider_id missing for user {current_user.id} on availability page.")
        flash("Your provider account is not properly configured. Please contact support.", "danger")
        return redirect(url_for('doctor_main.dashboard')) # Or appropriate error page/dashboard

    try:
        locations = get_all_provider_locations(provider_id)
        weekly_slots = get_all_provider_location_slots(provider_id)
        overrides = get_overrides(provider_id)
        daily_caps_data = get_location_daily_caps(provider_id)
    except (ConnectionError, mysql.connector.Error) as db_err:
        logger.critical(f"DB error loading availability page P:{provider_id}: {db_err}", exc_info=True)
        flash("A database error occurred while loading availability data. Please try again later.", "danger")
        return redirect(url_for('doctor_main.dashboard')) # Or render error template
    except Exception as e:
        logger.critical(f"Unexpected error loading availability page P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred. Please try again later.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    days_of_week_map = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    return render_template('Doctor_Portal/availability_management.html',
        locations=locations, weekly_slots=weekly_slots, overrides=overrides,
        daily_caps_data=daily_caps_data, days_of_week_map=days_of_week_map)

# --- AJAX Handlers (with refined transaction management) ---
# routes/Doctor_Portal/availability_management.py
# ... (other imports and existing code up to the route) ...

@availability_bp.route('/weekly', methods=['POST'])
@login_required
def add_weekly_slot_route():
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied."), 403
    provider_id = get_provider_id(current_user)
    if provider_id is None: return jsonify(success=False, message="Provider ID missing."), 400

    conn = None; cursor = None; operation_successful = False
    try:
        # ... (your form data retrieval and initial validation as before) ...
        doctor_location_id = request.form.get('doctor_location_id', type=int)
        day_of_week = request.form.get('day_of_week', type=int)
        start_time_str = request.form.get('start_time'); end_time_str = request.form.get('end_time')

        if not all([doctor_location_id, day_of_week is not None, start_time_str, end_time_str]):
            raise ValueError("Location, day, start/end times required.")
        if not (0 <= day_of_week <= 6): raise ValueError("Invalid day (0-6).")
        start_t = time.fromisoformat(start_time_str); end_t = time.fromisoformat(end_time_str)
        if start_t >= end_t: raise ValueError("Start time must be before end time.")

        conn = get_db_connection() # <--- The connection is obtained here
        if not conn: raise ConnectionError("DB connection failed.")

        # AGGRESSIVE ATTEMPT TO CLEAR ANY PRE-EXISTING TRANSACTION STATE
        if conn.in_transaction:
            logger.warning(f"add_weekly: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) received in transaction. Attempting to clear. P:{provider_id}")
            try:
                conn.rollback() # First, try to rollback
                logger.info(f"add_weekly: Pre-emptive rollback successful. P:{provider_id}")
            except mysql.connector.Error as rb_err:
                logger.error(f"add_weekly: Pre-emptive rollback failed: {rb_err}. Attempting commit to clear. P:{provider_id}", exc_info=True)
                try:
                    conn.commit() # If rollback fails, try to commit (might clear some states)
                    logger.info(f"add_weekly: Pre-emptive commit (after failed rollback) successful. P:{provider_id}")
                except mysql.connector.Error as c_err:
                    logger.error(f"add_weekly: Pre-emptive commit also failed: {c_err}. Connection state is likely bad. P:{provider_id}", exc_info=True)
                    # At this point, the connection is likely unusable for a new transaction.
                    # We could raise an error here, or proceed and let start_transaction fail.
                    # For this test, let's proceed to see if start_transaction still fails.
            
            # After attempting to clear, check again. This is for logging/understanding.
            if conn.in_transaction:
                logger.error(f"add_weekly: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) *still* in transaction after clear attempts. P:{provider_id}")
            else:
                logger.info(f"add_weekly: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) successfully cleared of prior transaction. P:{provider_id}")

        # Ensure autocommit is False before manual transaction start
        # This is crucial. If get_db_connection() sets it to True, start_transaction will fail or be meaningless.
        if conn.autocommit is True:
            logger.warning(f"add_weekly: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) had autocommit=True. Setting to False. P:{provider_id}")
            conn.autocommit = False


        # NOW, attempt to start the transaction for this route's operations
        conn.start_transaction() # <--- THIS IS WHERE THE ORIGINAL ERROR OCCURS
        
        # ... (rest of your logic: location check, overlap check, INSERT, commit) ...
        with conn.cursor() as cursor_check_loc:
            cursor_check_loc.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s AND is_active = TRUE", (doctor_location_id, provider_id))
            if not cursor_check_loc.fetchone():
                # No data modified yet in *this* transaction, so no need to rollback *this* transaction
                return jsonify(success=False, message="Invalid, inactive, or unauthorized location."), 403
        
        if check_location_weekly_slot_overlap(doctor_location_id, day_of_week, start_time_str, end_time_str):
            # No data modified yet in *this* transaction
            return jsonify(success=False, message="This slot overlaps with an existing one."), 400

        cursor = conn.cursor(dictionary=True)
        query = "INSERT INTO doctor_location_availability (doctor_location_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (doctor_location_id, day_of_week, start_time_str, end_time_str))
        new_slot_id = cursor.lastrowid
        
        cursor.execute("SELECT location_name FROM doctor_locations WHERE doctor_location_id = %s", (doctor_location_id,))
        loc_info = cursor.fetchone()
        location_name = loc_info['location_name'] if loc_info else 'Unknown'
        
        conn.commit() # Committing *this* transaction
        operation_successful = True
        
        return jsonify(success=True, message="Weekly slot added.", slot={"location_availability_id": new_slot_id, "doctor_location_id": doctor_location_id, "location_name": location_name, "day_of_week": day_of_week, "start_time": start_time_str, "end_time": end_time_str}), 201

    except ValueError as ve: 
        # If conn was obtained and a transaction *was* started for this route, finally block will handle rollback.
        return jsonify(success=False, message=str(ve)), 400
    except (mysql.connector.Error, ConnectionError) as err:
        # This will catch the "Transaction already in progress" if the aggressive clear fails
        # OR if other DB errors occur.
        logger.error(f"DB Err add weekly P:{provider_id} L:{request.form.get('doctor_location_id')}: {err}", exc_info=True)
        msg = f"DB Error: {err.msg}" if hasattr(err,'msg') else "Database Error"
        if hasattr(err, 'errno') and err.errno == 1452 : msg="Invalid Location ID"
        # Specific check for the error in question
        if "Transaction already in progress" in str(err):
            msg = "Database connection is in an inconsistent state. Please try again. If the problem persists, contact support."
        return jsonify(success=False, message=msg), 500
    except Exception as e:
        logger.error(f"Err add weekly P:{provider_id} L:{request.form.get('doctor_location_id')}: {e}", exc_info=True)
        return jsonify(success=False, message="An unexpected error occurred."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                # This rollback is for the transaction *started by this route*, if it wasn't committed.
                if conn.in_transaction: 
                    if not operation_successful: # Only rollback if this route's operation wasn't successful
                        logger.info(f"add_weekly: Rolling back this route's transaction. P:{provider_id}")
                        conn.rollback()
                    else:
                        # This state implies commit was called, but conn.in_transaction is still true.
                        # This is highly unusual for a successful commit.
                        logger.warning(f"add_weekly: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) still in transaction after successful commit. This is unexpected. P:{provider_id}")
            except Exception as rb_err: 
                logger.error(f"Rollback error in add_weekly finally: {rb_err}", exc_info=True)
            finally: 
                conn.close() # Always close the connection

@availability_bp.route('/weekly/<int:location_availability_id>', methods=['DELETE'])
@login_required
def delete_weekly_slot_route(location_availability_id):
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied."), 403
    provider_id = get_provider_id(current_user)
    if provider_id is None: return jsonify(success=False, message="Provider ID missing."), 400

    conn = None; cursor = None; operation_successful = False
    try:
        conn = get_db_connection(); 
        if not conn: raise ConnectionError("DB connection failed.")
        if conn.in_transaction:
            logger.warning(f"del_weekly: Conn already in transaction. P:{provider_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")

        conn.start_transaction()
        cursor = conn.cursor()
        query = """DELETE dla FROM doctor_location_availability dla
                   JOIN doctor_locations dl ON dla.doctor_location_id = dl.doctor_location_id
                   WHERE dla.location_availability_id = %s AND dl.doctor_id = %s"""
        cursor.execute(query, (location_availability_id, provider_id))
        
        if cursor.rowcount == 0:
            with conn.cursor() as check_cursor: # Check existence using a separate auto-closed cursor
                 check_cursor.execute("SELECT 1 FROM doctor_location_availability WHERE location_availability_id = %s", (location_availability_id,))
                 exists = check_cursor.fetchone()
            status_code = 403 if exists else 404
            # No data modified that needs rollback here beyond what finally handles
            return jsonify(success=False, message="Slot not found or unauthorized."), status_code
        
        conn.commit()
        operation_successful = True
        return jsonify(success=True, message="Weekly slot deleted."), 200
    except (mysql.connector.Error, ConnectionError) as err: 
        logger.error(f"DB Err del weekly ID {location_availability_id} P:{provider_id}: {err}", exc_info=True)
        return jsonify(success=False, message="DB error."), 500
    except Exception as e: 
        logger.error(f"Err del weekly ID {location_availability_id} P:{provider_id}: {e}", exc_info=True)
        return jsonify(success=False, message="Error."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction: 
                    logger.info(f"del_weekly: Rolling back. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error del_weekly: {rb_err}", exc_info=True)
            finally: conn.close()

@availability_bp.route('/override', methods=['POST'])
@login_required
def add_override_route():
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied."), 403
    provider_id = get_provider_id(current_user)
    if provider_id is None: return jsonify(success=False, message="Provider ID missing."), 400

    conn = None; cursor = None; operation_successful = False
    location_name_for_response = "All Locations (General)"
    try:
        override_date_str = request.form.get('override_date')
        doctor_location_id_str = request.form.get('doctor_location_id', '').strip()
        doctor_location_id = int(doctor_location_id_str) if doctor_location_id_str and doctor_location_id_str.isdigit() else None
        start_time_str = request.form.get('start_time', '').strip() or None
        end_time_str = request.form.get('end_time', '').strip() or None
        is_unavailable_str = request.form.get('is_unavailable', 'true')
        is_unavailable = is_unavailable_str.lower() == 'true'
        reason = request.form.get('reason', '').strip() or None

        if not override_date_str: raise ValueError("Override date is required.")
        date.fromisoformat(override_date_str)
        if start_time_str and end_time_str:
            start_t = time.fromisoformat(start_time_str); end_t = time.fromisoformat(end_time_str)
            if start_t >= end_t: raise ValueError("Start time must be before end time.")
        elif (start_time_str and not end_time_str) or (not start_time_str and end_time_str):
            raise ValueError("Both start and end times required for partial day, or neither for full day.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed.")
        if conn.in_transaction:
            logger.warning(f"add_override: Conn already in transaction. P:{provider_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")

        if doctor_location_id is not None:
            with conn.cursor(dictionary=True) as cursor_loc_check:
                cursor_loc_check.execute("SELECT location_name FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s AND is_active = TRUE", (doctor_location_id, provider_id))
                loc_info = cursor_loc_check.fetchone()
                if not loc_info: return jsonify(success=False, message="Invalid, inactive, or unauthorized location ID."), 403
                location_name_for_response = loc_info['location_name']
        
        if check_override_overlap(provider_id, override_date_str, doctor_location_id, start_time_str, end_time_str):
            return jsonify(success=False, message="This override conflicts with an existing one."), 400

        conn.start_transaction()
        cursor = conn.cursor()
        query = "INSERT INTO doctor_availability_overrides (doctor_id, doctor_location_id, override_date, start_time, end_time, is_unavailable, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        params = (provider_id, doctor_location_id, override_date_str, start_time_str, end_time_str, is_unavailable, reason)
        cursor.execute(query, params); new_id = cursor.lastrowid
        conn.commit()
        operation_successful = True

        override_data = {"override_id": new_id, "doctor_location_id": doctor_location_id, "location_name": location_name_for_response, "override_date": override_date_str, "start_time": start_time_str, "end_time": end_time_str, "is_unavailable": is_unavailable, "reason": reason}
        return jsonify(success=True, message="Override added.", override=override_data), 201
    except ValueError as ve: return jsonify(success=False, message=str(ve)), 400
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB Err add override P:{provider_id} L:{request.form.get('doctor_location_id')}: {err}", exc_info=True)
        msg = f"DB Error: {err.msg}" if hasattr(err,'msg') else "Database Error"
        if hasattr(err, 'errno') and err.errno == 1452 : msg="Invalid Location ID (if specified)"
        return jsonify(success=False, message=msg), 500
    except Exception as e:
        logger.error(f"Err add override P:{provider_id} L:{request.form.get('doctor_location_id')}: {e}", exc_info=True)
        return jsonify(success=False, message="An unexpected error occurred."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction: 
                    logger.info(f"add_override: Rolling back. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error add_override: {rb_err}", exc_info=True)
            finally: conn.close()

@availability_bp.route('/override/<int:override_id>', methods=['DELETE'])
@login_required
def delete_override_route(override_id):
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied."), 403
    provider_id = get_provider_id(current_user)
    if provider_id is None: return jsonify(success=False, message="Provider ID missing."), 400

    conn = None; cursor = None; operation_successful = False
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed.")
        if conn.in_transaction:
            logger.warning(f"del_override: Conn already in transaction. P:{provider_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}")
        
        conn.start_transaction()
        cursor = conn.cursor()
        query = "DELETE FROM doctor_availability_overrides WHERE override_id = %s AND doctor_id = %s"
        cursor.execute(query, (override_id, provider_id))
        
        if cursor.rowcount == 0:
            with conn.cursor() as check_cursor:
                check_cursor.execute("SELECT 1 FROM doctor_availability_overrides WHERE override_id = %s", (override_id,))
                exists = check_cursor.fetchone()
            status_code = 403 if exists else 404
            return jsonify(success=False, message="Override not found or unauthorized."), status_code
        
        conn.commit()
        operation_successful = True
        return jsonify(success=True, message="Override deleted."), 200
    except (mysql.connector.Error, ConnectionError) as err: 
        logger.error(f"DB Err del override ID {override_id} P:{provider_id}: {err}", exc_info=True)
        return jsonify(success=False, message="DB error."), 500
    except Exception as e: 
        logger.error(f"Err del override ID {override_id} P:{provider_id}: {e}", exc_info=True)
        return jsonify(success=False, message="Error."), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction: 
                    logger.info(f"del_override: Rolling back. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error del_override: {rb_err}", exc_info=True)
            finally: conn.close()

@availability_bp.route('/location-caps/save', methods=['POST'])
@login_required
def save_location_daily_cap_route():
    if not check_doctor_authorization(current_user): return jsonify(success=False, message="Access denied."), 403
    provider_id = get_provider_id(current_user)
    if provider_id is None: return jsonify(success=False, message="Provider ID missing."), 400

    data = request.json
    if not data: return jsonify(success=False, message="Invalid request data."), 400

    doctor_location_id_str = data.get('doctor_location_id')
    day_of_week_str = data.get('day_of_week') 
    max_appointments_str = data.get('max_appointments')

    if doctor_location_id_str is None or day_of_week_str is None or max_appointments_str is None:
        return jsonify(success=False, message="Location, day, and max appointments value required."), 400

    try:
        doctor_location_id_int = int(doctor_location_id_str)
        day_of_week_int = int(day_of_week_str)

        if max_appointments_str == '': # Clear cap
            op_success, message = delete_location_daily_cap_by_details(provider_id, doctor_location_id_int, day_of_week_int)
            status_code = 200 if op_success else (500 if "Database error" in message else 400)
            return jsonify(success=op_success, message=message, deleted=True, doctor_location_id=doctor_location_id_int, day_of_week=day_of_week_int), status_code
        else:
            max_appointments_int = int(max_appointments_str)
            # Validation for max_appointments_int (e.g. non-negative) is inside add_or_update helper
    except ValueError:
        return jsonify(success=False, message="Invalid input: Ensure numeric values for ID, day, and caps."), 400
    except Exception as e:
        logger.error(f"Error parsing daily cap save request: {e}", exc_info=True)
        return jsonify(success=False, message="Error processing request."), 500

    op_success, message, result_cap = add_or_update_location_daily_cap(provider_id, doctor_location_id_int, day_of_week_int, max_appointments_int)
    status_code = 200 if op_success else 400
    if not op_success:
        if "Database error" in message or "unexpected" in message.lower() or "DB Connection failed" in message: status_code = 500
        elif "Invalid or unauthorized Location" in message: status_code = 403
    return jsonify(success=op_success, message=message, cap=result_cap if op_success else None, deleted=False), status_code