# routes/Doctor_Portal/utils.py

import mysql.connector
from flask import current_app, has_app_context # For logging with app context
# from flask_login import current_user # Only import if directly used here, otherwise pass user object
from db import get_db_connection # Ensure this path is correct relative to your project structure
from datetime import date, datetime
import math # Not used in this snippet, but can keep if used elsewhere in full file
import os   # Not used in this snippet
import uuid
import logging

# Configure logger - Ensure this is configured at your app's entry point for consistency
logger = logging.getLogger(__name__)
# Example basic config if not done elsewhere:
# if not logger.hasHandlers():
#     logging.basicConfig(level=logging.INFO)
#     logger.setLevel(logging.INFO)

# --- Authorization Helpers ---

def check_doctor_authorization(user):
    logger.info("<<<<< THIS IS THE REAL check_doctor_authorization from Doctor_Portal/utils.py >>>>>") # Add this
    logger.debug(f"Checking doctor authorization for user: {user}")
    if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
        logger.debug("User is not authenticated.")
        return False
    logger.debug(f"User ID: {getattr(user, 'id', 'N/A')}")
    logger.debug(f"User type/role: {getattr(user, 'user_type', 'N/A')}") # Or whatever attribute stores the role

    # Example check:
    is_doctor = hasattr(user, 'user_type') and user.user_type == 'doctor'
    logger.debug(f"Is doctor based on check? {is_doctor}")
    return is_doctor

def can_modify_appointment(cursor, appointment_id, user_id_int):
    """Checks if the user is the provider for the appointment using an existing cursor."""
    # This function assumes the cursor is valid and managed externally.
    try:
        cursor.execute("SELECT 1 FROM appointments WHERE appointment_id = %s AND doctor_id = %s", (appointment_id, user_id_int))
        return cursor.fetchone() is not None
    except mysql.connector.Error as e:
        logger.error(f"DB Error in can_modify_appointment (Appt ID: {appointment_id}, User ID: {user_id_int}): {e}")
        return False # Fail safely

def check_provider_authorization(user):
    """Checks if the user is an authenticated doctor."""
    # Currently same as check_doctor_authorization.
    # Kept separate for potential future differentiation (e.g., 'nutritionist').
    if not user or not user.is_authenticated:
        return False
    user_type = getattr(user, 'user_type', None)
    return user_type == 'doctor'

def check_doctor_or_dietitian_authorization(user, require_dietitian_for_edit=False):
    """
    Checks authorization, optionally requiring the 'Registered Dietitian' specialization.
    """
    if not user or not user.is_authenticated:
        return False

    if getattr(user, 'user_type', None) != 'doctor':
        return False

    if require_dietitian_for_edit:
        conn = None; cursor = None
        try:
            user_id = get_provider_id(user) # Use helper to get ID consistently
            if not user_id:
                logger.warning("Auth check (dietitian) failed: Could not determine user ID.")
                return False

            conn = get_db_connection()
            if not conn:
                logger.error("DB connection failed for dietitian auth check.")
                return False
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
                if doctor_info:
                    logger.debug(f"Auth denied for dietitian U:{user_id}: Specialization='{doctor_info.get('specialization_name')}', Required='Registered Dietitian'.")
                else:
                    logger.warning(f"Auth denied for dietitian U:{user_id}: No doctor record found or specialization missing.")
                return False
        except (mysql.connector.Error, ConnectionError) as db_err:
            logger.error(f"DB Error during dietitian specialization check for U:{user_id}: {db_err}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during dietitian specialization check for U:{user_id}: {e}", exc_info=True)
            return False
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
    else:
        # If only view access is needed, being a 'doctor' type is sufficient
        return True

def is_doctor_authorized_for_patient(doctor_id, patient_id):
    """
    Checks if the doctor has had at least one non-canceled appointment with the patient.
    A more robust check might involve active care relationships.
    """
    conn = None; cursor = None; authorized = False
    if not doctor_id or not patient_id:
        return False
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("DB Connection failed for doctor-patient auth check.")
            return False
        cursor = conn.cursor()
        # Check for any non-canceled appointment as a proxy for a relationship
        query = """
            SELECT 1 FROM appointments
            WHERE doctor_id = %s AND patient_id = %s
            AND status != 'canceled'
            LIMIT 1
        """
        cursor.execute(query, (doctor_id, patient_id))
        authorized = cursor.fetchone() is not None
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB error checking doctor ({doctor_id}) auth for patient ({patient_id}): {err}")
    except Exception as e:
        logger.error(f"Unexpected error checking doctor-patient auth: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return authorized

# --- User/Provider ID Helper ---

def get_provider_id(user):
    """
    Safely gets the integer user ID from a user object.
    The user object might be current_user or another user instance.
    """
    if not user: return None
    try:
        # Prefer 'id' (Flask-Login default), then 'user_id' (common custom attribute)
        user_id_val = getattr(user, 'id', None)
        if user_id_val is None:
            user_id_val = getattr(user, 'user_id', None)

        if user_id_val is None:
            # logger.warning(f"User ID attribute ('id' or 'user_id') is missing from user object: {user}")
            return None
        return int(user_id_val)
    except (ValueError, TypeError) as e:
        logger.error(f"Could not convert user ID to int. User: {user}, Value: '{user_id_val}', Error: {e}")
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
        if not conn:
            logger.error(f"DB connection failed for ENUM fetch: {table_name}.{column_name}")
            return []
        cursor = conn.cursor()
        db_name = conn.database # Get the current database name
        query = """
            SELECT COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """
        cursor.execute(query, (db_name, table_name, column_name))
        result = cursor.fetchone()
        if result and result[0]:
            enum_str = result[0]
            if isinstance(enum_str, bytes): # Handle if connector returns bytes
                enum_str = enum_str.decode('utf-8')

            if enum_str.lower().startswith('enum(') and enum_str.endswith(')'):
                 # Extract content between parentheses: e.g., "'val1','val2','val3'"
                 enum_content = enum_str[enum_str.lower().find("(")+1:enum_str.rfind(")")]
                 # Split by comma, then strip whitespace and quotes from each value
                 values = [val.strip().strip("'\"") for val in enum_content.split(",")]
            else:
                logger.warning(f"Column {table_name}.{column_name} type format unexpected: {enum_str}")
        else:
            logger.warning(f"Could not retrieve ENUM definition for {table_name}.{column_name}")
        ENUM_CACHE[cache_key] = values
        return values
    except (mysql.connector.Error, ConnectionError, IndexError, TypeError) as e:
        logger.error(f"Error getting ENUM values for {table_name}.{column_name}: {e}", exc_info=True)
        return [] # Return empty list on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_all_simple(table_name, id_column_name, name_column_expression, where_clause=None, order_by=None, params=None):
    """
    Fetches ID and a name/display expression from a table, with optional WHERE and ORDER BY.
    Returns a list of dictionaries with 'id' and 'name' keys.

    Args:
        table_name (str): The name of the table.
        id_column_name (str): The name of the ID column.
        name_column_expression (str): The column name or SQL expression for the display name
                                      (e.g., 'column_name', "CONCAT(first, ' ', last)").
        where_clause (str, optional): SQL WHERE clause (without 'WHERE' keyword). E.g., "user_type='patient'".
        order_by (str, optional): SQL ORDER BY clause (without 'ORDER BY' keyword). E.g., "last_name, first_name".
        params (tuple, optional): Parameters for the WHERE clause if it uses placeholders.
    """
    conn = None
    cursor = None
    items = []

    # Basic sanitization for table and column names to prevent SQL injection
    # If these are always hardcoded strings from your code, this is less critical,
    # but good practice if there's any chance they could be influenced by external input.
    def sanitize_identifier(identifier):
        if identifier is None: return None
        # Allow simple column names, or expressions like CONCAT(...)
        # This is a very basic check; for complex dynamic queries, consider an ORM or more robust sanitization.
        if all(c.isalnum() or c in ['_', '.', ' ', '(', ')', "'", '"', ',', ':', '-'] for c in identifier): # Adjusted to allow more chars for expressions
            return identifier
        logger.error(f"Potentially unsafe identifier detected in get_all_simple: {identifier}")
        raise ValueError(f"Invalid identifier: {identifier}")

    try:
        safe_table = sanitize_identifier(table_name)
        safe_id_col = sanitize_identifier(id_column_name)
        # name_column_expression is an SQL expression, so it's harder to sanitize simply.
        # Trust it if it's hardcoded in your calling code.
        # For order_by, also be cautious if it's dynamic.
        safe_order_by = sanitize_identifier(order_by) if order_by else name_column_expression # Default order by name expression

        conn = get_db_connection()
        if not conn:
            logger.error(f"DB connection failed for get_all_simple(Table: {safe_table})")
            return items
        cursor = conn.cursor(dictionary=True) # Get results as dictionaries

        # Construct the query
        # Using f-strings for table/column names is generally safe if they are sanitized or hardcoded.
        # For `where_clause` and `params`, use parameterized queries.
        query = f"SELECT `{safe_id_col}` AS id, {name_column_expression} AS name FROM `{safe_table}`"

        if where_clause:
            query += f" WHERE {where_clause}" # where_clause should contain placeholders if needed

        if safe_order_by:
            query += f" ORDER BY {safe_order_by} ASC" # Default ASC, or let caller specify in order_by string

        current_logger = current_app.logger if has_app_context() else logger # Use app logger if available
        current_logger.debug(f"Executing get_all_simple query: {query} with params: {params}")

        cursor.execute(query, params or ()) # Pass params if provided
        items = cursor.fetchall()
        # `items` will be like: [{'id': 1, 'name': 'Display Name 1'}, {'id': 2, 'name': 'Display Name 2'}, ...]

    except mysql.connector.Error as err:
        (current_app.logger if has_app_context() else logger).error(f"DB error in get_all_simple (Table: {table_name}): {err}")
    except ValueError as ve: # From sanitize_identifier
        (current_app.logger if has_app_context() else logger).error(f"Value error in get_all_simple: {ve}")
    except Exception as e:
        (current_app.logger if has_app_context() else logger).error(f"Unexpected error in get_all_simple (Table: {table_name}): {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items


# --- General Utilities ---

def calculate_age(born_date_input):
    """
    Calculate age from date of birth.
    Input can be a date object, datetime object, or an ISO format string ('YYYY-MM-DD').
    """
    if not born_date_input:
        return None
    today = date.today()
    born_date = None
    try:
        if isinstance(born_date_input, str):
            born_date = date.fromisoformat(born_date_input)
        elif isinstance(born_date_input, datetime):
            born_date = born_date_input.date()
        elif isinstance(born_date_input, date):
            born_date = born_date_input
        else:
            logger.warning(f"Invalid type for age calculation: {type(born_date_input)}")
            return None

        # Calculate age
        age = today.year - born_date.year - ((today.month, today.day) < (born_date.month, born_date.day))
        return age
    except ValueError: # Handles invalid ISO date string format
        logger.warning(f"Invalid date format for age calculation: '{born_date_input}'")
        return None
    except TypeError: # Handles other type errors
        logger.warning(f"Type error during age calculation with input: {born_date_input}")
        return None

def allowed_file(filename, allowed_extensions):
    """
    Checks if the filename has an allowed extension.
    :param filename: The name of the file (str).
    :param allowed_extensions: A set of allowed lowercase extensions (e.g., {'png', 'jpg', 'jpeg'}).
    :return: True if allowed, False otherwise.
    """
    if not filename or not isinstance(filename, str):
        return False
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_secure_filename(original_filename):
    """
    Generates a more secure, unique filename using UUID, preserving the original extension.
    :param original_filename: The original name of the file.
    :return: A new, secure filename string.
    """
    if not original_filename or not isinstance(original_filename, str):
        # Fallback or raise error for invalid input
        logger.warning("generate_secure_filename received invalid input.")
        return f"{uuid.uuid4().hex}.unknown" # Default extension if original is bad

    parts = original_filename.rsplit('.', 1)
    extension = ""
    if len(parts) > 1:
        extension = parts[1].lower()
        # Optional: Validate extension against a list of generally safe extensions if desired
        # safe_extensions = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt', 'doc', 'docx', 'xls', 'xlsx'}
        # if extension not in safe_extensions:
        #     logger.warning(f"generate_secure_filename: Potentially unsafe extension '{extension}' from '{original_filename}'. Using default.")
        #     extension = "dat" # Or handle as an error

    # Generate a UUID and convert it to a hex string for the base name
    secure_base_name = uuid.uuid4().hex
    return f"{secure_base_name}.{extension}" if extension else secure_base_name

def get_doctor_details(doctor_user_id):
    """Fetches comprehensive doctor details joining users, doctors, specializations, and departments."""
    conn = None
    cursor = None
    doctor_info = None
    current_logger = current_app.logger if has_app_context() else logger

    if not doctor_user_id:
        current_logger.warning("get_doctor_details called with no doctor_user_id.")
        return None

    try:
        conn = get_db_connection()
        if conn is None:
            current_logger.error(f"DB connection failed for get_doctor_details (User ID: {doctor_user_id}).")
            return None
        # No need to check conn.is_connected() here, mysql.connector raises an error if operations are attempted on a closed conn.

        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT
                u.user_id, u.username, u.email, u.first_name, u.last_name,
                u.phone, u.country, u.account_status,
                u.created_at as user_created_at,
                d.user_id as doctor_user_id, d.specialization_id, s.name AS specialization_name,
                d.license_number, d.license_state, d.license_expiration, d.npi_number,
                d.medical_school, d.graduation_year, d.certifications, d.accepting_new_patients,
                d.biography, d.profile_photo_url, d.clinic_address, d.verification_status,
                d.department_id, dep.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dep ON d.department_id = dep.department_id
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """
        cursor.execute(query, (doctor_user_id,))
        doctor_info = cursor.fetchone()
        if not doctor_info:
            current_logger.info(f"No doctor details found for user_id {doctor_user_id}.")

    except mysql.connector.Error as err:
        current_logger.error(f"DB error in get_doctor_details for user_id {doctor_user_id}: {err}")
        return None # Return None on DB error
    except Exception as e:
        current_logger.error(f"Unexpected error in get_doctor_details for user_id {doctor_user_id}: {e}", exc_info=True)
        return None # Return None on other errors
    finally:
        if cursor:
            try: cursor.close()
            except Exception as cur_err: current_logger.error(f"Error closing cursor in get_doctor_details: {cur_err}", exc_info=False)
        if conn and conn.is_connected():
            try: conn.close()
            except Exception as conn_err: current_logger.error(f"Error closing connection in get_doctor_details: {conn_err}", exc_info=False)
    return doctor_info

def timedelta_to_time_filter(delta, format='%H:%M'):
    """Jinja filter to convert timedelta (from TIME column) or time object to HH:MM string."""
    if isinstance(delta, datetime.timedelta):
        # Convert timedelta to seconds, then to HH:MM
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        # Format ensuring leading zeros
        return f"{hours:02}:{minutes:02}"
    elif isinstance(delta, datetime.time):
        # If it's already a time object, just format it
        return delta.strftime(format)
    elif isinstance(delta, str):
        # If it's already a string in HH:MM or similar, return as is (basic check)
        if ':' in delta and len(delta) >= 4:
             return delta
        return '' # Or handle appropriately
    return '' # Return empty string for None or unexpected types