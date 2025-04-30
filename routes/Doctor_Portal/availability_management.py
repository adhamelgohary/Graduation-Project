# routes/Doctor_Portal/availability_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import time, date, datetime, timedelta

# --- Authorization Check ---
# UPDATED: Rename and modify to allow both doctors and nutritionists
def check_provider_authorization(user):
    """Checks if the user is an authenticated doctor or nutritionist."""
    if not user or not user.is_authenticated: return False
    user_type = getattr(user, 'user_type', None)
    # Allow users if their type is 'doctor' OR 'nutritionist'
    return user_type in ['doctor', 'nutritionist']

# --- Blueprint Definition ---
availability_bp = Blueprint(
    'availability',
    __name__,
    url_prefix='/portal/availability', # Match prefix style of appointments? '/portal/'
    template_folder='../../templates'
)

# --- Helper Functions for Database Interaction ---
# (get_weekly_slots, get_overrides, check_weekly_slot_overlap, check_override_overlap remain the same)
# ... (keep existing helper functions as they are compatible) ...

def get_weekly_slots(doctor_id):
    """Fetches all recurring weekly availability slots for a doctor."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("Failed to get DB connection")
        cursor = conn.cursor(dictionary=True)
        # Query remains the same - uses doctor_id which is the user_id for both
        query = """
            SELECT availability_id, day_of_week, start_time, end_time
            FROM doctor_availability
            WHERE doctor_id = %s AND is_available = TRUE
            ORDER BY day_of_week, start_time
        """
        cursor.execute(query, (doctor_id,))
        slots = cursor.fetchall()
        # Time conversion logic remains the same
        for slot in slots:
            if isinstance(slot.get('start_time'), timedelta):
                 slot['start_time'] = (datetime.min + slot['start_time']).strftime('%H:%M')
            if isinstance(slot.get('end_time'), timedelta):
                 slot['end_time'] = (datetime.min + slot['end_time']).strftime('%H:%M')
        return slots
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB Error getting weekly slots for doctor {doctor_id}: {err}")
        return []
    except ConnectionError as ce:
        current_app.logger.error(f"{ce} for doctor {doctor_id}")
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def get_overrides(doctor_id, start_date_str=None, end_date_str=None):
    """Fetches date-specific overrides for a doctor, optionally within a date range."""
    conn = None
    cursor = None
    filters = [doctor_id]
    sql_where_clause = ""

    try:
        # Date filtering logic remains the same
        if start_date_str:
            start_date = date.fromisoformat(start_date_str) # Validate format
            sql_where_clause += " AND override_date >= %s"
            filters.append(start_date)
        if end_date_str:
            end_date = date.fromisoformat(end_date_str) # Validate format
            sql_where_clause += " AND override_date <= %s"
            filters.append(end_date)
    except ValueError:
        current_app.logger.warning(f"Invalid date format for override filter: start={start_date_str}, end={end_date_str}")
        sql_where_clause = "" # Reset clause if dates are invalid
        filters = [doctor_id]

    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("Failed to get DB connection")
        cursor = conn.cursor(dictionary=True)
        # Query remains the same - uses doctor_id which is the user_id for both
        query = f"""
            SELECT override_id, override_date, start_time, end_time, is_unavailable, reason
            FROM doctor_availability_overrides
            WHERE doctor_id = %s {sql_where_clause}
            ORDER BY override_date, start_time
        """
        cursor.execute(query, tuple(filters))
        overrides = cursor.fetchall()
        # Date/time conversion logic remains the same
        for override in overrides:
            if isinstance(override.get('start_time'), timedelta):
                 override['start_time'] = (datetime.min + override['start_time']).strftime('%H:%M')
            if isinstance(override.get('end_time'), timedelta):
                 override['end_time'] = (datetime.min + override['end_time']).strftime('%H:%M')
            if isinstance(override.get('override_date'), date):
                 override['override_date'] = override['override_date'].isoformat()
        return overrides
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB Error getting overrides for doctor {doctor_id}: {err}")
        return []
    except ConnectionError as ce:
         current_app.logger.error(f"{ce} for doctor {doctor_id}")
         return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# --- Overlap check functions remain the same ---
def check_weekly_slot_overlap(doctor_id, day_of_week, new_start_time_str, new_end_time_str, exclude_id=None):
    # ... (no changes needed here) ...
    pass # Placeholder

def check_override_overlap(doctor_id, override_date, start_time_str=None, end_time_str=None, exclude_id=None):
    # ... (no changes needed here) ...
    pass # Placeholder

# --- Routes using availability_bp ---

@availability_bp.route('/', methods=['GET'])
@login_required
def manage_availability():
    """Displays the availability management page."""
    # UPDATED: Use the new authorization check
    if not check_provider_authorization(current_user):
        flash("Access denied. Provider role required.", "warning")
        # Redirect appropriately, maybe to a general portal dashboard if exists
        return redirect(url_for('auth.login')) # Or a portal home route

    # The rest of the function uses current_user.id, which is correct for both doctors and nutritionists
    doctor_id = current_user.id
    weekly_slots = get_weekly_slots(doctor_id)
    today = date.today()
    end_range = today + timedelta(days=60)
    overrides = get_overrides(doctor_id, today.isoformat(), end_range.isoformat())

    schedule = {i: [] for i in range(7)}
    for slot in weekly_slots:
        day_index = slot.get('day_of_week')
        if day_index is not None and 0 <= day_index <= 6:
             schedule[day_index].append(slot)
        else:
            current_app.logger.warning(f"Invalid day_of_week {day_index} found for doctor {doctor_id}, slot ID {slot.get('availability_id')}")

    days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    return render_template(
        'Doctor_Portal/availability.html', # Check template path
        schedule=schedule,
        overrides=overrides,
        days_of_week=days_of_week
    )


@availability_bp.route('/weekly', methods=['POST'])
@login_required
def add_weekly_slot_route():
    """Adds a new recurring weekly availability slot via AJAX."""
    # UPDATED: Use the new authorization check
    if not check_provider_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403

    # The rest of the function uses current_user.id (as doctor_id), which is correct
    doctor_id = current_user.id
    conn = None
    cursor = None
    try:
        # ... (validation and DB logic remains the same) ...
         day_of_week_str = request.form.get('day_of_week')
         start_time_str = request.form.get('start_time')
         end_time_str = request.form.get('end_time')

         # --- Validation ---
         if day_of_week_str is None or start_time_str is None or end_time_str is None:
              raise ValueError("Day, start time, and end time are required.")

         day_of_week = int(day_of_week_str)
         if not (0 <= day_of_week <= 6):
             raise ValueError("Invalid day of the week.")

         start_time = time.fromisoformat(start_time_str)
         end_time = time.fromisoformat(end_time_str)
         if start_time >= end_time:
             raise ValueError("Start time must be before end time.")

         if check_weekly_slot_overlap(doctor_id, day_of_week, start_time_str, end_time_str):
              return jsonify({"success": False, "message": "Time slot overlaps with an existing availability."}), 400
         # --- End Validation ---

         conn = get_db_connection()
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor()
         query = """
             INSERT INTO doctor_availability (doctor_id, day_of_week, start_time, end_time, is_available)
             VALUES (%s, %s, %s, %s, TRUE)
         """
         cursor.execute(query, (doctor_id, day_of_week, start_time_str, end_time_str))
         conn.commit()
         new_slot_id = cursor.lastrowid

         return jsonify({
             "success": True,
             "message": "Slot added.",
             "slot": {
                 "availability_id": new_slot_id,
                 "day_of_week": day_of_week,
                 "start_time": start_time_str,
                 "end_time": end_time_str
             }
         }), 201

    except ValueError as ve:
        # ... (error handling remains the same) ...
        current_app.logger.warning(f"Validation error adding weekly slot for doctor {doctor_id}: {ve}")
        return jsonify({"success": False, "message": str(ve)}), 400
    except mysql.connector.Error as err:
         # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"DB Error adding weekly slot for doctor {doctor_id}: {err}")
         if err.errno == 1062: # Duplicate entry
              return jsonify({"success": False, "message": "This exact time slot definition already exists."}), 409
         return jsonify({"success": False, "message": "Database error adding slot."}), 500
    except ConnectionError as ce:
          # ... (error handling remains the same) ...
          current_app.logger.error(f"{ce} adding weekly slot for doctor {doctor_id}")
          return jsonify({"success": False, "message": "Database connection error."}), 500
    except Exception as e:
        # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"Unexpected error adding weekly slot for doctor {doctor_id}: {e}", exc_info=True)
         return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        # ... (finally block remains the same) ...
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@availability_bp.route('/weekly/<int:availability_id>', methods=['DELETE'])
@login_required
def delete_weekly_slot_route(availability_id):
    """Deletes a recurring weekly availability slot via AJAX."""
    # UPDATED: Use the new authorization check
    if not check_provider_authorization(current_user):
         return jsonify({"success": False, "message": "Access Denied."}), 403

    # The rest of the function uses current_user.id (as doctor_id), which is correct
    doctor_id = current_user.id
    conn = None
    cursor = None
    try:
        # ... (DB logic remains the same) ...
         conn = get_db_connection()
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor()
         query = "DELETE FROM doctor_availability WHERE availability_id = %s AND doctor_id = %s"
         cursor.execute(query, (availability_id, doctor_id))

         if cursor.rowcount == 0:
             return jsonify({"success": False, "message": "Slot not found or not owned by user."}), 404

         conn.commit()
         return jsonify({"success": True, "message": "Slot deleted."}), 200

    except (mysql.connector.Error, ConnectionError) as err:
        # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"DB/Connection Error deleting weekly slot {availability_id} for doctor {doctor_id}: {err}")
         return jsonify({"success": False, "message": "Database error deleting slot."}), 500
    except Exception as e:
        # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"Unexpected error deleting weekly slot {availability_id} for doctor {doctor_id}: {e}", exc_info=True)
         return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        # ... (finally block remains the same) ...
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@availability_bp.route('/override', methods=['POST'])
@login_required
def add_override_route():
    """Adds a date-specific availability override via AJAX."""
    # UPDATED: Use the new authorization check
    if not check_provider_authorization(current_user):
         return jsonify({"success": False, "message": "Access Denied."}), 403

    # The rest of the function uses current_user.id (as doctor_id), which is correct
    doctor_id = current_user.id
    conn = None
    cursor = None
    try:
        # ... (validation and DB logic remains the same) ...
         override_date_str = request.form.get('override_date')
         start_time_str = request.form.get('start_time', '').strip()
         end_time_str = request.form.get('end_time', '').strip()
         is_unavailable_str = request.form.get('is_unavailable', 'true')
         reason = request.form.get('reason', '').strip()

         # --- Validation ---
         if not override_date_str: raise ValueError("Override date is required.")
         override_date_obj = date.fromisoformat(override_date_str)

         start_time_obj = time.fromisoformat(start_time_str) if start_time_str else None
         end_time_obj = time.fromisoformat(end_time_str) if end_time_str else None

         if (start_time_obj and not end_time_obj) or (not start_time_obj and end_time_obj):
             raise ValueError("Provide both start and end times, or leave both blank for full day.")
         if start_time_obj and end_time_obj and start_time_obj >= end_time_obj:
              raise ValueError("Start time must be before end time.")

         is_unavailable = is_unavailable_str.lower() == 'true'

         if check_override_overlap(doctor_id, override_date_obj, start_time_str or None, end_time_str or None):
              return jsonify({"success": False, "message": "This override overlaps with an existing one on the same date."}), 400
         # --- End Validation ---

         conn = get_db_connection()
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor()
         query = """
             INSERT INTO doctor_availability_overrides
             (doctor_id, override_date, start_time, end_time, is_unavailable, reason)
             VALUES (%s, %s, %s, %s, %s, %s)
         """
         params = (
             doctor_id, override_date_obj,
             start_time_obj, end_time_obj,
             is_unavailable, reason if reason else None
         )
         cursor.execute(query, params)
         conn.commit()
         new_override_id = cursor.lastrowid

         return jsonify({
             "success": True,
             "message": "Override added.",
             "override": {
                 "override_id": new_override_id,
                 "override_date": override_date_str,
                 "start_time": start_time_str if start_time_obj else None,
                 "end_time": end_time_str if end_time_obj else None,
                 "is_unavailable": is_unavailable,
                 "reason": reason
             }
         }), 201

    except ValueError as ve:
         # ... (error handling remains the same) ...
         current_app.logger.warning(f"Validation error adding override for doctor {doctor_id}: {ve}")
         return jsonify({"success": False, "message": str(ve)}), 400
    except mysql.connector.Error as err:
         # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"DB Error adding override for doctor {doctor_id}: {err}")
         if err.errno == 1062: # Unique constraint violation
              return jsonify({"success": False, "message": "This exact override definition already exists."}), 409
         return jsonify({"success": False, "message": "Database error adding override."}), 500
    except ConnectionError as ce:
          # ... (error handling remains the same) ...
          current_app.logger.error(f"{ce} adding override for doctor {doctor_id}")
          return jsonify({"success": False, "message": "Database connection error."}), 500
    except Exception as e:
         # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"Unexpected error adding override for doctor {doctor_id}: {e}", exc_info=True)
         return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
         # ... (finally block remains the same) ...
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()


@availability_bp.route('/override/<int:override_id>', methods=['DELETE'])
@login_required
def delete_override_route(override_id):
    """Deletes a date-specific availability override via AJAX."""
    # UPDATED: Use the new authorization check
    if not check_provider_authorization(current_user):
         return jsonify({"success": False, "message": "Access Denied."}), 403

    # The rest of the function uses current_user.id (as doctor_id), which is correct
    doctor_id = current_user.id
    conn = None
    cursor = None
    try:
        # ... (DB logic remains the same) ...
         conn = get_db_connection()
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor()

         query = "DELETE FROM doctor_availability_overrides WHERE override_id = %s AND doctor_id = %s"
         cursor.execute(query, (override_id, doctor_id))

         if cursor.rowcount == 0:
             return jsonify({"success": False, "message": "Override not found or not owned by user."}), 404

         conn.commit()
         return jsonify({"success": True, "message": "Override deleted."}), 200

    except (mysql.connector.Error, ConnectionError) as err:
        # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"DB/Connection Error deleting override {override_id} for doctor {doctor_id}: {err}")
         return jsonify({"success": False, "message": "Database error deleting override."}), 500
    except Exception as e:
         # ... (error handling remains the same) ...
         if conn: conn.rollback()
         current_app.logger.error(f"Unexpected error deleting override {override_id} for doctor {doctor_id}: {e}", exc_info=True)
         return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        # ... (finally block remains the same) ...
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()