# your_project/routes/Doctor_Portal/vaccine_management.py

import mysql.connector
import re
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort, send_from_directory
)
from flask_login import login_required, current_user
# from werkzeug.utils import secure_filename # Not strictly needed if not handling file uploads for vaccines
import os
from db import get_db_connection
from datetime import datetime # Import datetime for created_at/updated_at if managed by app
import math

# --- Utils (from disease_management.py, adapt as needed) ---
def check_doctor_authorization(user):
    return user.is_authenticated and getattr(user, 'user_type', None) == 'doctor'

def get_enum_values(table_name, column_name):
    conn = None; cursor = None; enum_values = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        safe_table_name = '`' + table_name.replace('`', '``') + '`'
        safe_column_name = column_name.replace("'", "''")
        query = f"SHOW COLUMNS FROM {safe_table_name} LIKE '{safe_column_name}'"
        cursor.execute(query); result = cursor.fetchone()
        if result and 'Type' in result:
            type_info = result['Type']
            match = re.match(r"enum\((.*)\)", type_info, re.IGNORECASE)
            if match:
                enum_values = [val.strip().strip("'") for val in match.group(1).split(',')]
    except Exception as e: current_app.logger.error(f"Error getting ENUM {table_name}.{column_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return enum_values

def get_all_simple(table_name, id_column, name_column, order_by_name=True, where_clause=None, params=None):
    conn = None; cursor = None; results = []
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name) or \
       not re.match(r'^[a-zA-Z0-9_]+$', id_column) or \
       not re.match(r'^[a-zA-Z0-9_]+$', name_column):
        current_app.logger.error(f"Invalid table/col name in get_all_simple: {table_name}, {id_column}, {name_column}")
        return []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        safe_table, safe_id_col, safe_name_col = f"`{table_name}`", f"`{id_column}`", f"`{name_column}`"
        order_clause = f"ORDER BY {safe_name_col} ASC" if order_by_name else ""
        where_sql = f" WHERE {where_clause}" if where_clause else ""
        query = f"SELECT {safe_id_col}, {safe_name_col} FROM {safe_table} {where_sql} {order_clause}"

        if params:
            cursor.execute(query, tuple(params))
        else:
            cursor.execute(query)
        results = cursor.fetchall()
    except Exception as e: current_app.logger.error(f"Error in get_all_simple for {table_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return results


# --- Blueprint Definition ---
vaccine_management_bp = Blueprint(
    'vaccine_management',
    __name__,
    url_prefix='/doctor/vaccines',
    template_folder='../../templates' # Assuming templates are in project_root/templates/Doctor_Portal/Vaccines/
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 15
VALID_SORT_COLUMNS_VACCINES = {
    'name': 'v.vaccine_name',
    'category': 'vc.category_name',
    'type': 'v.vaccine_type',
    'manufacturer': 'v.manufacturer',
    'id': 'v.vaccine_id'
}
DEFAULT_SORT_COLUMN_VACCINES = 'name'
DEFAULT_SORT_DIRECTION_VACCINES = 'ASC'

# --- Data Fetching Helpers specific to Vaccines ---
def get_all_vaccine_categories():
    return get_all_simple('vaccine_categories', 'category_id', 'category_name')

def get_paginated_vaccines(page=1, per_page=ITEMS_PER_PAGE, search_term=None,
                           sort_by=DEFAULT_SORT_COLUMN_VACCINES, sort_dir=DEFAULT_SORT_DIRECTION_VACCINES,
                           filters=None):
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS_VACCINES.get(sort_by, VALID_SORT_COLUMNS_VACCINES[DEFAULT_SORT_COLUMN_VACCINES])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql_select = """SELECT SQL_CALC_FOUND_ROWS
                            v.vaccine_id, v.vaccine_name, v.abbreviation, v.vaccine_type,
                            v.manufacturer, vc.category_name
                        """
        sql_from = """ FROM vaccines v
                       LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id
                   """
        sql_where = " WHERE v.is_active = TRUE" # Assuming soft delete with is_active
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += """ AND (v.vaccine_name LIKE %s OR v.abbreviation LIKE %s OR
                                  v.diseases_prevented LIKE %s OR vc.category_name LIKE %s OR
                                  v.manufacturer LIKE %s) """
            params.extend([search_like] * 5)

        if valid_filters.get('category_id'):
            sql_where += " AND v.category_id = %s"; params.append(valid_filters['category_id'])
        if valid_filters.get('vaccine_type'): # If filtering by type
            sql_where += " AND v.vaccine_type = %s"; params.append(valid_filters['vaccine_type'])

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        cursor.execute("SELECT FOUND_ROWS() as total"); result['total'] = cursor.fetchone()['total']

    except Exception as err:
        current_app.logger.error(f"Error in get_paginated_vaccines: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_vaccine_details_full(vaccine_id):
    conn = None; cursor = None; vaccine_details = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """SELECT v.*, vc.category_name
                 FROM vaccines v
                 LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id
                 WHERE v.vaccine_id = %s AND v.is_active = TRUE"""
        cursor.execute(sql, (vaccine_id,))
        vaccine_details = cursor.fetchone()
    except Exception as err:
        current_app.logger.error(f"Error in get_vaccine_details_full for ID {vaccine_id}: {err}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return vaccine_details

def get_vaccine_basic_info(vaccine_id): # For pre-filling edit form
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM vaccines WHERE vaccine_id = %s AND is_active = TRUE", (vaccine_id,))
        return cursor.fetchone()
    except Exception as err:
        current_app.logger.error(f"Error in get_vaccine_basic_info for ID {vaccine_id}: {err}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return None # Explicit return if try fails before assignment


# --- Routes ---
@vaccine_management_bp.route('/', methods=['GET'])
@login_required
def list_vaccines():
    if not check_doctor_authorization(current_user): abort(403)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN_VACCINES).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION_VACCINES).upper()

    filters = {}
    if request.args.get('filter_category_id'):
        filters['category_id'] = request.args.get('filter_category_id')
    if request.args.get('filter_vaccine_type'):
        filters['vaccine_type'] = request.args.get('filter_vaccine_type')

    if sort_by not in VALID_SORT_COLUMNS_VACCINES: sort_by = DEFAULT_SORT_COLUMN_VACCINES
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION_VACCINES

    result = get_paginated_vaccines(page=page, per_page=ITEMS_PER_PAGE, search_term=search,
                                  sort_by=sort_by, sort_dir=sort_dir, filters=filters)

    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and result['total'] > 0 else 0

    filter_options = {
        'categories': get_all_vaccine_categories(),
        'vaccine_types': get_enum_values('vaccines', 'vaccine_type') # Assuming 'vaccine_type' is ENUM in vaccines table
                                                                # Or fetch from a dedicated vaccine_types lookup table
    }

    return render_template(
        'Doctor_Portal/Vaccines/vaccine_list.html',
        vaccines=result['items'],
        search_term=search,
        current_page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=filters,
        valid_sort_columns=VALID_SORT_COLUMNS_VACCINES,
        **filter_options,
        request_args=request.args
    )

@vaccine_management_bp.route('/<int:vaccine_id>', methods=['GET'])
@login_required
def view_vaccine(vaccine_id):
    if not check_doctor_authorization(current_user): abort(403)
    vaccine = get_vaccine_details_full(vaccine_id)
    if not vaccine:
        flash("Vaccine not found or is inactive.", "warning")
        return redirect(url_for('.list_vaccines'))
    return render_template('Doctor_Portal/Vaccines/vaccine_detail.html', vaccine=vaccine)

@vaccine_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_vaccine():
    if not check_doctor_authorization(current_user): abort(403)

    dropdown_options = {
        'categories': get_all_vaccine_categories(),
        'vaccine_types_enum': get_enum_values('vaccines', 'vaccine_type') # if vaccine_type is an ENUM
        # Add more dropdowns if other fields like 'administration_route' are ENUMs or lookup tables
    }

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        try:
            form = request.form
            vaccine_name = form.get('vaccine_name', '').strip()
            category_id_str = form.get('category_id', '')
            abbreviation = form.get('abbreviation', '').strip() or None
            diseases_prevented = form.get('diseases_prevented', '').strip()
            recommended_for = form.get('recommended_for', '').strip() or None
            benefits = form.get('benefits', '').strip() or None
            timing_schedule = form.get('timing_schedule', '').strip() or None
            number_of_doses = form.get('number_of_doses', '').strip() or None
            booster_information = form.get('booster_information', '').strip() or None
            vaccine_type = form.get('vaccine_type', '').strip() or None # If free text or selected from ENUM
            administration_route = form.get('administration_route', '').strip() or None
            common_side_effects = form.get('common_side_effects', '').strip() or None
            contraindications_precautions = form.get('contraindications_precautions', '').strip() or None
            manufacturer = form.get('manufacturer', '').strip() or None
            notes = form.get('notes', '').strip() or None

            # --- Validation ---
            if not vaccine_name: errors.append("Vaccine Name is required.")
            if not category_id_str or not category_id_str.isdigit():
                errors.append("A valid Category is required.")
            else:
                category_id = int(category_id_str)
            if not diseases_prevented: errors.append("Diseases Prevented is required.")
            # Add more specific validations as needed (e.g., for vaccine_type if from ENUM)

            if errors: raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            # Add 'is_active = TRUE' and 'created_at = NOW(), updated_at = NOW()' to your SQL
            # The DB schema script you provided sets these with DEFAULTs, so an explicit insert is okay
            # but not strictly necessary for `created_at` and `updated_at` if using DB defaults.
            # I'll add them to be explicit. Assuming 'is_active' TINYINT(1) or BOOLEAN.
            sql_insert_vaccine = """
                INSERT INTO vaccines (
                    category_id, vaccine_name, abbreviation, diseases_prevented,
                    recommended_for, benefits, timing_schedule, number_of_doses,
                    booster_information, vaccine_type, administration_route,
                    common_side_effects, contraindications_precautions, manufacturer, notes,
                    is_active, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    TRUE, NOW(), NOW()
                )
            """
            params_vaccine = (
                category_id, vaccine_name, abbreviation, diseases_prevented,
                recommended_for, benefits, timing_schedule, number_of_doses,
                booster_information, vaccine_type, administration_route,
                common_side_effects, contraindications_precautions, manufacturer, notes
            )
            cursor.execute(sql_insert_vaccine, params_vaccine)
            new_vaccine_id = cursor.lastrowid
            if not new_vaccine_id:
                conn.rollback()
                raise mysql.connector.Error("Failed to insert vaccine.")

            conn.commit()
            flash(f"Vaccine '{vaccine_name}' added successfully.", "success")
            return redirect(url_for('.view_vaccine', vaccine_id=new_vaccine_id))

        except ValueError: # Catches custom validation errors
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"DB/Connection Error Adding Vaccine: {err}", exc_info=True)
            flash(f"Database error: {getattr(err, 'msg', str(err))}", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"Unexpected Error Adding Vaccine: {e}", exc_info=True)
            flash("An unexpected error occurred while adding the vaccine.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # If POST failed, re-render form with submitted data and errors
        return render_template(
            'Doctor_Portal/Vaccines/vaccine_form.html',
            form_action=url_for('.add_vaccine'),
            form_title="Add New Vaccine",
            vaccine=request.form, # Repopulate with submitted data
            errors=errors,
            **dropdown_options
        )

    # GET request
    return render_template(
        'Doctor_Portal/Vaccines/vaccine_form.html',
        form_action=url_for('.add_vaccine'),
        form_title="Add New Vaccine",
        vaccine=None, # No pre-filled data for add
        **dropdown_options
    )

@vaccine_management_bp.route('/<int:vaccine_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_vaccine(vaccine_id):
    if not check_doctor_authorization(current_user): abort(403)

    dropdown_options = {
        'categories': get_all_vaccine_categories(),
        'vaccine_types_enum': get_enum_values('vaccines', 'vaccine_type')
    }

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        try:
            form = request.form
            vaccine_name = form.get('vaccine_name', '').strip()
            category_id_str = form.get('category_id', '')
            # ... (collect all other form fields similar to add_vaccine) ...
            abbreviation = form.get('abbreviation', '').strip() or None
            diseases_prevented = form.get('diseases_prevented', '').strip()
            recommended_for = form.get('recommended_for', '').strip() or None
            benefits = form.get('benefits', '').strip() or None
            timing_schedule = form.get('timing_schedule', '').strip() or None
            number_of_doses = form.get('number_of_doses', '').strip() or None
            booster_information = form.get('booster_information', '').strip() or None
            vaccine_type = form.get('vaccine_type', '').strip() or None
            administration_route = form.get('administration_route', '').strip() or None
            common_side_effects = form.get('common_side_effects', '').strip() or None
            contraindications_precautions = form.get('contraindications_precautions', '').strip() or None
            manufacturer = form.get('manufacturer', '').strip() or None
            notes = form.get('notes', '').strip() or None

            # --- Validation ---
            if not vaccine_name: errors.append("Vaccine Name is required.")
            if not category_id_str or not category_id_str.isdigit():
                errors.append("A valid Category is required.")
            else:
                category_id = int(category_id_str)
            if not diseases_prevented: errors.append("Diseases Prevented is required.")
            # Add more specific validations as needed

            if errors: raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            # Your DB schema sets updated_at automatically on update.
            # is_active should remain TRUE for active records.
            sql_update_vaccine = """
                UPDATE vaccines SET
                    category_id = %s, vaccine_name = %s, abbreviation = %s, diseases_prevented = %s,
                    recommended_for = %s, benefits = %s, timing_schedule = %s, number_of_doses = %s,
                    booster_information = %s, vaccine_type = %s, administration_route = %s,
                    common_side_effects = %s, contraindications_precautions = %s,
                    manufacturer = %s, notes = %s
                    -- updated_at is handled by DB if schema defines it
                WHERE vaccine_id = %s AND is_active = TRUE
            """ # If your schema does not auto update updated_at: ", updated_at = NOW()"
            params_vaccine = (
                category_id, vaccine_name, abbreviation, diseases_prevented,
                recommended_for, benefits, timing_schedule, number_of_doses,
                booster_information, vaccine_type, administration_route,
                common_side_effects, contraindications_precautions, manufacturer, notes,
                vaccine_id
            )
            cursor.execute(sql_update_vaccine, params_vaccine)

            if cursor.rowcount == 0: # No rows updated, possibly vaccine_id not found or already inactive
                conn.rollback()
                flash("Vaccine not found or no changes made.", "warning")
                # It's better to redirect than re-render if the record genuinely doesn't exist for editing.
                # If it's just "no changes made", re-rendering might be okay.
                # For simplicity now, we'll assume the record might have been deactivated by another user.
                return redirect(url_for('.list_vaccines'))


            conn.commit()
            flash(f"Vaccine '{vaccine_name}' updated successfully.", "success")
            return redirect(url_for('.view_vaccine', vaccine_id=vaccine_id))

        except ValueError: # Validation
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"DB/Connection Error Editing Vaccine {vaccine_id}: {err}", exc_info=True)
            flash(f"Database error: {getattr(err, 'msg', str(err))}", "danger")
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            current_app.logger.error(f"Unexpected Error Editing Vaccine {vaccine_id}: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Repopulate form on error
        form_data_on_error = request.form.to_dict()
        form_data_on_error['vaccine_id'] = vaccine_id # Keep ID for form action
        return render_template(
            'Doctor_Portal/Vaccines/vaccine_form.html',
            form_action=url_for('.edit_vaccine', vaccine_id=vaccine_id),
            form_title=f"Edit Vaccine (ID: {vaccine_id})",
            vaccine=form_data_on_error,
            errors=errors,
            **dropdown_options
        )

    # GET request
    vaccine_data = get_vaccine_basic_info(vaccine_id)
    if not vaccine_data:
        flash("Vaccine not found or is inactive.", "warning")
        return redirect(url_for('.list_vaccines'))

    return render_template(
        'Doctor_Portal/Vaccines/vaccine_form.html',
        form_action=url_for('.edit_vaccine', vaccine_id=vaccine_id),
        form_title=f"Edit Vaccine: {vaccine_data.get('vaccine_name', 'N/A')}",
        vaccine=vaccine_data,
        **dropdown_options
    )


@vaccine_management_bp.route('/<int:vaccine_id>/delete', methods=['POST'])
@login_required
def delete_vaccine(vaccine_id): # Soft delete
    if not check_doctor_authorization(current_user): abort(403)
    conn = None; cursor = None
    try:
        # Optionally, first check if the vaccine exists and is active
        # current_vaccine = get_vaccine_basic_info(vaccine_id)
        # if not current_vaccine:
        #     flash("Vaccine not found or already inactive.", "warning")
        #     return redirect(url_for('.list_vaccines'))

        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        # Your DB schema might automatically set updated_at.
        cursor.execute("UPDATE vaccines SET is_active = FALSE WHERE vaccine_id = %s", (vaccine_id,))
        # If schema doesn't auto update: "UPDATE vaccines SET is_active = FALSE, updated_at = NOW() WHERE vaccine_id = %s"


        if cursor.rowcount == 0:
            flash("Vaccine not found or could not be deactivated.", "warning")
            conn.rollback()
        else:
            conn.commit()
            flash("Vaccine successfully deactivated.", "success")

    except Exception as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        current_app.logger.error(f"Error deactivating vaccine {vaccine_id}: {err}", exc_info=True)
        flash("Error deactivating vaccine.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_vaccines'))