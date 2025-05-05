# routes/Doctor_Portal/location_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, flash, redirect, url_for
)
from flask_login import login_required, current_user
from db import get_db_connection
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
# Use a distinct prefix for location-specific actions
locations_bp = Blueprint(
    'locations',
    __name__,
    url_prefix='/portal/locations', # Changed prefix
    template_folder='../../templates' # May not be needed
)

# --- Routes for Location Management (Moved from settings_management) ---

@locations_bp.route('', methods=['POST']) # Route changed to '/portal/locations'
@login_required
def add_doctor_location():
    """Adds a new location entry for the logged-in doctor."""
    if not check_doctor_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        return jsonify({"success": False, "message": "Invalid session."}), 401

    conn = None; cursor = None
    try:
        # Extract location details from form data
        location_name = request.form.get('location_name', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip() or None
        state = request.form.get('state', '').strip() or None
        zip_code = request.form.get('zip_code', '').strip() or None
        country = request.form.get('country', '').strip() or 'United States'
        phone_number = request.form.get('phone_number', '').strip() or None
        is_primary = request.form.get('is_primary') == 'on'
        notes = request.form.get('notes', '').strip() or None

        # Basic Validation
        if not location_name: raise ValueError("Location Name is required.")
        if not address: raise ValueError("Address is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True) # Use dictionary cursor to return data easily
        conn.start_transaction()

        # If setting this as primary, unset others for this doctor
        if is_primary:
            cursor.execute("UPDATE doctor_locations SET is_primary = FALSE WHERE doctor_id = %s", (doctor_id,))

        # Insert new location
        query = """
            INSERT INTO doctor_locations
            (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        """
        params = (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes)
        cursor.execute(query, params)
        new_location_id = cursor.lastrowid
        conn.commit()

        # Fetch the newly inserted row to return
        cursor.execute("SELECT * FROM doctor_locations WHERE doctor_location_id = %s", (new_location_id,))
        new_location_data = cursor.fetchone()
        # Format datetime if needed for JSON (created_at, updated_at are timestamps, usually fine)

        return jsonify({"success": True, "message": "Location added successfully.", "location": new_location_data}), 201

    except ValueError as ve:
         return jsonify({"success": False, "message": str(ve)}), 400
    except mysql.connector.Error as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"DB Error adding location for doctor {doctor_id}: {err}", exc_info=True)
        return jsonify({"success": False, "message": "Database error adding location."}), 500
    except ConnectionError as ce:
        logger.error(f"DB Connection Error adding location for doctor {doctor_id}: {ce}")
        return jsonify({"success": False, "message": "Database connection error."}), 500
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error adding location for doctor {doctor_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

@locations_bp.route('/<int:doctor_location_id>', methods=['DELETE']) # Route changed to '/portal/locations/<id>'
@login_required
def delete_doctor_location(doctor_location_id):
    """Deletes a location entry for the logged-in doctor."""
    if not check_doctor_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        return jsonify({"success": False, "message": "Invalid session."}), 401

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor()
        conn.start_transaction()

        # Delete the location entry, ensuring ownership
        # ON DELETE CASCADE handles related availability, limits, etc.
        query = "DELETE FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s"
        cursor.execute(query, (doctor_location_id, doctor_id))

        if cursor.rowcount == 0:
            conn.rollback()
            # Check if ID exists but isn't owned vs not existing
            cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s", (doctor_location_id,))
            status_code = 403 if cursor.fetchone() else 404
            return jsonify({"success": False, "message": "Location not found or not authorized."}), status_code

        conn.commit()
        return jsonify({"success": True, "message": "Location deleted successfully."}), 200

    except mysql.connector.Error as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        # Check for FK constraint issues (should not happen with CASCADE)
        if err.errno == 1451: # Cannot delete or update a parent row
             logger.error(f"FK Constraint error deleting location DL_ID:{doctor_location_id} for P:{doctor_id}: {err}", exc_info=True)
             return jsonify({"success": False, "message": "Cannot delete location due to existing references (e.g., appointments). Please resolve conflicts first."}), 409 # Conflict
        logger.error(f"DB Error deleting location DL_ID:{doctor_location_id} for P:{doctor_id}: {err}", exc_info=True)
        return jsonify({"success": False, "message": "Database error deleting location."}), 500
    except ConnectionError as ce:
        logger.error(f"DB Connection Error deleting location DL_ID:{doctor_location_id} for P:{doctor_id}: {ce}")
        return jsonify({"success": False, "message": "Database connection error."}), 500
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        logger.error(f"Unexpected error deleting location DL_ID:{doctor_location_id} for P:{doctor_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Add routes for updating a location if needed (e.g., PUT /portal/locations/<id>)
# @locations_bp.route('/<int:doctor_location_id>', methods=['PUT']) # Example
# @login_required
# def update_doctor_location(doctor_location_id):
#     # ... implementation ...