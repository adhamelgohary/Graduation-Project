# routes/shared_utils.py

import mysql.connector
from flask import current_app, flash
from datetime import datetime, date, time, timedelta
import uuid
import os
from werkzeug.utils import secure_filename

# --- Authorization ---
def check_provider_authorization(user):
    """Checks if the user is an authenticated doctor or nutritionist."""
    if not user or not user.is_authenticated: return False
    user_type = getattr(user, 'user_type', None)
    return user_type in ['doctor', 'nutritionist']

def check_doctor_authorization(user):
    """Checks if the logged-in user is authenticated and is a doctor."""
    if not user or not user.is_authenticated: return False
    return getattr(user, 'user_type', None) == 'doctor'

# --- User ID Helper ---
def get_provider_id(user):
    """Safely gets the integer user ID from the current_user object."""
    try:
        user_id_str = getattr(user, 'id', None)
        if user_id_str is None:
            raise ValueError("User ID attribute ('id') is missing or None.")
        return int(user_id_str)
    except (AttributeError, ValueError, TypeError) as e:
        current_app.logger.error(f"Could not get valid provider user ID from current_user. User: {user}, Error: {e}")
        return None

# --- Generic DB Helpers ---
ENUM_CACHE = {}

def get_enum_values(table_name, column_name):
    """Fetches and caches ENUM values for a given table and column."""
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE: return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(); db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result:
            enum_str = result[0]
            enum_content = enum_str[enum_str.find("(")+1:enum_str.rfind(")")]
            values = [val.strip().strip("'\"") for val in enum_content.split(",")]
        ENUM_CACHE[cache_key] = values; return values
    except (mysql.connector.Error, ConnectionError, IndexError) as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_col, name_col, order_by=None, where_clause=None, params=None):
    """Fetches simple ID/Name pairs from a table."""
    conn = None; cursor = None; items = []
    order_clause = f"ORDER BY {order_by}" if order_by else f"ORDER BY {name_col}"
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        query = f"SELECT {id_col}, {name_col} FROM {table_name} {where_sql} {order_clause}"
        cursor.execute(query, params or [])
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching from {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

def get_specializations():
    """Fetches active specializations for dropdowns."""
    return get_all_simple('specializations', 'specialization_id', 'name', where_clause="is_active = TRUE", order_by="name")

# --- Location Helper ---
def get_all_provider_locations(provider_id):
     """
     Fetches locations relevant to the provider.
     Placeholder: Currently fetches ALL active locations.
     Adjust query if providers are linked to specific locations (e.g., via a provider_locations table).
     """
     conn = None; cursor = None; locations = []
     try:
         conn = get_db_connection();
         if not conn: raise ConnectionError("DB Connection failed")
         cursor = conn.cursor(dictionary=True)
         # Ideal: SELECT l.location_id, l.name FROM locations l JOIN provider_locations pl ON l.location_id = pl.location_id WHERE pl.provider_id = %s AND l.is_active = TRUE ORDER BY l.name
         # Current Fallback: Get all active locations
         query = "SELECT location_id, name FROM locations WHERE is_active = TRUE ORDER BY name"
         # cursor.execute(query, (provider_id,)) # Use this if using the 'Ideal' query
         cursor.execute(query) # Use this for the fallback query
         locations = cursor.fetchall()
     except mysql.connector.Error as err:
         if err.errno == 1146: # Table 'locations' or 'provider_locations' doesn't exist
             current_app.logger.error(f"Error fetching locations P:{provider_id}: Required table missing.")
             # Optionally flash a message if appropriate context exists, otherwise just log
             # flash("Location data is currently unavailable.", "warning")
         else:
             current_app.logger.error(f"DB Error fetching locations P:{provider_id}: {err}")
     except ConnectionError as ce:
          current_app.logger.error(f"DB Connection Error fetching locations P:{provider_id}: {ce}")
     except Exception as e:
         current_app.logger.error(f"Unexpected Error fetching locations P:{provider_id}: {e}", exc_info=True)
     finally:
         if cursor: cursor.close()
         if conn and conn.is_connected(): conn.close()
     return locations


# --- Appointment Related Helpers (Potentially Shared) ---
DEFAULT_APPOINTMENT_DURATIONS = {
    'initial': 60, 'follow-up': 30, 'consultation': 45,
    'urgent': 30, 'routine': 20, 'telehealth': 30,
}

def get_appointment_duration(appointment_type):
    """Gets the default duration for an appointment type."""
    # Ensure lowercase comparison for robustness
    return DEFAULT_APPOINTMENT_DURATIONS.get(str(appointment_type).lower(), 30)


# --- File Upload Helpers ---
def allowed_file(filename, allowed_extensions):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_secure_filename(filename):
    """Generates a secure, unique filename using UUID."""
    ext = ''
    if '.' in filename:
        ext = filename.rsplit('.', 1)[1].lower()
    secure_base = uuid.uuid4().hex
    secure_name = f"{secure_base}.{ext}" if ext else secure_base
    # Use werkzeug's secure_filename on the original name part *before* adding UUID if needed for sanitization
    # For UUID-based names, direct construction is usually fine.
    return secure_name