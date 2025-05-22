# routes/Doctor_Portal/location_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, flash, redirect, url_for, render_template
)
from flask_login import login_required, current_user
from db import get_db_connection
import logging
from datetime import datetime # <--- IMPORT DATETIME HERE

# Assuming utils.py is in the same directory or correctly referenced in your project
try:
    from .utils import check_doctor_authorization, get_provider_id
except (ImportError, ValueError) as e:
    logging.getLogger(__name__).error(f"CRITICAL: Failed to import utils for location_management. Details: {e}", exc_info=True)
    def check_doctor_authorization(user): return False # Fallback
    def get_provider_id(user): return None # Fallback


logger = logging.getLogger(__name__)

locations_bp = Blueprint(
    'locations',
    __name__,
    url_prefix='/portal/locations',
    template_folder='../../templates' # Assumes templates are two levels up
)

# --- Helper to get locations for the page ---
def get_doctor_locations_list(doctor_id):
    conn = None; cursor = None; locations = []
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM doctor_locations WHERE doctor_id = %s AND is_active = TRUE ORDER BY is_primary DESC, location_name ASC"
        cursor.execute(query, (doctor_id,))
        locations = cursor.fetchall()
        
        for loc in locations:
            # Check if the key exists and is a datetime object before formatting
            created_at_val = loc.get('created_at')
            if created_at_val and isinstance(created_at_val, datetime):
                loc['created_at'] = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
            
            updated_at_val = loc.get('updated_at')
            if updated_at_val and isinstance(updated_at_val, datetime):
                loc['updated_at'] = updated_at_val.strftime('%Y-%m-%d %H:%M:%S')

    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error fetching locations for P:{doctor_id}: {err}", exc_info=True)
        raise # Re-raise to be handled by the calling route
    except Exception as e:
        logger.error(f"Unexpected error fetching locations for P:{doctor_id}: {e}", exc_info=True)
        raise # Re-raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return locations

# --- Route to display the locations management page ---
@locations_bp.route('', methods=['GET'])
@login_required
def manage_locations_page():
    if not check_doctor_authorization(current_user):
        abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        flash("Invalid user session or provider ID not found.", "danger")
        return redirect(url_for('doctor_main.dashboard')) 

    try:
        current_locations = get_doctor_locations_list(doctor_id)
    except Exception as e: 
        logger.error(f"Error loading locations page for P:{doctor_id}: {e}", exc_info=True)
        flash("Could not load location data. Please try again.", "danger")
        current_locations = [] 

    return render_template('Doctor_Portal/location_management.html', locations=current_locations)


# --- Routes for Location Management (CRUD operations) ---

@locations_bp.route('/add', methods=['POST']) 
@login_required
def add_doctor_location():
    if not check_doctor_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        return jsonify({"success": False, "message": "Invalid session or provider ID missing."}), 401

    conn = None; cursor = None; operation_successful = False
    try:
        location_name = request.form.get('location_name', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip() or None
        state = request.form.get('state', '').strip() or None
        zip_code = request.form.get('zip_code', '').strip() or None
        country = request.form.get('country', '').strip() or 'United States' 
        phone_number = request.form.get('phone_number', '').strip() or None
        is_primary = request.form.get('is_primary') == 'on' 
        notes = request.form.get('notes', '').strip() or None

        if not location_name: raise ValueError("Location Name is required.")
        if not address: raise ValueError("Address is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction:
            logger.warning(f"add_location: Conn already in transaction. P:{doctor_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}", exc_info=True)
        
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if is_primary:
            cursor.execute("UPDATE doctor_locations SET is_primary = FALSE WHERE doctor_id = %s", (doctor_id,))

        query = """
            INSERT INTO doctor_locations (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        """
        params = (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes)
        cursor.execute(query, params)
        new_location_id = cursor.lastrowid
        
        conn.commit()
        operation_successful = True

        cursor.execute("SELECT * FROM doctor_locations WHERE doctor_location_id = %s", (new_location_id,))
        new_location_data = cursor.fetchone()
        
        # Format datetime for JSON response consistency
        created_at_val = new_location_data.get('created_at')
        if created_at_val and isinstance(created_at_val, datetime):
            new_location_data['created_at'] = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
        
        updated_at_val = new_location_data.get('updated_at')
        if updated_at_val and isinstance(updated_at_val, datetime): # Should be NOW() from insert
            new_location_data['updated_at'] = updated_at_val.strftime('%Y-%m-%d %H:%M:%S')


        return jsonify({"success": True, "message": "Location added successfully.", "location": new_location_data}), 201

    except ValueError as ve: return jsonify({"success": False, "message": str(ve)}), 400
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error adding location P:{doctor_id}: {err}", exc_info=True)
        return jsonify({"success": False, "message": "Database error adding location."}), 500
    except Exception as e:
        logger.error(f"Unexpected error adding location P:{doctor_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction and not operation_successful: 
                    logger.info(f"add_location: Rolling back due to failure. P:{doctor_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error add_location: {rb_err}", exc_info=True)
            finally: conn.close()

@locations_bp.route('/<int:location_id>/update', methods=['POST']) 
@login_required
def update_doctor_location(location_id):
    if not check_doctor_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        return jsonify({"success": False, "message": "Invalid session or provider ID missing."}), 401

    conn = None; cursor = None; operation_successful = False
    try:
        location_name = request.form.get('location_name', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip() or None
        state = request.form.get('state', '').strip() or None
        zip_code = request.form.get('zip_code', '').strip() or None
        country = request.form.get('country', '').strip() or 'United States'
        phone_number = request.form.get('phone_number', '').strip() or None
        is_primary = request.form.get('is_primary') == 'on'
        notes = request.form.get('notes', '').strip() or None
        
        if not location_name: raise ValueError("Location Name is required.")
        if not address: raise ValueError("Address is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction:
            logger.warning(f"update_location: Conn already in transaction. P:{doctor_id}, L_ID:{location_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}", exc_info=True)

        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s", (location_id, doctor_id))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Location not found or not authorized."}), 404

        if is_primary:
            cursor.execute("UPDATE doctor_locations SET is_primary = FALSE WHERE doctor_id = %s AND doctor_location_id != %s", (doctor_id, location_id))

        query = """
            UPDATE doctor_locations SET
            location_name = %s, address = %s, city = %s, state = %s, zip_code = %s, country = %s,
            phone_number = %s, is_primary = %s, notes = %s, updated_at = NOW() 
            WHERE doctor_location_id = %s AND doctor_id = %s
        """ 
        params = (location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, location_id, doctor_id)
        cursor.execute(query, params)
        
        conn.commit()
        operation_successful = True

        cursor.execute("SELECT * FROM doctor_locations WHERE doctor_location_id = %s", (location_id,))
        updated_location_data = cursor.fetchone()

        created_at_val = updated_location_data.get('created_at')
        if created_at_val and isinstance(created_at_val, datetime):
            updated_location_data['created_at'] = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
        
        updated_at_val = updated_location_data.get('updated_at') # Should be NOW() from update
        if updated_at_val and isinstance(updated_at_val, datetime):
            updated_location_data['updated_at'] = updated_at_val.strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({"success": True, "message": "Location updated successfully.", "location": updated_location_data}), 200

    except ValueError as ve: return jsonify({"success": False, "message": str(ve)}), 400
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error updating L_ID:{location_id} for P:{doctor_id}: {err}", exc_info=True)
        return jsonify({"success": False, "message": "Database error updating location."}), 500
    except Exception as e:
        logger.error(f"Unexpected error updating L_ID:{location_id} for P:{doctor_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction and not operation_successful: 
                    logger.info(f"update_location: Rolling back due to failure. P:{doctor_id}, L_ID:{location_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error update_location: {rb_err}", exc_info=True)
            finally: conn.close()

@locations_bp.route('/<int:location_id>/delete', methods=['POST']) 
@login_required
def delete_doctor_location(location_id):
    if not check_doctor_authorization(current_user):
        return jsonify({"success": False, "message": "Access Denied."}), 403
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        return jsonify({"success": False, "message": "Invalid session or provider ID missing."}), 401

    conn = None; cursor = None; operation_successful = False
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction:
            logger.warning(f"delete_location: Conn already in transaction. P:{doctor_id}, L_ID:{location_id}")
            try: conn.rollback()
            except Exception as e_rb: logger.error(f"Pre-emptive rollback failed: {e_rb}", exc_info=True)
        
        conn.start_transaction()
        cursor = conn.cursor()

        # Consider soft delete: "UPDATE doctor_locations SET is_active = FALSE WHERE ..."
        query = "DELETE FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s"
        cursor.execute(query, (location_id, doctor_id))

        if cursor.rowcount == 0:
            with conn.cursor() as check_cursor: # Use a separate cursor for this read
                check_cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s", (location_id,))
                exists = check_cursor.fetchone()
            status_code = 403 if exists else 404
            return jsonify({"success": False, "message": "Location not found or not authorized."}), status_code
        
        conn.commit()
        operation_successful = True
        return jsonify({"success": True, "message": "Location deleted successfully."}), 200

    except mysql.connector.Error as err:
        if err.errno == 1451: # FK constraint
             logger.error(f"FK Constraint error L_ID:{location_id} P:{doctor_id}: {err}")
             return jsonify({"success": False, "message": "Cannot delete location: it is referenced by other records (e.g., availability slots, appointments). Please remove these references first or deactivate the location if possible."}), 409 
        logger.error(f"DB Error deleting L_ID:{location_id} P:{doctor_id}: {err}", exc_info=True)
        return jsonify({"success": False, "message": "Database error deleting location."}), 500
    except ConnectionError as ce:
        logger.error(f"DB Conn Error deleting L_ID:{location_id} P:{doctor_id}: {ce}")
        return jsonify({"success": False, "message": "Database connection error."}), 500
    except Exception as e:
        logger.error(f"Unexpected error deleting L_ID:{location_id} P:{doctor_id}: {e}", exc_info=True)
        return jsonify({"success": False, "message": "An unexpected error occurred."}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected():
            try:
                if conn.in_transaction and not operation_successful: 
                    logger.info(f"delete_location: Rolling back due to failure. P:{doctor_id}, L_ID:{location_id}")
                    conn.rollback()
            except Exception as rb_err: logger.error(f"Rollback error delete_location: {rb_err}", exc_info=True)
            finally: conn.close()