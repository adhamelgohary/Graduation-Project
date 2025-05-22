# routes/Doctor_Portal/diet_plan_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime, time, timedelta
import math
import json
import decimal

# Assuming utils.py is in the same directory (adjust import if needed)
from .utils import (
    check_doctor_authorization,
    check_provider_authorization,
    check_doctor_or_dietitian_authorization,
    is_doctor_authorized_for_patient,
    get_provider_id,
    get_enum_values,
    get_all_simple,
    calculate_age,
    allowed_file,
    generate_secure_filename,
    can_modify_appointment,
    timedelta_to_time_filter
)

# --- Blueprint Definition ---
diet_plans_bp = Blueprint(
    'diet_plans',
    __name__,
    url_prefix='/doctor/diet-plans',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 10
VALID_SORT_COLUMNS = {
    'name': 'dp.plan_name', 'type': 'dp.plan_type', 'calories': 'dp.calories',
    'protein': 'dp.protein_grams', 'carbs': 'dp.carbs_grams', 'fat': 'dp.fat_grams', # Added more sortable nutrients
    'id': 'dp.plan_id', 'updated': 'dp.updated_at', 'creator': 'u.last_name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'

# --- Helper Functions ---
def validate_numeric(value, field_name, errors, allow_negative=False, is_float=False, required=False):
    if value is None and not required: return None
    if value is None and required:
        errors.append(f"{field_name} is required.")
        return None
    
    str_value = str(value).strip()
    if not str_value:
        if required: errors.append(f"{field_name} is required."); return None
        return None
    try:
        num = float(str_value) if is_float else int(str_value)
        if not allow_negative and num < 0:
            errors.append(f"{field_name} cannot be negative.")
            return None
        return num
    except (ValueError, TypeError):
        errors.append(f"{field_name} must be a valid number.")
        return None

def parse_time_string(time_str):
    if not time_str: return None
    try: return datetime.strptime(time_str, '%H:%M').time()
    except (ValueError, TypeError): return None

# *** UPDATED HELPER for Nutrient Calculation ***
def calculate_nutrient_totals(items_list):
    """
    Calculates the sum of specified nutrients from a list of dictionaries (food items).
    Returns a dictionary with total_calories, total_protein, total_carbs, etc.
    Values will be None if no valid data for that nutrient was found.
    """
    totals = {
        'calories': 0, 'protein_grams': 0.0, 'carbs_grams': 0.0, 'fat_grams': 0.0,
        'fiber_grams': 0.0, 'sodium_mg': 0
    }
    # Flags to track if any valid data was found for each nutrient
    found_data = {key: False for key in totals}
    nutrient_keys = list(totals.keys()) # e.g., 'calories', 'protein_grams'

    for item in items_list:
        for key in nutrient_keys:
            item_val = item.get(key) # Get value from item dict (e.g., item['calories'])
            if item_val is not None:
                try:
                    # Try to convert to appropriate type (float for grams, int for calories/sodium)
                    if key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams']:
                        num_val = float(item_val)
                    else: # calories, sodium_mg
                        num_val = int(item_val)
                    
                    totals[key] += num_val
                    found_data[key] = True
                except (ValueError, TypeError):
                    # Silently ignore if conversion fails for an item's nutrient
                    current_app.logger.debug(f"Could not convert item value '{item_val}' for nutrient '{key}'.")
                    pass
    
    # Set totals to None if no valid data was found for that nutrient
    for key in nutrient_keys:
        if not found_data[key]:
            totals[key] = None
        elif key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams']:
            totals[key] = round(totals[key], 2) # Round decimals to 2 places

    return totals


# --- Specific Fetchers ---
def get_all_conditions(): return get_all_simple('conditions', 'condition_name', 'condition_name', order_by='condition_name', where_clause='is_active = TRUE')
def get_all_active_patients(): return get_all_simple('users', 'user_id', "CONCAT(first_name, ' ', last_name)", order_by="last_name, first_name", where_clause="user_type = 'patient' AND account_status = 'active'")
def get_all_selectable_diet_plans(user_id):
     conn = None; cursor = None; items = []
     try:
         conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
         query = """
             SELECT plan_id, plan_name FROM diet_plans
             WHERE is_public = TRUE OR creator_id = %s
             ORDER BY plan_name ASC
         """
         cursor.execute(query, (user_id,))
         items = cursor.fetchall()
     except Exception as e: current_app.logger.error(f"Error fetching selectable diet plans for user {user_id}: {e}")
     finally:
        if cursor: cursor.close();
        if conn and conn.is_connected(): conn.close()
     return items

# --- Data Fetching Functions ---
def get_paginated_diet_plans(page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
    # ... no changes ...
    conn = None; cursor = None; result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        sql_select = """
            SELECT SQL_CALC_FOUND_ROWS dp.*,
                   u.user_id as creator_user_id, u.first_name as creator_first_name, u.last_name as creator_last_name
        """
        sql_from = " FROM diet_plans dp LEFT JOIN users u ON dp.creator_id = u.user_id "
        sql_where = " WHERE 1=1 "
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (dp.plan_name LIKE %s OR dp.description LIKE %s OR dp.target_conditions LIKE %s)"
            params.extend([search_like, search_like, search_like])
        if valid_filters.get('plan_type'):
            sql_where += " AND dp.plan_type = %s"; params.append(valid_filters['plan_type'])
        if valid_filters.get('is_public') is not None:
            sql_where += " AND dp.is_public = %s"
            params.append(valid_filters['is_public'])

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        cursor.execute("SELECT FOUND_ROWS() as total")
        total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching paginated diet plans: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_diet_plan_details(plan_id):
    # ... no changes ...
    conn = None; cursor = None; details = {'plan': None, 'meals': []}
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        # Fetch plan details
        query_plan = """SELECT dp.*, u.first_name as creator_first_name, u.last_name as creator_last_name
                        FROM diet_plans dp LEFT JOIN users u ON dp.creator_id = u.user_id WHERE dp.plan_id = %s"""
        cursor.execute(query_plan, (plan_id,))
        details['plan'] = cursor.fetchone()
        if not details['plan']: return None

        # Fetch meals (MySQL TIME type might be returned as timedelta by connector)
        query_meals = """SELECT * FROM diet_plan_meals WHERE plan_id = %s
                         ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack', 'other'), time_of_day, meal_id"""
        cursor.execute(query_meals, (plan_id,))
        meals = cursor.fetchall()

        if meals:
            meal_ids = [meal['meal_id'] for meal in meals]
            placeholders = ', '.join(['%s'] * len(meal_ids))
            query_items = f"SELECT * FROM diet_plan_food_items WHERE meal_id IN ({placeholders}) ORDER BY meal_id, item_id"
            cursor.execute(query_items, tuple(meal_ids))
            all_items = cursor.fetchall()
            expected_meal_nutrient_keys = ['calories', 'protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams', 'sodium_mg']

            # Map items to their meals
            items_by_meal = {}
            for item in all_items:
                 # Convert Decimal types to float for easier handling in templates if needed, or keep as Decimal
                for key, value in item.items():
                     if isinstance(value, decimal.Decimal):
                         item[key] = float(value) # Example conversion

                meal_id = item['meal_id']
                if meal_id not in items_by_meal: items_by_meal[meal_id] = []
                items_by_meal[meal_id].append(item)

            # Attach items to each meal dictionary
            for meal in meals:
                meal['food_items'] = items_by_meal.get(meal['meal_id'], [])

            details['meals'] = meals

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching diet plan details for ID {plan_id}: {err}"); return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return details

# --- Routes ---
@diet_plans_bp.route('/', methods=['GET'])
@login_required
def list_diet_plans():
    # ... no changes ...
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view diet plans.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    filter_type = request.args.get('filter_type', '')
    filter_public = request.args.get('filter_public', '') # 'true', 'false', ''

    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    filters = {}
    if filter_type: filters['plan_type'] = filter_type
    if filter_public == 'true': filters['is_public'] = True
    elif filter_public == 'false': filters['is_public'] = False

    result = get_paginated_diet_plans(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    plans = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    plan_types = get_enum_values('diet_plans', 'plan_type')

    can_manage_plans = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_list.html',
        plans=plans, search_term=search_term, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters, plan_types=plan_types,
        valid_sort_columns=VALID_SORT_COLUMNS,
        can_manage_plans=can_manage_plans,
        request_args=request.args
    )

@diet_plans_bp.route('/<int:plan_id>', methods=['GET'])
@login_required
def view_diet_plan(plan_id):
    # ... no changes ...
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view diet plan details.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    details = get_diet_plan_details(plan_id)
    if not details:
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    target_conditions_list = []
    if details['plan'].get('target_conditions'):
        target_conditions_list = [c.strip() for c in details['plan']['target_conditions'].split(',') if c.strip()]
    details['plan']['target_conditions_list'] = target_conditions_list

    plan_check_info = details['plan']
    is_dietitian_creator = (check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
                           plan_check_info.get('creator_id') == current_user.id)
    can_edit_this_plan = (check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
                          plan_check_info.get('is_public')) or is_dietitian_creator

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_detail.html',
        details=details,
        can_edit_this_plan=can_edit_this_plan
    )


@diet_plans_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_diet_plan():
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to add diet plans.", "danger")
        return redirect(url_for('.list_diet_plans') if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False) else url_for('doctor_main.dashboard'))

    plan_types = get_enum_values('diet_plans', 'plan_type')
    conditions = get_all_conditions()
    meal_types = get_enum_values('diet_plan_meals', 'meal_type')

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        try:
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            is_public = request.form.get('is_public') == 'on'
            selected_conditions_list = request.form.getlist('target_conditions')
            target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None

            if not plan_name: errors.append("Plan Name is required.")
            if not plan_type or plan_type not in plan_types: errors.append("Valid Plan Type is required.")
            if errors: raise ValueError("Plan validation failed (details)")

            conn = get_db_connection(); cursor = conn.cursor()
            # Insert diet_plans record with all nutrients initially NULL
            # These will be calculated if meals/items are added during the subsequent edit.
            sql_insert_plan = """INSERT INTO diet_plans (plan_name, plan_type, description,
                                 calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg,
                                 is_public, creator_id, target_conditions,
                                 created_at, updated_at)
                                 VALUES (%s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL, %s, %s, %s, NOW(), NOW())"""
            params_plan = (plan_name, plan_type, description,
                           is_public, current_user.id, target_conditions_str)
            cursor.execute(sql_insert_plan, params_plan)
            new_plan_id = cursor.lastrowid
            conn.commit()
            flash(f"Diet plan '{plan_name}' details saved. You can now add meals and food items to calculate nutritional totals.", "success")
            return redirect(url_for('.edit_diet_plan', plan_id=new_plan_id))

        except ValueError:
            for err in errors: flash(err, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback(); current_app.logger.error(f"DB Error Adding Diet Plan: {err}")
            flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
            if conn: conn.rollback(); current_app.logger.error(f"Unexpected Error Adding Diet Plan: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        form_data = request.form.to_dict()
        form_data['target_conditions_list'] = selected_conditions_list
        form_data['is_public'] = request.form.get('is_public') == 'on'
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
            plan=form_data, meals=[], plan_types=plan_types,
            meal_types=meal_types, conditions=conditions, errors=errors
        )

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_form.html',
        form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
        plan=None, meals=[],
        plan_types=plan_types, meal_types=meal_types, conditions=conditions
    )


@diet_plans_bp.route('/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_diet_plan(plan_id):
    # --- Authorization Check (remains the same) ---
    can_edit_this_plan = False; plan_check_info = None; conn_check = None; cursor_check = None
    try:
        conn_check = get_db_connection(); cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
        plan_check_info = cursor_check.fetchone()
        if plan_check_info:
            is_dietitian = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)
            is_creator = plan_check_info.get('creator_id') == current_user.id
            is_public = plan_check_info.get('is_public')
            if is_dietitian and (is_public or is_creator): can_edit_this_plan = True
        else:
             flash("Diet plan not found.", "warning"); return redirect(url_for('.list_diet_plans'))
    except (ConnectionError, mysql.connector.Error) as db_err:
         current_app.logger.error(f"DB Error checking edit permission for plan {plan_id}: {db_err}")
         flash("Database error checking permissions.", "danger"); return redirect(url_for('.list_diet_plans'))
    finally:
         if cursor_check: cursor_check.close()
         if conn_check and conn_check.is_connected(): conn_check.close()

    if not can_edit_this_plan:
         flash("Access denied. You do not have permission to edit this diet plan.", "danger")
         return redirect(url_for('.view_diet_plan', plan_id=plan_id) if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False) else url_for('doctor_main.dashboard'))

    plan_types = get_enum_values('diet_plans', 'plan_type')
    meal_types = get_enum_values('diet_plan_meals', 'meal_type')
    conditions = get_all_conditions()

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        
        # Initialize overall plan nutrient totals
        overall_plan_nutrients = {
            'calories': 0, 'protein_grams': 0.0, 'carbs_grams': 0.0, 'fat_grams': 0.0,
            'fiber_grams': 0.0, 'sodium_mg': 0
        }
        # Flags to track if any valid data was found for each nutrient at the plan level
        plan_has_nutrient_data = {key: False for key in overall_plan_nutrients}


        try:
            conn = get_db_connection(); cursor = conn.cursor()
            conn.start_transaction()

            # --- 1. Update Plan Main Details (name, type, description, etc.) ---
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            is_public = request.form.get('is_public') == 'on'
            selected_conditions_list = request.form.getlist('target_conditions')
            target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None

            if not plan_name: errors.append("Plan Name is required.")
            if not plan_type or plan_type not in plan_types: errors.append("Valid Plan Type is required.")
            if errors: raise ValueError("Plan validation failed (details)")

            # Update plan details (nutrients will be updated after meal processing)
            sql_update_plan_details_only = """UPDATE diet_plans SET plan_name=%s, plan_type=%s, description=%s,
                                       is_public=%s, target_conditions=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP
                                       WHERE plan_id=%s"""
            params_plan_details_only = (plan_name, plan_type, description,
                                   is_public, target_conditions_str, current_user.id, plan_id)
            cursor.execute(sql_update_plan_details_only, params_plan_details_only)


            # --- 2. Process Deletions ---
            deleted_meal_ids = request.form.getlist('deleted_meal_ids')
            deleted_item_ids = request.form.getlist('deleted_item_ids')
            if deleted_meal_ids:
                # ... (deletion logic remains the same) ...
                valid_deleted_meal_ids = [int(id) for id in deleted_meal_ids if id.isdigit()]
                if valid_deleted_meal_ids:
                    placeholders = ','.join(['%s'] * len(valid_deleted_meal_ids))
                    cursor.execute(f"DELETE FROM diet_plan_food_items WHERE meal_id IN ({placeholders})", tuple(valid_deleted_meal_ids))
                    sql_delete_meals = f"DELETE FROM diet_plan_meals WHERE meal_id IN ({placeholders}) AND plan_id = %s"
                    cursor.execute(sql_delete_meals, (*valid_deleted_meal_ids, plan_id))
            if deleted_item_ids:
                # ... (deletion logic remains the same) ...
                valid_deleted_item_ids = [int(id) for id in deleted_item_ids if id.isdigit()]
                if valid_deleted_item_ids:
                    placeholders = ','.join(['%s'] * len(valid_deleted_item_ids))
                    sql_delete_items = f"DELETE FROM diet_plan_food_items WHERE item_id IN ({placeholders})"
                    cursor.execute(sql_delete_items, tuple(valid_deleted_item_ids))


            # --- 3. Process Updates (Existing Meals/Items) ---
            existing_meal_ids = request.form.getlist('meal_id')
            for meal_id_str in existing_meal_ids:
                if not meal_id_str.isdigit() or meal_id_str in deleted_meal_ids: continue
                meal_id = int(meal_id_str)
                
                meal_food_items_data = [] # To calculate this meal's nutrients

                # Process existing items for this meal
                existing_item_ids_for_meal = request.form.getlist(f'item_id[{meal_id}]')
                for item_id_str in existing_item_ids_for_meal:
                    # ... (validation for item_id_str) ...
                    if not item_id_str.isdigit() or item_id_str in deleted_item_ids: continue
                    item_id = int(item_id_str)

                    item_data = {} # To collect individual item nutrients
                    item_data['food_name'] = request.form.get(f'item_food_name[{item_id}]', '').strip()
                    item_data['serving_size'] = request.form.get(f'item_serving_size[{item_id}]', '').strip()
                    item_data['notes'] = request.form.get(f'item_notes[{item_id}]', '').strip() or None
                    item_data['alternatives'] = request.form.get(f'item_alternatives[{item_id}]', '').strip() or None
                    
                    # Validate and collect nutrients for this item
                    item_data['calories'] = validate_numeric(request.form.get(f'item_calories[{item_id}]'), f"Cals for {item_data['food_name']}", errors)
                    item_data['protein_grams'] = validate_numeric(request.form.get(f'item_protein[{item_id}]'), f"Prot for {item_data['food_name']}", errors, is_float=True)
                    item_data['carbs_grams'] = validate_numeric(request.form.get(f'item_carbs[{item_id}]'), f"Carb for {item_data['food_name']}", errors, is_float=True)
                    item_data['fat_grams'] = validate_numeric(request.form.get(f'item_fat[{item_id}]'), f"Fat for {item_data['food_name']}", errors, is_float=True)
                    # Add fiber_grams, sodium_mg if you have fields for them at item level
                    # item_data['fiber_grams'] = validate_numeric(...)
                    # item_data['sodium_mg'] = validate_numeric(...)

                    if not item_data['food_name'] or not item_data['serving_size']:
                        errors.append(f"Food Name and Serving Size are required for item ID {item_id}.")
                        continue # Skip update if basic validation fails
                    if errors: continue

                    sql_update_item = """UPDATE diet_plan_food_items SET food_name=%s, serving_size=%s, notes=%s, alternatives=%s,
                                         calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s
                                         WHERE item_id=%s AND meal_id=%s"""
                    cursor.execute(sql_update_item, (item_data['food_name'], item_data['serving_size'], item_data['notes'], item_data['alternatives'],
                                                    item_data['calories'], item_data['protein_grams'], item_data['carbs_grams'], item_data['fat_grams'],
                                                    item_id, meal_id))
                    meal_food_items_data.append(item_data) # Add for meal total calculation
                
                # Process NEW items for THIS EXISTING meal
                meal_ref_existing = str(meal_id)
                new_item_names_ex = request.form.getlist(f'new_item_food_name[{meal_ref_existing}]')
                for k, item_name_form in enumerate(new_item_names_ex):
                    # ... (similar logic as for new items in new meals) ...
                    item_name_form = item_name_form.strip()
                    if not item_name_form: continue
                    item_data = {}
                    item_data['food_name'] = item_name_form
                    item_data['serving_size'] = (request.form.getlist(f'new_item_serving_size[{meal_ref_existing}]')[k] if k < len(request.form.getlist(f'new_item_serving_size[{meal_ref_existing}]')) else '').strip()
                    # ... (validate and collect nutrients for this new item) ...
                    item_data['calories'] = validate_numeric(request.form.getlist(f'new_item_calories[{meal_ref_existing}]')[k] if k < len(request.form.getlist(f'new_item_calories[{meal_ref_existing}]')) else None, f"Cals for new item '{item_data['food_name']}'", errors)
                    item_data['protein_grams'] = validate_numeric(request.form.getlist(f'new_item_protein[{meal_ref_existing}]')[k] if k < len(request.form.getlist(f'new_item_protein[{meal_ref_existing}]')) else None, f"Prot for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['carbs_grams'] = validate_numeric(request.form.getlist(f'new_item_carbs[{meal_ref_existing}]')[k] if k < len(request.form.getlist(f'new_item_carbs[{meal_ref_existing}]')) else None, f"Carbs for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['fat_grams'] = validate_numeric(request.form.getlist(f'new_item_fat[{meal_ref_existing}]')[k] if k < len(request.form.getlist(f'new_item_fat[{meal_ref_existing}]')) else None, f"Fat for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['notes'] = (request.form.getlist(f'new_item_notes[{meal_ref_existing}]')[k].strip() if k < len(request.form.getlist(f'new_item_notes[{meal_ref_existing}]')) else None) or None
                    item_data['alternatives'] = (request.form.getlist(f'new_item_alternatives[{meal_ref_existing}]')[k].strip() if k < len(request.form.getlist(f'new_item_alternatives[{meal_ref_existing}]')) else None) or None

                    if not item_data['serving_size']: errors.append(f"Serving Size for new item '{item_data['food_name']}'."); continue
                    if errors: continue

                    sql_insert_item_ex = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives,
                                            calories, protein_grams, carbs_grams, fat_grams)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_insert_item_ex, (meal_id, item_data['food_name'], item_data['serving_size'], item_data['notes'], item_data['alternatives'],
                                                        item_data['calories'], item_data['protein_grams'], item_data['carbs_grams'], item_data['fat_grams']))
                    meal_food_items_data.append(item_data)

                # Calculate and Update This Existing Meal's Nutrients
                calculated_meal_nutrients = calculate_nutrient_totals(meal_food_items_data)
                
                # Update meal's own details (name, type, time) and calculated nutrients
                meal_name_form = request.form.get(f'meal_name[{meal_id}]', '').strip()
                meal_type_form = request.form.get(f'meal_type[{meal_id}]')
                time_of_day_str_form = request.form.get(f'meal_time[{meal_id}]')
                meal_time_obj_form = parse_time_string(time_of_day_str_form)
                meal_desc_form = request.form.get(f'meal_desc[{meal_id}]', '').strip() or None
                
                # ... (validation for meal_name_form, meal_type_form, etc.)
                if not meal_name_form: errors.append(f"Meal Name required for meal ID {meal_id}.")

                sql_update_meal_nutrients = """UPDATE diet_plan_meals SET 
                                             meal_name=%s, meal_type=%s, time_of_day=%s, description=%s,
                                             calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s,
                                             fiber_grams=%s, sodium_mg=%s
                                             WHERE meal_id=%s AND plan_id=%s"""
                cursor.execute(sql_update_meal_nutrients, (
                    meal_name_form, meal_type_form, meal_time_obj_form, meal_desc_form,
                    calculated_meal_nutrients['calories'], calculated_meal_nutrients['protein_grams'],
                    calculated_meal_nutrients['carbs_grams'], calculated_meal_nutrients['fat_grams'],
                    calculated_meal_nutrients['fiber_grams'], calculated_meal_nutrients['sodium_mg'],
                    meal_id, plan_id
                ))
                
                # Add this meal's calculated nutrients to the overall plan totals
                for key, value in calculated_meal_nutrients.items():
                    if value is not None:
                        if isinstance(overall_plan_nutrients[key], (int, float)): # Ensure it's a number
                            overall_plan_nutrients[key] += value
                            plan_has_nutrient_data[key] = True
                        elif overall_plan_nutrients[key] is None: # If None, start with this value
                            overall_plan_nutrients[key] = value
                            plan_has_nutrient_data[key] = True


            # --- 4. Process Inserts (New Meals & Their Items) ---
            new_meal_names = request.form.getlist('new_meal_name')
            for i, new_meal_name_form in enumerate(new_meal_names):
                new_meal_name_form = new_meal_name_form.strip()
                if not new_meal_name_form: continue

                new_meal_food_items_data = [] # For this new meal's nutrients

                new_type_form = request.form.getlist('new_meal_type')[i] if i < len(request.form.getlist('new_meal_type')) else None
                new_time_str_form = request.form.getlist('new_meal_time')[i] if i < len(request.form.getlist('new_meal_time')) else None
                new_time_obj_form = parse_time_string(new_time_str_form)
                new_desc_form = request.form.getlist('new_meal_desc')[i].strip() if i < len(request.form.getlist('new_meal_desc')) else None
                
                # ... (validation for new_meal_name_form, new_type_form) ...
                if not new_type_form or new_type_form not in meal_types: errors.append(f"Meal Type for '{new_meal_name_form}'."); continue
                
                # Insert meal with NULL nutrients initially
                sql_insert_meal = """INSERT INTO diet_plan_meals (plan_id, meal_name, meal_type, time_of_day, description, 
                                     calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg) 
                                     VALUES (%s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL)"""
                cursor.execute(sql_insert_meal, (plan_id, new_meal_name_form, new_type_form, new_time_obj_form, new_desc_form))
                new_meal_id = cursor.lastrowid

                meal_ref_new = f'new_{i}'
                new_item_names_for_new_meal = request.form.getlist(f'new_item_food_name[{meal_ref_new}]')
                for j, item_name_form in enumerate(new_item_names_for_new_meal):
                    # ... (similar logic as for new items in existing meals, collect item_data) ...
                    item_name_form = item_name_form.strip()
                    if not item_name_form: continue
                    item_data = {}
                    item_data['food_name'] = item_name_form
                    item_data['serving_size'] = (request.form.getlist(f'new_item_serving_size[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_serving_size[{meal_ref_new}]')) else '').strip()
                    # ... (validate and collect nutrients for this new item) ...
                    item_data['calories'] = validate_numeric(request.form.getlist(f'new_item_calories[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_calories[{meal_ref_new}]')) else None, f"Cals for new item '{item_data['food_name']}'", errors)
                    item_data['protein_grams'] = validate_numeric(request.form.getlist(f'new_item_protein[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_protein[{meal_ref_new}]')) else None, f"Prot for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['carbs_grams'] = validate_numeric(request.form.getlist(f'new_item_carbs[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_carbs[{meal_ref_new}]')) else None, f"Carbs for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['fat_grams'] = validate_numeric(request.form.getlist(f'new_item_fat[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_fat[{meal_ref_new}]')) else None, f"Fat for new item '{item_data['food_name']}'", errors, is_float=True)
                    item_data['notes'] = (request.form.getlist(f'new_item_notes[{meal_ref_new}]')[j].strip() if j < len(request.form.getlist(f'new_item_notes[{meal_ref_new}]')) else None) or None
                    item_data['alternatives'] = (request.form.getlist(f'new_item_alternatives[{meal_ref_new}]')[j].strip() if j < len(request.form.getlist(f'new_item_alternatives[{meal_ref_new}]')) else None) or None

                    if not item_data['serving_size']: errors.append(f"Serving Size for new item '{item_data['food_name']}'."); continue
                    if errors: continue

                    sql_insert_item = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives,
                                           calories, protein_grams, carbs_grams, fat_grams)
                                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_insert_item, (new_meal_id, item_data['food_name'], item_data['serving_size'], item_data['notes'], item_data['alternatives'],
                                                    item_data['calories'], item_data['protein_grams'], item_data['carbs_grams'], item_data['fat_grams']))
                    new_meal_food_items_data.append(item_data)
                
                # Calculate and Update This New Meal's Nutrients
                calculated_new_meal_nutrients = calculate_nutrient_totals(new_meal_food_items_data)
                sql_update_new_meal_nutrients = """UPDATE diet_plan_meals SET 
                                                calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s,
                                                fiber_grams=%s, sodium_mg=%s
                                                WHERE meal_id=%s"""
                cursor.execute(sql_update_new_meal_nutrients, (
                    calculated_new_meal_nutrients['calories'], calculated_new_meal_nutrients['protein_grams'],
                    calculated_new_meal_nutrients['carbs_grams'], calculated_new_meal_nutrients['fat_grams'],
                    calculated_new_meal_nutrients['fiber_grams'], calculated_new_meal_nutrients['sodium_mg'],
                    new_meal_id
                ))
                
                # Add this new meal's calculated nutrients to the overall plan totals
                for key, value in calculated_new_meal_nutrients.items():
                    if value is not None:
                        if isinstance(overall_plan_nutrients[key], (int, float)):
                           overall_plan_nutrients[key] += value
                           plan_has_nutrient_data[key] = True
                        elif overall_plan_nutrients[key] is None:
                           overall_plan_nutrients[key] = value
                           plan_has_nutrient_data[key] = True


            # --- 5. Finalize and Update Overall Plan Nutrients ---
            final_plan_nutrients_to_save = {}
            for key in overall_plan_nutrients.keys():
                final_plan_nutrients_to_save[key] = overall_plan_nutrients[key] if plan_has_nutrient_data[key] else None
                if key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams'] and final_plan_nutrients_to_save[key] is not None:
                     final_plan_nutrients_to_save[key] = round(final_plan_nutrients_to_save[key], 2)


            sql_update_plan_all_nutrients = """UPDATE diet_plans SET 
                                             calories = %s, protein_grams = %s, carbs_grams = %s, 
                                             fat_grams = %s, fiber_grams = %s, sodium_mg = %s,
                                             updated_at = CURRENT_TIMESTAMP 
                                             WHERE plan_id = %s"""
            cursor.execute(sql_update_plan_all_nutrients, (
                final_plan_nutrients_to_save['calories'], final_plan_nutrients_to_save['protein_grams'],
                final_plan_nutrients_to_save['carbs_grams'], final_plan_nutrients_to_save['fat_grams'],
                final_plan_nutrients_to_save['fiber_grams'], final_plan_nutrients_to_save['sodium_mg'],
                plan_id
            ))

            if errors:
                 unique_errors = list(dict.fromkeys(errors))
                 raise ValueError("Validation errors occurred: " + "; ".join(unique_errors))

            conn.commit()
            flash(f"Diet plan '{plan_name}' updated successfully with calculated nutritional totals.", "success")
            return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        except ValueError as ve:
            if conn and conn.is_connected(): conn.rollback()
            unique_errors = list(dict.fromkeys(errors))
            for err in unique_errors: flash(err, 'danger')
            if not unique_errors and str(ve): flash(str(ve), 'danger')
            current_app.logger.warning(f"Validation Error Editing Diet Plan {plan_id}: {ve}")
        except mysql.connector.Error as err:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"DB Error Editing Diet Plan {plan_id}: {err}")
            flash(f"Database error updating plan: {err.msg}", "danger")
        except Exception as e:
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Unexpected Error Editing Diet Plan {plan_id}: {e}", exc_info=True)
            flash("An unexpected error occurred during update.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        current_details = get_diet_plan_details(plan_id) or {'plan': {}, 'meals': []}
        submitted_plan_data = {
            'plan_name': request.form.get('plan_name', current_details['plan'].get('plan_name', '')),
            'plan_type': request.form.get('plan_type', current_details['plan'].get('plan_type', '')),
            'description': request.form.get('description', current_details['plan'].get('description', '')),
            # Nutrient fields are now calculated, so not directly repopulated from form for the plan itself
            'is_public': request.form.get('is_public') == 'on',
            'target_conditions_list': request.form.getlist('target_conditions'),
            'plan_id': plan_id
        }
        # For repopulation, pass the calculated/DB values for nutrients if available
        for key in ['calories', 'protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams', 'sodium_mg']:
             submitted_plan_data[key] = current_details['plan'].get(key)

        existing_meals = current_details.get('meals', [])
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.edit_diet_plan', plan_id=plan_id),
            form_title=f"Edit Diet Plan: {submitted_plan_data.get('plan_name', '')}",
            plan=submitted_plan_data, 
            meals=existing_meals, 
            plan_types=plan_types,
            meal_types=meal_types, conditions=conditions,
            errors=list(dict.fromkeys(errors))
        )

    details = get_diet_plan_details(plan_id)
    if not details:
        flash("Diet plan not found.", "warning"); return redirect(url_for('.list_diet_plans'))
    selected_conditions = []
    if details['plan'].get('target_conditions'):
        selected_conditions = [c.strip() for c in details['plan']['target_conditions'].split(',') if c.strip()]
    details['plan']['target_conditions_list'] = selected_conditions
    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_form.html',
        form_action=url_for('.edit_diet_plan', plan_id=plan_id),
        form_title=f"Edit Diet Plan: {details['plan']['plan_name']}",
        plan=details['plan'], meals=details.get('meals', []),
        plan_types=plan_types, meal_types=meal_types, conditions=conditions
    )


# ... (delete_diet_plan and subsequent routes remain the same) ...
@diet_plans_bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_diet_plan(plan_id):
    """Deletes a diet plan - Restricted based on ownership/public and dietitian role."""
    # --- Authorization Check (same as before) ---
    can_delete_this_plan = False; plan_check_info = None; conn_check = None; cursor_check = None
    try:
        conn_check = get_db_connection(); cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT plan_name, creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
        plan_check_info = cursor_check.fetchone()
        if plan_check_info:
            is_dietitian = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)
            is_creator = plan_check_info.get('creator_id') == current_user.id
            is_public = plan_check_info.get('is_public')
            if is_dietitian and (is_public or is_creator): can_delete_this_plan = True
        else: flash("Diet plan not found.", "warning"); return redirect(url_for('.list_diet_plans'))
    except (ConnectionError, mysql.connector.Error) as db_err:
        current_app.logger.error(f"DB Error checking delete permission for plan {plan_id}: {db_err}")
        flash("Database error checking permissions.", "danger"); return redirect(url_for('.list_diet_plans'))
    finally:
        if cursor_check: cursor_check.close()
        if conn_check and conn_check.is_connected(): conn_check.close()

    if not can_delete_this_plan:
        flash("Access denied. You do not have permission to delete this diet plan.", "danger")
        return redirect(url_for('.view_diet_plan', plan_id=plan_id))
    # --- End Authorization Check ---

    conn = None; cursor = None; plan_name = plan_check_info['plan_name']
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        conn.start_transaction()

        # Check for active assignments FIRST
        cursor.execute("SELECT 1 FROM user_diet_plans WHERE plan_id = %s AND active = TRUE LIMIT 1", (plan_id,))
        if cursor.fetchone():
             conn.rollback()
             flash(f"Cannot delete plan '{plan_name}'. It is actively assigned to one or more patients.", "warning")
             return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        # Manually delete related items and meals (safer if CASCADE DELETE is not guaranteed)
        cursor.execute("DELETE FROM diet_plan_food_items WHERE meal_id IN (SELECT meal_id FROM diet_plan_meals WHERE plan_id = %s)", (plan_id,))
        cursor.execute("DELETE FROM diet_plan_meals WHERE plan_id = %s", (plan_id,))
        # Now delete the plan itself
        cursor.execute("DELETE FROM diet_plans WHERE plan_id = %s", (plan_id,))

        # Check if the plan was actually deleted (it might have related inactive assignments preventing deletion due to FK constraints)
        if cursor.rowcount == 0:
             conn.rollback() # Rollback the transaction
             flash(f"Could not delete plan '{plan_name}'. It might have historical assignments or related data preventing deletion.", "danger")
             current_app.logger.warning(f"Deletion attempt failed for plan_id {plan_id} (rowcount 0), possibly due to FK constraints.")
        else:
            conn.commit()
            flash(f"Diet plan '{plan_name}' deleted successfully.", "success")

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback();
        current_app.logger.error(f"DB Error Deleting Diet Plan {plan_id}: {err}")
        # Check for foreign key constraint error (often indicates related records exist)
        if err.errno == 1451: # MySQL error code for foreign key constraint failure
             flash(f"Cannot delete plan '{plan_name}'. It is referenced by other records (e.g., inactive assignments).", "danger")
        else:
             flash(f"Database error deleting plan: {err.msg}", "danger")
    except ConnectionError as ce:
        current_app.logger.error(f"DB Connection Error Deleting Diet Plan {plan_id}: {ce}"); flash("Database connection error.", "danger")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback();
        current_app.logger.error(f"Unexpected Error Deleting Diet Plan {plan_id}: {e}", exc_info=True)
        flash(f"An unexpected error occurred while deleting '{plan_name}'.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.list_diet_plans'))


# --- Assignment & Progress Routes (Largely unchanged, but reviewed authorization) ---

@diet_plans_bp.route('/assign', methods=['GET', 'POST'])
@login_required
def assign_diet_plan():
    """Assigns a diet plan to a patient - Restricted to Dietitians."""
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to assign diet plans.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
             return redirect(url_for('.list_assignments'))
        else: return redirect(url_for('doctor_main.dashboard'))

    patients = get_all_active_patients()
    diet_plans = get_all_selectable_diet_plans(current_user.id) # Use current user's ID

    form_data_repop = {} # For repopulating form on error

    if request.method == 'POST':
        form_data_repop = request.form.to_dict() # Capture submitted data
        patient_user_id = request.form.get('patient_user_id', type=int)
        plan_id = request.form.get('plan_id', type=int)
        start_date_str = request.form.get('start_date'); end_date_str = request.form.get('end_date')
        notes = request.form.get('notes', '').strip() or None; errors = []

        # --- Validation ---
        if not patient_user_id: errors.append("Patient selection is required.")
        if not plan_id: errors.append("Diet Plan selection is required.")
        start_date = None; end_date = None
        try:
            if start_date_str: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else: errors.append("Start Date is required.")
        except ValueError: errors.append("Invalid Start Date format (YYYY-MM-DD).")
        try:
            if end_date_str: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError: errors.append("Invalid End Date format (YYYY-MM-DD).")
        if start_date and end_date and end_date < start_date:
            errors.append("End Date cannot be before Start Date.")
        # --- End Validation ---

        if errors:
            for err in errors: flash(err, 'danger')
            return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=form_data_repop)

        conn = None; cursor = None
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            # Check for existing *active* plan for the same user
            cursor.execute("SELECT 1 FROM user_diet_plans WHERE user_id = %s AND active = TRUE LIMIT 1", (patient_user_id,))
            if cursor.fetchone():
                 flash(f"Patient already has an active diet plan assigned. Deactivate the existing one first or edit its end date.", "warning")
                 return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=form_data_repop)

            sql = """INSERT INTO user_diet_plans (user_id, plan_id, assigned_by, start_date, end_date, notes, active, created_at, updated_at)
                     VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())"""
            params = (patient_user_id, plan_id, current_user.id, start_date, end_date, notes)
            cursor.execute(sql, params)
            conn.commit()
            flash("Diet plan assigned successfully.", "success")
            return redirect(url_for('.list_assignments'))

        except mysql.connector.Error as err:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"DB Error Assigning Diet Plan: {err}")
             if err.errno == 1062: flash("Failed to assign plan. A similar active assignment might exist.", "warning") # Should be caught by check above, but just in case
             elif err.errno == 1452: flash("Invalid patient or plan selected. Please check your selections.", "danger") # FK constraint
             else: flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"Error Assigning Diet Plan: {e}", exc_info=True)
             flash("An unexpected error occurred during assignment.", "danger")
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()
        # Re-render form on DB error
        return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=form_data_repop)

    # GET Request
    return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=None)


@diet_plans_bp.route('/assignments', methods=['GET'])
@login_required
def list_assignments():
    """Lists diet plan assignments - Viewable by any doctor."""
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view assignments.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    conn = None; cursor = None; assignments = []
    # TODO: Implement pagination and sorting/filtering for assignments
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT
                udp.user_diet_plan_id, udp.start_date, udp.end_date, udp.active, udp.notes,
                p_user.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                dp.plan_id, dp.plan_name,
                a_user.user_id as assigner_user_id, a_user.first_name as assigner_first_name, a_user.last_name as assigner_last_name
            FROM user_diet_plans udp
            JOIN users p_user ON udp.user_id = p_user.user_id
            JOIN diet_plans dp ON udp.plan_id = dp.plan_id
            LEFT JOIN users a_user ON udp.assigned_by = a_user.user_id
            ORDER BY udp.active DESC, udp.start_date DESC, p_user.last_name
            LIMIT 200 -- Temporary limit, replace with pagination
        """
        cursor.execute(sql)
        assignments = cursor.fetchall()
    except Exception as e:
        flash("Error fetching diet plan assignments.", "danger")
        current_app.logger.error(f"Error listing assignments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    can_manage_assignments = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template('Doctor_Portal/DietPlans/assignments_list.html',
                           assignments=assignments,
                           can_manage_assignments=can_manage_assignments)


@diet_plans_bp.route('/assignments/<int:assignment_id>/deactivate', methods=['POST'])
@login_required
def deactivate_assignment(assignment_id):
    """Deactivate an assignment - Restricted to Dietitians."""
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to deactivate assignments.", "danger")
        # Redirect appropriately based on user role if access denied
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
            return redirect(url_for('.list_assignments'))
        else:
            return redirect(url_for('doctor_main.dashboard'))

    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        # Update the specific assignment to inactive
        cursor.execute("UPDATE user_diet_plans SET active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_diet_plan_id = %s", (assignment_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Assignment deactivated successfully.", "success")
        else:
            # Could be that the assignment ID doesn't exist or was already inactive
            flash("Assignment not found or already inactive.", "warning")
            current_app.logger.warning(f"Deactivation attempt for non-existent or inactive assignment ID: {assignment_id}")
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback()
        flash("Database error deactivating assignment.", "danger")
        current_app.logger.error(f"DB Error deactivating assignment {assignment_id}: {err}")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash("An unexpected error occurred while deactivating the assignment.", "danger")
        current_app.logger.error(f"Error deactivating assignment {assignment_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_assignments'))


@diet_plans_bp.route('/progress/<int:patient_user_id>', methods=['GET'])
@login_required
def view_nutrition_progress(patient_user_id):
    """Views nutritional progress logs - Viewable by authorized doctors/dietitians or the patient themselves."""
    # VIEW access check: Allow if authorized doctor/dietitian OR if the user is the patient themselves
    # Assuming is_doctor_authorized_for_patient checks if the current doctor *can* view this patient
    is_authorized_provider = is_doctor_authorized_for_patient(current_user, patient_user_id)
    is_patient = current_user.id == patient_user_id and current_user.user_type == 'patient'

    if not (is_authorized_provider or is_patient):
         flash("Access denied. You are not authorized to view this patient's progress.", "danger")
         return redirect(url_for('doctor_main.dashboard')) # Redirect appropriately

    conn = None; cursor = None; patient_info = None; logs = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Fetch patient details
        cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_user_id,))
        patient_info = cursor.fetchone()
        if not patient_info:
             flash("Patient not found.", "warning")
             # Redirect based on who is trying to access
             if is_authorized_provider:
                 return redirect(url_for('.list_assignments')) # Or doctor dashboard
             else:
                 return redirect(url_for('patient_routes.dashboard')) # Or patient dashboard

        # Fetch nutrition logs for the patient
        # TODO: Implement pagination for logs if needed
        cursor.execute("SELECT * FROM user_nutrition_logs WHERE user_id = %s ORDER BY log_date DESC LIMIT 100", (patient_user_id,)) # Add LIMIT
        logs = cursor.fetchall()
    except mysql.connector.Error as err:
        flash("Database error fetching nutrition progress.", "danger")
        current_app.logger.error(f"DB Error fetching progress for user {patient_user_id}: {err}")
    except Exception as e:
        flash("An unexpected error occurred while fetching nutrition progress.", "danger")
        current_app.logger.error(f"Error fetching progress for user {patient_user_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Determine if the viewer is the patient themselves (for adding logs)
    can_add_log = is_patient
    # Get current datetime for default log date (requires datetime import)
    from datetime import datetime as dt # Use alias to avoid conflict
    now = dt.now()

    return render_template('Doctor_Portal/DietPlans/nutrition_progress.html',
                           patient=patient_info,
                           logs=logs,
                           can_add_log=can_add_log,
                           now=now # Pass 'now' for default date in form
                           )