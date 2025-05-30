# your_project/routes/Doctor_Portal/vaccine_management.py

import mysql.connector
import re
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    current_app, abort
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import get_db_connection
from datetime import datetime
import math
import logging

module_logger = logging.getLogger(__name__)

# --- Import Utility Functions ---
try:
    from utils.directory_configs import allowed_file 
    # Assuming get_relative_upload_path is not used in this specific file directly for now.
    # If generate_secure_filename_from_file is in directory_configs, use it.
    # from utils.directory_configs import generate_secure_filename_from_file 
    module_logger.info("Successfully imported 'allowed_file' for vaccine_management.")
except ImportError as e:
    module_logger.critical(f"CRITICAL: Failed to import 'allowed_file' from directory_configs: {e}. Using basic fallback.", exc_info=True)
    def allowed_file(filename, config_key='ALLOWED_IMAGE_EXTENSIONS'):
        module_logger.error(f"FALLBACK allowed_file used for {filename} with key {config_key}!")
        basic_allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in basic_allowed

# --- LOCAL Authorization Helper ---
def is_doctor():
    return current_user.is_authenticated and getattr(current_user, 'user_type', None) == 'doctor'

# --- Custom Helper for Filename Generation ---
def generate_custom_secure_filename(original_filename, prefix=""):
    filename = secure_filename(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}{timestamp}_{filename}"

def get_enum_values(table_name, column_name):
    conn = None; cursor = None; enum_values = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        safe_table_name = '`' + re.sub(r'[^a-zA-Z0-9_]', '', table_name) + '`'
        safe_column_name = re.sub(r'[^a-zA-Z0-9_]', '', column_name)
        query = f"SHOW COLUMNS FROM {safe_table_name} LIKE '{safe_column_name}'"
        cursor.execute(query); result = cursor.fetchone()
        if result and 'Type' in result:
            type_info = result['Type']
            match = re.match(r"enum\((.*?)\)$", type_info, re.IGNORECASE)
            if match:
                enum_values = [val.strip().strip("'").strip('"') for val in match.group(1).split(',')]
    except Exception as e: 
        current_app.logger.error(f"Error getting ENUM {table_name}.{column_name}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return enum_values

vaccine_management_bp = Blueprint(
    'vaccine_management',
    __name__,
    url_prefix='/doctor/vaccines',
    template_folder='../../templates' 
)

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

def get_all_vaccine_categories_with_details(include_inactive=False):
    conn = None; cursor = None; categories = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        where_clause = "" if include_inactive else "WHERE vc.is_active = TRUE"
        query = f"""
            SELECT vc.category_id, vc.category_name, vc.description, 
                   vc.target_group, vc.image_filename, 
                   COUNT(DISTINCT v.vaccine_id) as vaccine_count 
            FROM vaccine_categories vc
            LEFT JOIN vaccines v ON vc.category_id = v.category_id AND v.is_active = TRUE
            {where_clause}
            GROUP BY vc.category_id, vc.category_name, vc.description, vc.target_group, vc.image_filename
            ORDER BY vc.category_name ASC
        """
        cursor.execute(query)
        categories = cursor.fetchall()
    except Exception as e:
        current_app.logger.error(f"Error fetching vaccine categories with details: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return categories

def get_vaccine_category_by_id(category_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT category_id, category_name, description, target_group, image_filename, is_active FROM vaccine_categories WHERE category_id = %s", (category_id,))
        return cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Error fetching category {category_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return None

def get_paginated_vaccines(page=1, per_page=ITEMS_PER_PAGE, search_term=None,
                           sort_by=DEFAULT_SORT_COLUMN_VACCINES, sort_dir=DEFAULT_SORT_DIRECTION_VACCINES,
                           filters=None, category_id_filter=None):
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS_VACCINES.get(sort_by, VALID_SORT_COLUMNS_VACCINES[DEFAULT_SORT_COLUMN_VACCINES])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql_select = "SELECT SQL_CALC_FOUND_ROWS v.vaccine_id, v.vaccine_name, v.abbreviation, v.vaccine_type, v.manufacturer, vc.category_name"
        sql_from = " FROM vaccines v LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id"
        sql_where = " WHERE v.is_active = TRUE" 
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (v.vaccine_name LIKE %s OR v.abbreviation LIKE %s OR v.diseases_prevented LIKE %s OR vc.category_name LIKE %s OR v.manufacturer LIKE %s)"
            params.extend([search_like] * 5)

        if valid_filters.get('category_id'):
            sql_where += " AND v.category_id = %s"; params.append(valid_filters['category_id'])
        
        if category_id_filter:
             sql_where += " AND v.category_id = %s"; params.append(category_id_filter)
             
        if valid_filters.get('vaccine_type'):
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
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT v.*, vc.category_name FROM vaccines v LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id WHERE v.vaccine_id = %s AND v.is_active = TRUE"
        cursor.execute(sql, (vaccine_id,))
        return cursor.fetchone()
    except Exception as err:
        current_app.logger.error(f"Error in get_vaccine_details_full for ID {vaccine_id}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return None

def get_vaccine_basic_info(vaccine_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM vaccines WHERE vaccine_id = %s AND is_active = TRUE", (vaccine_id,))
        return cursor.fetchone()
    except Exception as err:
        current_app.logger.error(f"Error in get_vaccine_basic_info for ID {vaccine_id}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return None

@vaccine_management_bp.route('/categories', methods=['GET'])
@login_required
def list_vaccine_categories():
    if not is_doctor(): abort(403)
    categories = get_all_vaccine_categories_with_details()
    return render_template('Doctor_Portal/Vaccines/category_list.html', categories=categories)

@vaccine_management_bp.route('/categories/add', methods=['GET', 'POST'])
@login_required
def add_vaccine_category():
    if not is_doctor(): abort(403)
    
    if request.method == 'POST':
        category_name = request.form.get('category_name', '').strip() # Use category_name
        description = request.form.get('description', '').strip() or None
        target_group = request.form.get('target_group', '').strip() or None
        image_file = request.files.get('image_file')
        image_filename_for_db = None
        errors = []

        if not category_name: errors.append("Category Name is required.")

        if image_file and image_file.filename:
            if allowed_file(image_file.filename, 'ALLOWED_IMAGE_EXTENSIONS'): 
                upload_folder = current_app.config.get('UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES')
                if not upload_folder:
                    errors.append("Server error: Upload folder for category images not configured.")
                    current_app.logger.error("UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES not configured in app.config.")
                else:
                    filename = generate_custom_secure_filename(image_file.filename, prefix="cat_") 
                    try:
                        os.makedirs(upload_folder, exist_ok=True)
                        image_file.save(os.path.join(upload_folder, filename))
                        image_filename_for_db = filename 
                    except Exception as e:
                        errors.append(f"Could not save image: {str(e)}")
                        current_app.logger.error(f"Error saving category image: {e}", exc_info=True)
            else:
                allowed_types_str = ", ".join(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', []))
                errors.append(f"Invalid image file type. Allowed: {allowed_types_str}.")
        
        if errors:
            for error_msg in errors: flash(error_msg, 'danger')
            category_form_data = request.form.to_dict() # Get all form data for repopulation
            return render_template('Doctor_Portal/Vaccines/category_form.html', 
                                   form_title="Add New Vaccine Category", 
                                   category=category_form_data, 
                                   form_action=url_for('.add_vaccine_category'),
                                   errors=errors)
        else:
            conn = None; cursor = None
            try:
                conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
                sql = """INSERT INTO vaccine_categories 
                         (category_name, description, target_group, image_filename, is_active, created_at, updated_at) 
                         VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())"""
                cursor.execute(sql, (category_name, description, target_group, image_filename_for_db))
                conn.commit()
                flash(f"Vaccine category '{category_name}' added successfully.", "success")
                return redirect(url_for('.list_vaccine_categories'))
            except mysql.connector.Error as err:
                if conn: conn.rollback() 
                flash(f"Database error adding category: {err.msg}", "danger")
                current_app.logger.error(f"DB error adding category: {err}", exc_info=True)
            except Exception as e: 
                if conn: conn.rollback()
                flash(f"An unexpected error occurred: {str(e)}", "danger")
                current_app.logger.error(f"Unexpected error adding category: {e}", exc_info=True)
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
        
        category_form_data_after_fail = request.form.to_dict()
        return render_template('Doctor_Portal/Vaccines/category_form.html', 
                               form_title="Add New Vaccine Category", 
                               category=category_form_data_after_fail, 
                               form_action=url_for('.add_vaccine_category'),
                               errors=errors if 'errors' in locals() else ["An error occurred saving the category."])

    return render_template('Doctor_Portal/Vaccines/category_form.html', 
                           form_title="Add New Vaccine Category",
                           category={}, 
                           form_action=url_for('.add_vaccine_category'))

@vaccine_management_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_vaccine_category(category_id):
    if not is_doctor(): abort(403)
    category = get_vaccine_category_by_id(category_id)
    if not category:
        flash("Vaccine category not found.", "warning")
        return redirect(url_for('.list_vaccine_categories'))

    if request.method == 'POST':
        category_name_form = request.form.get('category_name', '').strip() # Use category_name
        description_form = request.form.get('description', '').strip() or None
        target_group_form = request.form.get('target_group', '').strip() or None
        image_file = request.files.get('image_file')
        current_image_filename = category.get('image_filename')
        new_image_filename = current_image_filename
        errors = []

        if not category_name_form: errors.append("Category name is required.")

        if image_file and image_file.filename:
            if allowed_file(image_file.filename, 'ALLOWED_IMAGE_EXTENSIONS'):
                upload_folder = current_app.config.get('UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES')
                if not upload_folder:
                    errors.append("Server error: Upload folder for category images not configured.")
                    current_app.logger.error("UPLOAD_FOLDER_VACCINE_CATEGORY_IMAGES not configured in app.config.")
                else:
                    filename = generate_custom_secure_filename(image_file.filename, prefix="cat_")
                    try:
                        os.makedirs(upload_folder, exist_ok=True)
                        image_file.save(os.path.join(upload_folder, filename))
                        new_image_filename = filename
                        if current_image_filename and current_image_filename != new_image_filename:
                            old_path = os.path.join(upload_folder, current_image_filename)
                            if os.path.exists(old_path): 
                                try: os.remove(old_path)
                                except OSError as oe: current_app.logger.error(f"Error deleting old image {old_path}: {oe}")
                    except Exception as e:
                        errors.append(f"Could not save new image: {str(e)}")
                        current_app.logger.error(f"Error saving new category image: {e}", exc_info=True)
            else:
                allowed_types_str = ", ".join(current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', []))
                errors.append(f"Invalid new image file type. Allowed: {allowed_types_str}.")
        
        if errors:
            for error_msg in errors: flash(error_msg, 'danger')
        else:
            conn = None; cursor = None
            try:
                conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
                sql = """UPDATE vaccine_categories SET 
                         category_name = %s, description = %s, target_group = %s, image_filename = %s
                         WHERE category_id = %s""" # updated_at is auto
                cursor.execute(sql, (category_name_form, description_form, target_group_form, new_image_filename, category_id))
                conn.commit()
                flash(f"Vaccine category '{category_name_form}' updated successfully.", "success")
                return redirect(url_for('.list_vaccine_categories'))
            except mysql.connector.Error as err:
                if conn: conn.rollback()
                flash(f"Database error updating category: {err.msg}", "danger")
                current_app.logger.error(f"DB error updating category {category_id}: {err}", exc_info=True)
            except Exception as e:
                if conn: conn.rollback()
                flash(f"An unexpected error occurred: {str(e)}", "danger")
                current_app.logger.error(f"Unexpected error updating category {category_id}: {e}", exc_info=True)
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
        
        category_data_for_form = category.copy() # Start with original data
        category_data_for_form.update(request.form.to_dict()) # Override with form data
        category_data_for_form['image_filename'] = new_image_filename # Ensure new image is reflected
        return render_template('Doctor_Portal/Vaccines/category_form.html', 
                               form_title=f"Edit Category: {category.get('category_name')}", 
                               category=category_data_for_form, 
                               form_action=url_for('.edit_vaccine_category', category_id=category_id),
                               errors=errors)

    return render_template('Doctor_Portal/Vaccines/category_form.html', 
                           form_title=f"Edit Category: {category.get('category_name')}", 
                           category=category,
                           form_action=url_for('.edit_vaccine_category', category_id=category_id))


@vaccine_management_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_vaccine_category(category_id):
    if not is_doctor(): abort(403)
    conn = None; cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True) 
        cursor.execute("SELECT COUNT(*) as vaccine_count FROM vaccines WHERE category_id = %s AND is_active = TRUE", (category_id,))
        count_result = cursor.fetchone()
        active_vaccines_count = count_result['vaccine_count'] if count_result else 0
        
        if active_vaccines_count > 0:
            flash(f"Cannot deactivate category: It still contains {active_vaccines_count} active vaccine(s). Please deactivate or reassign them first.", "danger")
            return redirect(url_for('.list_vaccine_categories'))

        conn.start_transaction()
        cursor.execute("UPDATE vaccine_categories SET is_active = FALSE WHERE category_id = %s", (category_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Vaccine category deactivated successfully.", "success")
        else:
            flash("Vaccine category not found or already inactive.", "warning")
    except Exception as e:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        flash(f"Error deactivating category: {str(e)}", "danger")
        current_app.logger.error(f"Error deactivating category {category_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_vaccine_categories'))


# --- VACCINE (Items) ROUTES ---
@vaccine_management_bp.route('/', methods=['GET']) 
@vaccine_management_bp.route('/category/<int:category_id_filter>', methods=['GET']) 
@login_required
def list_vaccines(category_id_filter=None):
    if not is_doctor(): abort(403)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN_VACCINES).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION_VACCINES).upper()
    filters = {}
    if request.args.get('filter_category_id'): 
        filters['category_id'] = request.args.get('filter_category_id')
    if request.args.get('filter_vaccine_type'):
        filters['vaccine_type'] = request.args.get('filter_vaccine_type')
    
    current_category_info = None
    if category_id_filter:
        current_category_info = get_vaccine_category_by_id(category_id_filter)
        if not current_category_info:
            flash("Selected vaccine category not found.", "warning")
            return redirect(url_for('.list_vaccine_categories')) 

    if sort_by not in VALID_SORT_COLUMNS_VACCINES: sort_by = DEFAULT_SORT_COLUMN_VACCINES
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION_VACCINES

    result = get_paginated_vaccines(page=page, per_page=ITEMS_PER_PAGE, search_term=search,
                                  sort_by=sort_by, sort_dir=sort_dir, filters=filters,
                                  category_id_filter=category_id_filter) 

    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 and result['total'] > 0 else 0
    all_categories_for_filter = get_all_vaccine_categories_with_details(include_inactive=False)

    filter_options = {
        'categories': all_categories_for_filter, 
        'vaccine_types': get_enum_values('vaccines', 'vaccine_type')
    }
    
    request_args = request.args.to_dict()
    if category_id_filter: 
        request_args['category_id_filter'] = category_id_filter 
        if 'filter_category_id' in request_args:
            del request_args['filter_category_id']

    return render_template(
        'Doctor_Portal/Vaccines/vaccine_list.html',
        vaccines=result['items'],
        search_term=search,
        current_page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        filters=filters, 
        current_category_info=current_category_info, 
        category_id_filter=category_id_filter, 
        valid_sort_columns=VALID_SORT_COLUMNS_VACCINES,
        **filter_options,
        request_args=request_args 
    )

@vaccine_management_bp.route('/view/<int:vaccine_id>', methods=['GET'])
@login_required
def view_vaccine(vaccine_id):
    if not is_doctor(): abort(403)
    vaccine = get_vaccine_details_full(vaccine_id)
    if not vaccine:
        flash("Vaccine not found or is inactive.", "warning")
        return redirect(url_for('.list_vaccines'))
    return render_template('Doctor_Portal/Vaccines/vaccine_detail.html', vaccine=vaccine)

@vaccine_management_bp.route('/add', methods=['GET', 'POST'])
@vaccine_management_bp.route('/category/<int:category_id_context>/add', methods=['GET', 'POST'])
@login_required
def add_vaccine(category_id_context=None):
    if not is_doctor(): abort(403)
    all_categories_for_dropdown = get_all_vaccine_categories_with_details(include_inactive=False)
    dropdown_options = {
        'categories': all_categories_for_dropdown, 
        'vaccine_types_enum': get_enum_values('vaccines', 'vaccine_type')
    }
    
    prefilled_vaccine_data = {}
    if category_id_context:
        prefilled_vaccine_data['category_id'] = category_id_context

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
            vaccine_type = form.get('vaccine_type', '').strip() or None 
            administration_route = form.get('administration_route', '').strip() or None
            common_side_effects = form.get('common_side_effects', '').strip() or None
            contraindications_precautions = form.get('contraindications_precautions', '').strip() or None
            manufacturer = form.get('manufacturer', '').strip() or None
            notes = form.get('notes', '').strip() or None

            if not vaccine_name: errors.append("Vaccine Name is required.")
            if not category_id_str or not category_id_str.isdigit():
                errors.append("A valid Category is required.")
            else: category_id = int(category_id_str)
            if not diseases_prevented: errors.append("Diseases Prevented is required.")
            
            if errors: raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_insert_vaccine = """
                INSERT INTO vaccines (
                    category_id, vaccine_name, abbreviation, diseases_prevented,
                    recommended_for, benefits, timing_schedule, number_of_doses,
                    booster_information, vaccine_type, administration_route,
                    common_side_effects, contraindications_precautions, manufacturer, notes,
                    is_active, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
            """
            params_vaccine = (
                category_id, vaccine_name, abbreviation, diseases_prevented,
                recommended_for, benefits, timing_schedule, number_of_doses,
                booster_information, vaccine_type, administration_route,
                common_side_effects, contraindications_precautions, manufacturer, notes
            )
            cursor.execute(sql_insert_vaccine, params_vaccine)
            new_vaccine_id = cursor.lastrowid
            if not new_vaccine_id: conn.rollback(); raise mysql.connector.Error("Failed to insert vaccine.")
            conn.commit()
            flash(f"Vaccine '{vaccine_name}' added successfully.", "success")
            
            redirect_url = url_for('.view_vaccine', vaccine_id=new_vaccine_id)
            if category_id_context: 
                redirect_url = url_for('.list_vaccines', category_id_filter=category_id_context)
            return redirect(redirect_url)

        except ValueError: 
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            flash(f"Database error: {getattr(err, 'msg', str(err))}", "danger")
            current_app.logger.error(f"DB Error Adding Vaccine: {err}", exc_info=True)
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            flash(f"An unexpected error occurred: {str(e)}", "danger")
            current_app.logger.error(f"Unexpected Error Adding Vaccine: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        
        form_data_on_error = {**prefilled_vaccine_data, **request.form.to_dict()}
        return render_template('Doctor_Portal/Vaccines/vaccine_form.html',
                               form_action=url_for('.add_vaccine', category_id_context=category_id_context) if category_id_context else url_for('.add_vaccine'),
                               form_title="Add New Vaccine", vaccine=form_data_on_error, errors=errors, **dropdown_options)

    return render_template('Doctor_Portal/Vaccines/vaccine_form.html',
                           form_action=url_for('.add_vaccine', category_id_context=category_id_context) if category_id_context else url_for('.add_vaccine'),
                           form_title="Add New Vaccine", vaccine=prefilled_vaccine_data, **dropdown_options)


@vaccine_management_bp.route('/<int:vaccine_id>/edit', methods=['GET', 'POST'])
@vaccine_management_bp.route('/category/<int:category_id_context>/<int:vaccine_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_vaccine(vaccine_id, category_id_context=None):
    if not is_doctor(): abort(403)
    all_categories_for_dropdown = get_all_vaccine_categories_with_details(include_inactive=False)
    dropdown_options = {
        'categories': all_categories_for_dropdown,
        'vaccine_types_enum': get_enum_values('vaccines', 'vaccine_type')
    }
    
    vaccine_data_for_form = get_vaccine_basic_info(vaccine_id) 
    if not vaccine_data_for_form:
        flash("Vaccine not found or is inactive.", "warning")
        return redirect(url_for('.list_vaccines'))

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
            vaccine_type = form.get('vaccine_type', '').strip() or None
            administration_route = form.get('administration_route', '').strip() or None
            common_side_effects = form.get('common_side_effects', '').strip() or None
            contraindications_precautions = form.get('contraindications_precautions', '').strip() or None
            manufacturer = form.get('manufacturer', '').strip() or None
            notes = form.get('notes', '').strip() or None

            if not vaccine_name: errors.append("Vaccine Name is required.")
            if not category_id_str or not category_id_str.isdigit():
                errors.append("A valid Category is required.")
            else: category_id = int(category_id_str)
            if not diseases_prevented: errors.append("Diseases Prevented is required.")
            
            if errors: raise ValueError("Validation errors.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_update_vaccine = """
                UPDATE vaccines SET
                    category_id = %s, vaccine_name = %s, abbreviation = %s, diseases_prevented = %s,
                    recommended_for = %s, benefits = %s, timing_schedule = %s, number_of_doses = %s,
                    booster_information = %s, vaccine_type = %s, administration_route = %s,
                    common_side_effects = %s, contraindications_precautions = %s,
                    manufacturer = %s, notes = %s 
                WHERE vaccine_id = %s AND is_active = TRUE 
            """ 
            params_vaccine = (
                category_id, vaccine_name, abbreviation, diseases_prevented,
                recommended_for, benefits, timing_schedule, number_of_doses,
                booster_information, vaccine_type, administration_route,
                common_side_effects, contraindications_precautions, manufacturer, notes,
                vaccine_id
            )
            cursor.execute(sql_update_vaccine, params_vaccine)

            if cursor.rowcount == 0:
                conn.rollback() 
                flash("Vaccine not found, already inactive, or no changes were made.", "warning")
                redirect_url = url_for('.list_vaccines')
                if category_id_context:
                    redirect_url = url_for('.list_vaccines', category_id_filter=category_id_context)
                elif vaccine_data_for_form.get('category_id'):
                    redirect_url = url_for('.list_vaccines', category_id_filter=vaccine_data_for_form.get('category_id'))
                return redirect(redirect_url)

            conn.commit()
            flash(f"Vaccine '{vaccine_name}' updated successfully.", "success")
            return redirect(url_for('.view_vaccine', vaccine_id=vaccine_id))

        except ValueError: 
            for e_msg in errors: flash(e_msg, 'danger')
        except (mysql.connector.Error, ConnectionError) as err:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            flash(f"Database error: {getattr(err, 'msg', str(err))}", "danger")
            current_app.logger.error(f"DB Error Editing Vaccine {vaccine_id}: {err}", exc_info=True)
        except Exception as e:
            if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
            flash(f"An unexpected error occurred: {str(e)}", "danger")
            current_app.logger.error(f"Unexpected Error Editing Vaccine {vaccine_id}: {e}", exc_info=True)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        
        form_data_on_error = {**vaccine_data_for_form, **request.form.to_dict()}
        return render_template('Doctor_Portal/Vaccines/vaccine_form.html',
                               form_action=url_for('.edit_vaccine', vaccine_id=vaccine_id, category_id_context=category_id_context),
                               form_title=f"Edit Vaccine: {vaccine_data_for_form.get('vaccine_name', 'N/A')}", 
                               vaccine=form_data_on_error, errors=errors, **dropdown_options)

    return render_template('Doctor_Portal/Vaccines/vaccine_form.html',
                           form_action=url_for('.edit_vaccine', vaccine_id=vaccine_id, category_id_context=category_id_context),
                           form_title=f"Edit Vaccine: {vaccine_data_for_form.get('vaccine_name', 'N/A')}",
                           vaccine=vaccine_data_for_form, **dropdown_options)


@vaccine_management_bp.route('/<int:vaccine_id>/delete', methods=['POST'])
@vaccine_management_bp.route('/category/<int:category_id_context>/<int:vaccine_id>/delete', methods=['POST'])
@login_required
def delete_vaccine(vaccine_id, category_id_context=None): 
    if not is_doctor(): abort(403)
    conn = None; cursor = None
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
        cursor.execute("UPDATE vaccines SET is_active = FALSE WHERE vaccine_id = %s", (vaccine_id,))
        if cursor.rowcount == 0:
            flash("Vaccine not found or could not be deactivated.", "warning")
            conn.rollback()
        else:
            conn.commit()
            flash("Vaccine successfully deactivated.", "success")
    except Exception as err:
        if conn and conn.is_connected() and conn.in_transaction: conn.rollback()
        flash(f"Error deactivating vaccine: {str(err)}", "danger")
        current_app.logger.error(f"Error deactivating vaccine {vaccine_id}: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    if category_id_context:
        return redirect(url_for('.list_vaccines', category_id_filter=category_id_context))
    return redirect(url_for('.list_vaccines'))