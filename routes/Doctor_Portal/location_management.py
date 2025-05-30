# routes/Doctor_Portal/locations/location_management.py

import mysql.connector
from flask import (
    Blueprint, request, jsonify, current_app, flash, redirect, url_for, render_template, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
import logging
from datetime import datetime

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
            created_at_val = loc.get('created_at')
            if created_at_val and isinstance(created_at_val, datetime):
                loc['created_at'] = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
            
            updated_at_val = loc.get('updated_at')
            if updated_at_val and isinstance(updated_at_val, datetime):
                loc['updated_at'] = updated_at_val.strftime('%Y-%m-%d %H:%M:%S')
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error fetching locations for P:{doctor_id}: {err}", exc_info=True)
        raise 
    except Exception as e:
        logger.error(f"Unexpected error fetching locations for P:{doctor_id}: {e}", exc_info=True)
        raise 
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return locations

def get_doctor_location_details(doctor_id, location_id):
    conn = None; cursor = None; location = None
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM doctor_locations WHERE doctor_id = %s AND doctor_location_id = %s AND is_active = TRUE"
        cursor.execute(query, (doctor_id, location_id))
        location = cursor.fetchone()
        if location:
            created_at_val = location.get('created_at')
            if created_at_val and isinstance(created_at_val, datetime):
                location['created_at'] = created_at_val.strftime('%Y-%m-%d %H:%M:%S')
            updated_at_val = location.get('updated_at')
            if updated_at_val and isinstance(updated_at_val, datetime):
                location['updated_at'] = updated_at_val.strftime('%Y-%m-%d %H:%M:%S')
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error fetching location L_ID:{location_id} for P:{doctor_id}: {err}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching location L_ID:{location_id} for P:{doctor_id}: {e}", exc_info=True)
        raise
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return location


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

    return render_template('Doctor_Portal/locations/location_management.html', locations=current_locations)

# --- Route to display Add Location Page ---
@locations_bp.route('/new', methods=['GET'])
@login_required
def add_location_page():
    if not check_doctor_authorization(current_user):
        abort(403)
    # Pass an empty dictionary or specific default values for the form if needed
    return render_template('Doctor_Portal/locations/add_location.html', location={})


# --- Route to display Edit Location Page ---
@locations_bp.route('/<int:location_id>/edit', methods=['GET'])
@login_required
def edit_location_page(location_id):
    if not check_doctor_authorization(current_user):
        abort(403)
    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        flash("Invalid user session.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    try:
        location = get_doctor_location_details(doctor_id, location_id)
    except Exception as e:
        logger.error(f"Error fetching location details for edit page P:{doctor_id} L:{location_id}: {e}", exc_info=True)
        flash("Could not load location details for editing.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    if not location:
        flash("Location not found or you are not authorized to edit it.", "warning")
        return redirect(url_for('locations.manage_locations_page'))
    
    return render_template('Doctor_Portal/locations/edit_location.html', location=location)


# --- Routes for Location Management (CRUD operations) ---

@locations_bp.route('/add', methods=['POST']) 
@login_required
def add_doctor_location():
    if not check_doctor_authorization(current_user):
        # For standard form POST, abort or redirect with flash is better than JSON
        flash("Access Denied.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        flash("Invalid session or provider ID missing.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    # Store form data to re-populate form in case of error
    form_data = request.form.to_dict()

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
        google_maps_link = request.form.get('google_maps_link', '').strip() or None

        if not location_name: raise ValueError("Location Name is required.")
        if not address: raise ValueError("Address is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        
        if conn.in_transaction:
             logger.warning(f"add_location: Conn already in transaction for P:{doctor_id}. Attempting rollback.")
             try: conn.rollback()
             except Exception as rb_ex: logger.error(f"Rollback attempt failed for P:{doctor_id}: {rb_ex}")
        
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if is_primary:
            cursor.execute("UPDATE doctor_locations SET is_primary = FALSE WHERE doctor_id = %s", (doctor_id,))

        query = """
            INSERT INTO doctor_locations 
            (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, is_active, google_maps_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
        """
        params = (doctor_id, location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, google_maps_link)
        cursor.execute(query, params)
        # new_location_id = cursor.lastrowid # Not strictly needed for redirect flow
        
        conn.commit()
        operation_successful = True
        flash("Location added successfully.", "success")
        return redirect(url_for('locations.manage_locations_page'))

    except ValueError as ve: 
        flash(str(ve), "danger")
        # Re-render the add form with the data they entered and the error
        return render_template('Doctor_Portal/locations/add_location.html', location=form_data, error=str(ve))
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error adding location P:{doctor_id}: {err}", exc_info=True)
        flash("Database error adding location. Please try again.", "danger")
        return render_template('Doctor_Portal/locations/add_location.html', location=form_data, error="Database error.")
    except Exception as e:
        logger.error(f"Unexpected error adding location P:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred. Please try again.", "danger")
        return render_template('Doctor_Portal/locations/add_location.html', location=form_data, error="Unexpected error.")
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
        flash("Access Denied.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    doctor_id = get_provider_id(current_user)
    if doctor_id is None:
        flash("Invalid session or provider ID missing.", "danger")
        return redirect(url_for('locations.manage_locations_page'))

    # Store form data to re-populate form in case of error
    form_data = request.form.to_dict()
    # Add location_id to form_data for re-rendering edit page
    form_data['doctor_location_id'] = location_id


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
        google_maps_link = request.form.get('google_maps_link', '').strip() or None
        
        if not location_name: raise ValueError("Location Name is required.")
        if not address: raise ValueError("Address is required.")

        conn = get_db_connection()
        if not conn: raise ConnectionError("DB Connection failed.")
        if conn.in_transaction:
            logger.warning(f"update_location: Conn already in transaction for P:{doctor_id}, L:{location_id}. Attempting rollback.")
            try: conn.rollback()
            except Exception as rb_ex: logger.error(f"Rollback attempt failed for P:{doctor_id}, L:{location_id}: {rb_ex}")

        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        # Verify ownership before update
        cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s", (location_id, doctor_id))
        if not cursor.fetchone():
            flash("Location not found or not authorized for update.", "warning")
            return redirect(url_for('locations.manage_locations_page'))

        if is_primary:
            cursor.execute("UPDATE doctor_locations SET is_primary = FALSE WHERE doctor_id = %s AND doctor_location_id != %s", (doctor_id, location_id))

        query = """
            UPDATE doctor_locations SET
            location_name = %s, address = %s, city = %s, state = %s, zip_code = %s, country = %s,
            phone_number = %s, is_primary = %s, notes = %s, updated_at = NOW(),
            google_maps_link = %s 
            WHERE doctor_location_id = %s AND doctor_id = %s
        """ 
        params = (location_name, address, city, state, zip_code, country, phone_number, is_primary, notes, google_maps_link, location_id, doctor_id)
        cursor.execute(query, params)
        
        conn.commit()
        operation_successful = True
        flash("Location updated successfully.", "success")
        return redirect(url_for('locations.manage_locations_page'))

    except ValueError as ve:
        flash(str(ve), "danger")
        return render_template('Doctor_Portal/locations/edit_location.html', location=form_data, error=str(ve))
    except (mysql.connector.Error, ConnectionError) as err:
        logger.error(f"DB/Conn Error updating L_ID:{location_id} for P:{doctor_id}: {err}", exc_info=True)
        flash("Database error updating location. Please try again.", "danger")
        return render_template('Doctor_Portal/locations/edit_location.html', location=form_data, error="Database error.")
    except Exception as e:
        logger.error(f"Unexpected error updating L_ID:{location_id} for P:{doctor_id}: {e}", exc_info=True)
        flash("An unexpected error occurred. Please try again.", "danger")
        return render_template('Doctor_Portal/locations/edit_location.html', location=form_data, error="Unexpected error.")
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
    # This endpoint will still be called via AJAX/fetch from the main list page.
    # So, it should still return JSON.
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
            logger.warning(f"delete_location: Conn already in transaction for P:{doctor_id}, L:{location_id}. Attempting rollback.")
            try: conn.rollback()
            except Exception as rb_ex: logger.error(f"Rollback attempt failed for P:{doctor_id}, L:{location_id}: {rb_ex}")
        
        conn.start_transaction()
        cursor = conn.cursor() 

        query = "DELETE FROM doctor_locations WHERE doctor_location_id = %s AND doctor_id = %s"
        cursor.execute(query, (location_id, doctor_id))

        if cursor.rowcount == 0:
            exists_check_cursor = conn.cursor(dictionary=True)
            exists_check_cursor.execute("SELECT 1 FROM doctor_locations WHERE doctor_location_id = %s", (location_id,))
            exists = exists_check_cursor.fetchone()
            exists_check_cursor.close()
            
            status_code = 403 if exists else 404 
            return jsonify({"success": False, "message": "Location not found or not authorized for deletion."}), status_code
        
        conn.commit()
        operation_successful = True
        return jsonify({"success": True, "message": "Location deleted successfully."}), 200

    except mysql.connector.Error as err:
        if err.errno == 1451: 
             logger.warning(f"FK Constraint error on delete L_ID:{location_id} P:{doctor_id}: {err}")
             return jsonify({"success": False, "message": "Cannot delete location: it's currently in use (e.g., by appointments or availability schedules). Please update those records first."}), 409 
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