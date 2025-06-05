# routes/Doctor_Portal/availability_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, abort, render_template, flash, url_for, redirect
)
from flask_login import login_required, current_user
from db import get_db_connection 
from datetime import time, date, datetime, timedelta
import logging

try:
    from routes.Doctor_Portal.utils import check_doctor_authorization, get_provider_id 
except (ImportError, ValueError) as e:
    logging.getLogger(__name__).critical(f"CRITICAL: Failed to import utils for availability. Details: {e}", exc_info=True)
    def check_doctor_authorization(user): return False 
    def get_provider_id(user): return None 

logger = logging.getLogger(__name__)

availability_bp = Blueprint(
    'availability',
    __name__,
    url_prefix='/portal/availability',
    template_folder='../../templates/Doctor_Portal/Availability' 
)

# --- Database Helper Functions (Remain Unchanged, ensure they are correct) ---
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
        raise 
    except Exception as e:
        logger.error(f"Unexpected error in get_all_provider_locations P:{provider_id}: {e}", exc_info=True)
        raise 
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
            start_date_obj = date.fromisoformat(start_date_str) # Renamed to avoid conflict
            sql_where_clause += " AND dao.override_date >= %s"; filters.append(start_date_obj)
        if end_date_str:
            end_date_obj = date.fromisoformat(end_date_str) # Renamed to avoid conflict
            sql_where_clause += " AND dao.override_date <= %s"; filters.append(end_date_obj)
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
    # Unchanged
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
        with conn.cursor() as cursor_check: 
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
    except (mysql.connector.Error, ConnectionError) as db_err:
        logger.error(f"DB/Connection Error weekly overlap DL_ID:{doctor_location_id}: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error check weekly overlap DL_ID:{doctor_location_id}: {e}", exc_info=True)
    finally:
        if conn and conn.is_connected(): conn.close()
    return overlap

def check_override_overlap(provider_id, override_date_str, doctor_location_id=None, start_time_str=None, end_time_str=None, exclude_id=None):
    # Unchanged
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
                  AND ( (dao.start_time IS NULL OR dao.end_time IS NULL) OR (%(start_time)s < COALESCE(dao.end_time, TIME('23:59:59')) AND %(end_time)s > COALESCE(dao.start_time, TIME('00:00:00'))) )
                  AND ( dao.doctor_location_id IS NULL OR %(current_loc_id)s IS NULL OR dao.doctor_location_id = %(current_loc_id)s )
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
    # Unchanged
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

def add_or_update_location_daily_cap(provider_id, doctor_location_id, day_of_week, max_appointments):
    # Unchanged
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
                if conn.in_transaction: 
                    logger.info(f"add_or_update_cap: Rolling back due to failure. P:{provider_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error add_or_update_cap: {rb_err}", exc_info=True)
            finally: conn.close()
    return operation_successful, message, result_cap

def delete_location_daily_cap_by_details(provider_id, doctor_location_id, day_of_week):
    # Unchanged
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

# --- Main Page Routes ---
@availability_bp.route('/')
@login_required
def manage_availability_redirect():
    # Redirect to the default tab, e.g., weekly schedule
    return redirect(url_for('.manage_weekly_schedule'))

@availability_bp.route('/weekly-schedule', methods=['GET'])
@login_required
def manage_weekly_schedule():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    try:
        locations = get_all_provider_locations(provider_id)
        weekly_slots = get_all_provider_location_slots(provider_id)
    except Exception as e:
        flash("Error loading weekly schedule data. Please try again later.", "danger")
        logger.error(f"Error loading weekly schedule page for P:{provider_id}: {e}", exc_info=True)
        # Render the page with empty data or redirect
        locations = []
        weekly_slots = []
        # return redirect(url_for('doctor_main.dashboard')) # Alternative

    days_of_week_map = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    
    csrf_token_form_field = ""
    if hasattr(current_app, 'extensions') and 'csrf' in current_app.extensions:
        from flask_wtf.csrf import generate_csrf
        csrf_token_form_field = f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'

    return render_template('weekly_schedule.html',
                           locations=locations,
                           weekly_slots=weekly_slots,
                           days_of_week_map=days_of_week_map,
                           csrf_token_form_field=csrf_token_form_field)

@availability_bp.route('/daily-caps', methods=['GET'])
@login_required
def manage_daily_caps():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('doctor_main.dashboard'))
    
    try:
        locations = get_all_provider_locations(provider_id) 
        daily_caps_data = get_location_daily_caps(provider_id)
    except Exception as e:
        flash("Error loading daily caps data. Please try again later.", "danger")
        logger.error(f"Error loading daily caps page for P:{provider_id}: {e}", exc_info=True)
        locations = []
        daily_caps_data = []

    days_of_week_map = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
    csrf_token_form_field = "" 
    if hasattr(current_app, 'extensions') and 'csrf' in current_app.extensions:
        from flask_wtf.csrf import generate_csrf
        csrf_token_form_field = f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'

    return render_template('daily_caps.html', 
                           locations=locations, 
                           daily_caps_data=daily_caps_data,
                           days_of_week_map=days_of_week_map,
                           csrf_token_form_field=csrf_token_form_field)

@availability_bp.route('/date-overrides', methods=['GET'])
@login_required
def manage_date_overrides():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    try:
        locations = get_all_provider_locations(provider_id)
        overrides = get_overrides(provider_id) 
    except Exception as e:
        flash("Error loading date override data. Please try again later.", "danger")
        logger.error(f"Error loading date overrides page for P:{provider_id}: {e}", exc_info=True)
        locations = []
        overrides = []
    
    csrf_token_form_field = ""
    if hasattr(current_app, 'extensions') and 'csrf' in current_app.extensions:
        from flask_wtf.csrf import generate_csrf
        csrf_token_form_field = f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'

    return render_template('date_overrides.html', 
                           locations=locations, 
                           overrides=overrides,
                           csrf_token_form_field=csrf_token_form_field)


# --- Form Handling Routes (Full Page POST and Redirect) ---

@availability_bp.route('/weekly-schedule/add', methods=['POST'])
@login_required
def add_weekly_slot_page_route():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('.manage_weekly_schedule'))

    conn = None; cursor = None # Initialize here
    operation_successful = False # To track if commit should happen or rollback
    
    try:
        doctor_location_id = request.form.get('doctor_location_id', type=int)
        day_of_week = request.form.get('day_of_week', type=int)
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')

        if not all([doctor_location_id, day_of_week is not None, start_time_str, end_time_str]):
            flash("Location, day, start and end times are required.", "danger")
            raise ValueError("Missing required fields")
        if not (0 <= day_of_week <= 6): 
            flash("Invalid day of the week selected.", "danger")
            raise ValueError("Invalid day of week")
        
        start_t = time.fromisoformat(start_time_str)
        end_t = time.fromisoformat(end_time_str)
        if start_t >= end_t:
            flash("Start time must be before end time.", "danger")
            raise ValueError("Start time not before end time")

        conn = get_db_connection()
        if not conn: 
            logger.error(f"add_weekly_slot_page_route: Failed to get DB connection for P:{provider_id}")
            raise ConnectionError("DB connection failed.")

        # --- Ensure clean state before starting a new transaction ---
        if conn.in_transaction:
            logger.warning(f"add_weekly_slot_page_route: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) was unexpectedly in a transaction. Attempting rollback. P:{provider_id}")
            try:
                conn.rollback() # Attempt to clear any lingering transaction
                logger.info(f"add_weekly_slot_page_route: Pre-emptive rollback succeeded. P:{provider_id}")
            except mysql.connector.Error as rb_err:
                logger.error(f"add_weekly_slot_page_route: Pre-emptive rollback failed: {rb_err}. Connection state might be problematic. P:{provider_id}", exc_info=True)
                # Depending on the error, you might re-raise or try to proceed cautiously.
                # For now, let's log and proceed to see if start_transaction still fails.

        # Ensure autocommit is False for manual transaction control
        if conn.autocommit is True:
            logger.info(f"add_weekly_slot_page_route: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) had autocommit=True. Setting to False. P:{provider_id}")
            conn.autocommit = False
        # --- End of clean state assurance ---
        
        conn.start_transaction() # Start the transaction for this specific operation
        
        # Check location ownership within the current transaction
        with conn.cursor() as cursor_check_loc: # Using 'with' ensures cursor is closed
            cursor_check_loc.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s AND is_active = TRUE", (doctor_location_id, provider_id))
            if not cursor_check_loc.fetchone():
                flash("Invalid or unauthorized location selected.", "danger")
                raise ValueError("Invalid location") # This will trigger rollback in finally

        # Check for overlap (this function gets its own connection, so it's isolated)
        if check_location_weekly_slot_overlap(doctor_location_id, day_of_week, start_time_str, end_time_str):
            flash("This slot overlaps with an existing one for the selected location and day.", "warning")
            raise ValueError("Slot overlap") # This will trigger rollback in finally

        cursor = conn.cursor(dictionary=True) # Create cursor for insert after checks
        query = "INSERT INTO doctor_location_availability (doctor_location_id, day_of_week, start_time, end_time) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (doctor_location_id, day_of_week, start_time_str, end_time_str))
        # new_slot_id = cursor.lastrowid # Not used in redirect flow currently, but good to have if needed
        
        conn.commit() # Commit the transaction for this operation
        operation_successful = True # Mark as successful for the finally block
        flash("Weekly slot added successfully.", "success")

    except ValueError as ve:
        logger.warning(f"Validation error adding weekly slot for P:{provider_id}: {ve}")
        # Flash message should have been set by the validation checks
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB Error adding weekly slot P:{provider_id}: {err}", exc_info=True)
        flash(f"Database error: {getattr(err, 'msg', 'Could not add slot.')}", "danger")
    except Exception as e:
        logger.error(f"Unexpected error adding weekly slot P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while adding the slot.", "danger")
    finally:
        if cursor: 
            cursor.close()
        if conn and conn.is_connected():
            try:
                # Only rollback if an operation was started for this route AND it wasn't successful
                if conn.in_transaction and not operation_successful: 
                    logger.info(f"add_weekly_slot_page_route: Rolling back this route's transaction due to failure. P:{provider_id}")
                    conn.rollback()
                elif conn.in_transaction and operation_successful:
                     logger.warning(f"add_weekly_slot_page_route: Connection (ID: {conn.connection_id if hasattr(conn, 'connection_id') else 'N/A'}) still in transaction after explicit commit. This is unexpected. P:{provider_id}")
                     # You might attempt another rollback here if this state is problematic
                     # conn.rollback() 
            except Exception as rb_err: 
                logger.error(f"Rollback/Cleanup error in add_weekly_slot_page_route finally: {rb_err}", exc_info=True)
            finally: 
                conn.close() 
        
    return redirect(url_for('.manage_weekly_schedule'))

@availability_bp.route('/weekly-schedule/delete/<int:location_availability_id>', methods=['POST'])
@login_required
def delete_weekly_slot_page_route(location_availability_id):
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('.manage_weekly_schedule'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed.")
        conn.start_transaction()
        cursor = conn.cursor()
        query = """DELETE dla FROM doctor_location_availability dla
                   JOIN doctor_locations dl ON dla.doctor_location_id = dl.doctor_location_id
                   WHERE dla.location_availability_id = %s AND dl.doctor_id = %s"""
        cursor.execute(query, (location_availability_id, provider_id))
        
        if cursor.rowcount == 0:
            flash("Slot not found or you are not authorized to delete it.", "warning")
        else:
            flash("Weekly slot deleted successfully.", "success")
        conn.commit()
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"DB Error deleting weekly slot ID {location_availability_id} P:{provider_id}: {err}", exc_info=True)
        flash("Database error while deleting slot.", "danger")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error deleting weekly slot ID {location_availability_id} P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.manage_weekly_schedule'))


@availability_bp.route('/daily-caps/save', methods=['POST'])
@login_required
def save_daily_caps_page_route():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('.manage_daily_caps'))

    all_ops_successful = True
    error_messages = []
    try:
        locations = get_all_provider_locations(provider_id) # Get locations to iterate through
        for loc in locations:
            for day_idx in range(7):
                cap_value_str = request.form.get(f"cap_{loc['doctor_location_id']}_{day_idx}")
                if cap_value_str is not None: 
                    if cap_value_str.strip() == '' or cap_value_str.strip() == '0':
                        success, msg = delete_location_daily_cap_by_details(provider_id, loc['doctor_location_id'], day_idx)
                        if not success: 
                            all_ops_successful = False
                            error_messages.append(f"Location '{loc['location_name']}', Day {day_idx}: {msg}")
                    else:
                        try:
                            max_appts = int(cap_value_str)
                            if max_appts < 0:
                                all_ops_successful = False
                                error_messages.append(f"Location '{loc['location_name']}', Day {day_idx}: Cap must be non-negative.")
                                continue
                            success, msg, _ = add_or_update_location_daily_cap(provider_id, loc['doctor_location_id'], day_idx, max_appts)
                            if not success:
                                all_ops_successful = False
                                error_messages.append(f"Location '{loc['location_name']}', Day {day_idx}: {msg}")
                        except ValueError:
                            all_ops_successful = False
                            error_messages.append(f"Location '{loc['location_name']}', Day {day_idx}: Invalid cap value '{cap_value_str}'.")
    except Exception as e:
        logger.error(f"Error processing batch daily caps save for P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while saving caps.", "danger")
        return redirect(url_for('.manage_daily_caps'))

    if all_ops_successful:
        flash("Daily caps updated successfully.", "success")
    else:
        flash("Some errors occurred while updating daily caps: " + "; ".join(error_messages), "danger")
        
    return redirect(url_for('.manage_daily_caps'))


@availability_bp.route('/date-overrides/add', methods=['POST'])
@login_required
def add_override_page_route():
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('.manage_date_overrides'))

    conn = None; cursor = None
    try:
        override_date_str = request.form.get('override_date')
        doctor_location_id_str = request.form.get('doctor_location_id', '').strip()
        doctor_location_id = int(doctor_location_id_str) if doctor_location_id_str and doctor_location_id_str.isdigit() else None
        start_time_str = request.form.get('start_time', '').strip() or None
        end_time_str = request.form.get('end_time', '').strip() or None
        is_unavailable_str = request.form.get('is_unavailable', 'false') # If checkbox not checked, it won't be in form
        is_unavailable = is_unavailable_str.lower() == 'true' or request.form.get('is_unavailable') == 'on' # Handle 'on' from checkbox
        reason = request.form.get('reason', '').strip() or None

        if not override_date_str:
            flash("Override date is required.", "danger"); raise ValueError("Missing override date")
        date.fromisoformat(override_date_str) 

        if start_time_str and end_time_str:
            start_t = time.fromisoformat(start_time_str); end_t = time.fromisoformat(end_time_str)
            if start_t >= end_t:
                flash("Start time must be before end time.", "danger"); raise ValueError("Start time not before end time")
        elif (start_time_str and not end_time_str) or (not start_time_str and end_time_str):
            flash("Both start and end times are required for a partial day override, or leave both blank for a full day override.", "warning"); raise ValueError("Partial time missing")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed.")

        if doctor_location_id is not None: # Check location ownership if a specific location is chosen
            with conn.cursor() as cursor_loc_check: 
                cursor_loc_check.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s AND is_active = TRUE", (doctor_location_id, provider_id))
                if not cursor_loc_check.fetchone():
                    flash("Invalid or unauthorized location selected.", "danger"); raise ValueError("Invalid location")
        
        if check_override_overlap(provider_id, override_date_str, doctor_location_id, start_time_str, end_time_str):
            flash("This override overlaps with an existing one for the selected date and location scope.", "warning"); raise ValueError("Override overlap")

        conn.start_transaction()
        cursor = conn.cursor()
        query = "INSERT INTO doctor_availability_overrides (doctor_id, doctor_location_id, override_date, start_time, end_time, is_unavailable, reason) VALUES (%s, %s, %s, %s, %s, %s, %s)"
        params = (provider_id, doctor_location_id, override_date_str, start_time_str, end_time_str, is_unavailable, reason)
        cursor.execute(query, params)
        conn.commit()
        flash("Date override added successfully.", "success")

    except ValueError as ve:
        logger.warning(f"Validation error adding override for P:{provider_id}: {ve}")
        # Flash message should have been set by the validation checks or explicitly above
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"DB Error adding override P:{provider_id}: {err}", exc_info=True)
        flash(f"Database error: {getattr(err, 'msg', 'Could not add override.')}", "danger")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error adding override P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred while adding the override.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.manage_date_overrides'))


@availability_bp.route('/date-overrides/delete/<int:override_id>', methods=['POST'])
@login_required
def delete_override_page_route(override_id): 
    if not check_doctor_authorization(current_user): abort(403)
    provider_id = get_provider_id(current_user)
    if provider_id is None:
        flash("Provider account not configured.", "danger")
        return redirect(url_for('.manage_date_overrides'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed.")
        conn.start_transaction()
        cursor = conn.cursor()
        query = "DELETE FROM doctor_availability_overrides WHERE override_id = %s AND doctor_id = %s"
        cursor.execute(query, (override_id, provider_id))
        
        if cursor.rowcount == 0:
            flash("Override not found or you are not authorized to delete it.", "warning")
        else:
            flash("Date override deleted successfully.", "success")
        conn.commit()
    except (mysql.connector.Error, ConnectionError) as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"DB Error deleting override ID {override_id} P:{provider_id}: {err}", exc_info=True)
        flash("Database error while deleting override.", "danger")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error deleting override ID {override_id} P:{provider_id}: {e}", exc_info=True)
        flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return redirect(url_for('.manage_date_overrides'))