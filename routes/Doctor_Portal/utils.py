# routes/Doctor_Portal/utils.py

import mysql.connector
from flask import current_app
from flask_login import current_user # Needed if auth checks depend directly on it, otherwise pass user
from db import get_db_connection
from datetime import date, datetime
import math
import os
import uuid
import logging

# Configure logger
logger = logging.getLogger(__name__)

# --- Authorization Helpers ---

def check_doctor_authorization(user):
    """Checks if the user is an authenticated doctor."""
    if not user or not user.is_authenticated:
        return False
    return getattr(user, 'user_type', None) == 'doctor'


def can_modify_appointment(cursor, appointment_id, user_id_int):
    """Checks if the user is the provider for the appointment."""
    # Keep as is
    cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, user_id_int))
    return cursor.fetchone() is not None

def check_provider_authorization(user):
    """Checks if the user is an authenticated doctor (or nutritionist if needed)."""
    # Currently same as check_doctor_authorization based on updated files.
    # Keep separate if you anticipate needing different logic later (e.g., including 'nutritionist')
    if not user or not user.is_authenticated:
        return False
    user_type = getattr(user, 'user_type', None)
    return user_type == 'doctor' # Adjust required types here if needed

def check_doctor_or_dietitian_authorization(user, require_dietitian_for_edit=False):
    """
    Checks authorization, optionally requiring the 'Registered Dietitian' specialization.
    """
    if not user or not user.is_authenticated:
        return False

    # Basic check: Must be a 'doctor' user type
    if getattr(user, 'user_type', None) != 'doctor':
        return False

    # If edit/add/delete permission is required, check specialization
    if require_dietitian_for_edit:
        conn = None; cursor = None
        try:
            user_id = getattr(user, 'user_id', None) or getattr(user, 'id', None)
            if not user_id:
                logger.warning("Auth check (dietitian) failed: Could not determine user ID.")
                return False

            conn = get_db_connection()
            if not conn: raise ConnectionError("DB connection failed for auth check")
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT s.name as specialization_name FROM doctors doc
                JOIN specializations s ON doc.specialization_id = s.specialization_id
                WHERE doc.user_id = %s
            """, (user_id,))
            doctor_info = cursor.fetchone()
            if doctor_info and doctor_info.get('specialization_name') == 'Registered Dietitian':
                return True
            else:
                if doctor_info: logger.debug(f"Auth denied U:{user_id}: Spec='{doctor_info.get('specialization_name')}', Req='Registered Dietitian'.")
                else: logger.warning(f"Auth denied (dietitian) U:{user_id}: No doctor record found.")
                return False
        except (mysql.connector.Error, ConnectionError) as db_err:
            logger.error(f"DB Error check dietitian spec U:{user_id}: {db_err}")
            return False
        except Exception as e:
            logger.error(f"Error check dietitian spec U:{user_id}: {e}", exc_info=True)
            return False
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        # If only view access is needed, being a 'doctor' is enough
        return True

def is_doctor_authorized_for_patient(doctor_id, patient_id):
    """Checks if the doctor has had at least one appointment with the patient."""
    # Consolidates check_doctor_patient_relationship logic
    conn = None; cursor = None; authorized = False
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed for auth check")
        cursor = conn.cursor()
        query = "SELECT 1 FROM appointments WHERE doctor_id = %s AND patient_id = %s LIMIT 1"
        cursor.execute(query, (doctor_id, patient_id))
        authorized = cursor.fetchone() is not None
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"Error check doctor ({doctor_id}) auth for patient ({patient_id}): {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return authorized

# --- User/Provider ID Helper ---

def get_provider_id(user):
    """Safely gets the integer user ID from the current_user object."""
    try:
        # Prefer 'id' if using Flask-Login's default, fallback to 'user_id' if custom User class uses that
        user_id_str = getattr(user, 'id', None) or getattr(user, 'user_id', None)
        if user_id_str is None:
            raise ValueError("User ID attribute ('id' or 'user_id') is missing or None.")
        return int(user_id_str)
    except (AttributeError, ValueError, TypeError) as e:
        logger.error(f"Could not get valid provider user ID from current_user object. User: {user}, Error: {e}")
        return None

# --- Database Interaction Utilities ---

ENUM_CACHE = {} # Simple cache for ENUM values
def get_enum_values(table_name, column_name):
    """ Fetches and caches ENUM values from DB schema. """
    cache_key = f"{table_name}_{column_name}"
    if cache_key in ENUM_CACHE:
        return ENUM_CACHE[cache_key]
    conn = None; cursor = None; values = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor()
        db_name = conn.database
        query = "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s"
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0]
            if isinstance(enum_str, bytes): enum_str = enum_str.decode('utf-8')
            if enum_str.startswith('enum(') and enum_str.endswith(')'):
                 raw_values = enum_str[len('enum('):-1].split(',')
                 values = [val.strip().strip("'") for val in raw_values]
            else: logger.warning(f"Col {table_name}.{column_name} format unexpected: {enum_str}")
        else: logger.warning(f"Could not get ENUM def for {table_name}.{column_name}")
        ENUM_CACHE[cache_key] = values
        return values
    except (mysql.connector.Error, ConnectionError, IndexError, TypeError) as e:
        logger.error(f"Error get ENUM {table_name}.{column_name}: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_col, name_col, order_by=None, where_clause=None, params=None):
    """ Generic helper to fetch ID/Name pairs from simple tables, with optional WHERE """
    conn = None; cursor = None; items = []
    effective_order_by = order_by if order_by else name_col
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        # Use backticks for safety, though inputs are controlled internally
        query = f"SELECT `{id_col}`, {name_col} as name FROM `{table_name}` {where_sql} ORDER BY {effective_order_by}"
        cursor.execute(query, params or [])
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        logger.error(f"Error get simple list from {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items

# --- General Utilities ---

def calculate_age(born):
    """Calculate age from date of birth (date, datetime, or ISO string)."""
    if not born: return None
    today = date.today()
    try:
        if isinstance(born, str): born_date = date.fromisoformat(born)
        elif isinstance(born, datetime): born_date = born.date()
        elif isinstance(born, date): born_date = born
        else: return None # Invalid type
        return today.year - born_date.year - ((today.month, today.day) < (born_date.month, born_date.day))
    except (ValueError, TypeError): return None

def allowed_file(filename, allowed_extensions):
    """
    Checks if the filename has an allowed extension.
    :param filename: The name of the file.
    :param allowed_extensions: A set of allowed lowercase extensions (e.g., {'png', 'jpg'}).
    :return: True if allowed, False otherwise.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_secure_filename(filename):
    """ Generates a secure, unique filename using UUID. """
    ext = ''
    if '.' in filename:
        # Limit extension length for safety? Optional.
        ext = filename.rsplit('.', 1)[1].lower()[:10] # Limit ext length
    # Generate a UUID and convert it to a hex string
    secure_base = uuid.uuid4().hex
    # Combine the secure base name and the extension
    secure_name = f"{secure_base}.{ext}" if ext else secure_base
    return secure_name


def get_doctor_details(doctor_user_id):
    """Fetches comprehensive doctor details joining users, doctors, specializations, and departments."""
    conn = None
    cursor = None
    doctor_info = None
    try:
        conn = get_db_connection()
        if conn is None:
            current_app.logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id}): Could not establish connection.")
            return None
        if not conn.is_connected():
             current_app.logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id}): Connection is not active.")
             try: conn.close()
             except: pass
             return None

        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT
                u.user_id, u.username, u.email, u.first_name, u.last_name,
                u.phone, u.country, u.account_status,
                u.created_at as user_created_at,
                d.user_id as doctor_user_id, d.specialization_id, s.name AS specialization_name,
                d.license_number, d.license_state, d.license_expiration, d.npi_number, d.medical_school,
                d.graduation_year, d.certifications, d.accepting_new_patients, d.biography,
                d.profile_photo_url, d.clinic_address, d.verification_status, d.department_id,
                dep.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor';
        """
        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone()

    except mysql.connector.Error as err:
        current_app.logger.error(f"DB error in get_doctor_details for user_id {doctor_user_id}: {err}")
        return None
    except Exception as e:
        current_app.logger.error(f"Unexpected error in get_doctor_details for user_id {doctor_user_id}: {e}", exc_info=True)
        return None
    finally:
        if cursor:
            try: cursor.close()
            except Exception as cur_err: current_app.logger.error(f"Error closing cursor in get_doctor_details: {cur_err}", exc_info=False)
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as conn_err: current_app.logger.error(f"Error closing connection in get_doctor_details: {conn_err}", exc_info=False)
    return doctor_info
