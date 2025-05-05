# routes/Doctor_Portal/diet_plan_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort
)
from flask_login import login_required, current_user
from db import get_db_connection
from datetime import date, datetime
import math
import json # For handling target_conditions if stored as JSON (Alternative)
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

# --- Blueprint Definition ---
diet_plans_bp = Blueprint(
    'diet_plans',
    __name__,
    url_prefix='/doctor/diet-plans', # Changed URL prefix
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 10
VALID_SORT_COLUMNS = {
    'name': 'dp.plan_name', 'type': 'dp.plan_type', 'calories': 'dp.calories',
    'id': 'dp.plan_id', 'updated': 'dp.updated_at', 'creator': 'u.last_name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'
ENUM_CACHE = {}

# Specific fetchers
def get_all_conditions(): return get_all_simple('conditions', 'condition_name', 'condition_name', order_by='condition_name', where_clause='is_active = TRUE') # Use name as value, filter active
def get_all_active_patients(): return get_all_simple('users', 'user_id', "CONCAT(first_name, ' ', last_name)", order_by="last_name, first_name", where_clause="user_type = 'patient' AND account_status = 'active'")
def get_all_selectable_diet_plans(user_id): # Show public or user's own plans
     conn = None; cursor = None; items = []
     try:
         conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
         # Select public plans OR plans created by the current user
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
    """Fetches paginated diet plans (can be viewed by any doctor)."""
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
        sql_where = " WHERE 1=1 " # Basic condition, filters added below
        params = []

        # Public or Own filtering (Applied for all viewers for consistency, could be removed if truly all plans should be visible)
        # if current_user and current_user.is_authenticated:
        #     sql_where += " AND (dp.is_public = TRUE OR dp.creator_id = %s)"
        #     params.append(current_user.user_id)

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (dp.plan_name LIKE %s OR dp.description LIKE %s OR dp.target_conditions LIKE %s)"
            params.extend([search_like, search_like, search_like])
        if valid_filters.get('plan_type'):
            sql_where += " AND dp.plan_type = %s"; params.append(valid_filters['plan_type'])
        # Handle boolean filter carefully
        if valid_filters.get('is_public') is not None:
            sql_where += " AND dp.is_public = %s"
            params.append(valid_filters['is_public'])


        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        # Get total count (FOUND_ROWS accounts for filters but not LIMIT)
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
    """Fetches full diet plan details including meals and items."""
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
        if not details['plan']: return None # Not found

        # Fetch meals
        query_meals = """SELECT * FROM diet_plan_meals WHERE plan_id = %s
                         ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack', 'other'), time_of_day, meal_id"""
        cursor.execute(query_meals, (plan_id,))
        meals = cursor.fetchall()

        # Fetch items for all meals if meals exist
        if meals:
            meal_ids = [meal['meal_id'] for meal in meals]
            placeholders = ', '.join(['%s'] * len(meal_ids))
            query_items = f"SELECT * FROM diet_plan_food_items WHERE meal_id IN ({placeholders}) ORDER BY meal_id, item_id"
            cursor.execute(query_items, tuple(meal_ids))
            all_items = cursor.fetchall()

            # Map items to their meals
            items_by_meal = {}
            for item in all_items:
                meal_id = item['meal_id']
                if meal_id not in items_by_meal: items_by_meal[meal_id] = []
                items_by_meal[meal_id].append(item)

            # Attach items to each meal dictionary
            for meal in meals:
                meal['food_items'] = items_by_meal.get(meal['meal_id'], [])

            details['meals'] = meals # Assign meals with items

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
    """Lists diet plans - Viewable by any doctor."""
    # VIEW access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor role required to view diet plans.", "danger")
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
    # Convert filter_public string to boolean for the query helper
    if filter_public == 'true': filters['is_public'] = True
    elif filter_public == 'false': filters['is_public'] = False
    # If filter_public is '', filters['is_public'] remains None (no filter)

    result = get_paginated_diet_plans(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    plans = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    plan_types = get_enum_values('diet_plans', 'plan_type')

    # Determine if the current user can manage plans (for add button)
    can_manage_plans = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_list.html',
        plans=plans, search_term=search_term, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters, plan_types=plan_types,
        valid_sort_columns=VALID_SORT_COLUMNS,
        can_manage_plans=can_manage_plans # Pass flag to template
    )

@diet_plans_bp.route('/<int:plan_id>', methods=['GET'])
@login_required
def view_diet_plan(plan_id):
    """View details of a diet plan - Viewable by any doctor."""
    # VIEW access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor role required to view diet plan details.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    details = get_diet_plan_details(plan_id)
    if not details:
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    # Prepare conditions list for display
    target_conditions_list = []
    if details['plan'].get('target_conditions'):
        target_conditions_list = [c.strip() for c in details['plan']['target_conditions'].split(',') if c.strip()]
    details['plan']['target_conditions_list'] = target_conditions_list

    # Determine if the current user *can* edit this specific plan
    plan_check_info = details['plan']
    # A dietitian can edit public plans AND their own plans
    is_dietitian_creator = (check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
                           plan_check_info.get('creator_id') == current_user.id)
    can_edit_this_plan = (check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
                          plan_check_info.get('is_public')) or is_dietitian_creator

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_detail.html',
        details=details,
        can_edit_this_plan=can_edit_this_plan # Pass flag to template
    )


@diet_plans_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_diet_plan():
    """Handles adding a new diet plan - Restricted to Dietitians."""
    # ADD access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to add diet plans.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
             return redirect(url_for('.list_diet_plans'))
        else:
             return redirect(url_for('doctor_main.dashboard'))

    plan_types = get_enum_values('diet_plans', 'plan_type')
    conditions = get_all_conditions() # Use updated helper

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        # Initialize lists to hold potentially selected IDs even if validation fails
        selected_conditions_list = []
        try:
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            calories = request.form.get('calories'); protein = request.form.get('protein_grams')
            carbs = request.form.get('carbs_grams'); fat = request.form.get('fat_grams')
            fiber = request.form.get('fiber_grams'); sodium = request.form.get('sodium_mg')
            is_public = request.form.get('is_public') == 'on'
            selected_conditions_list = request.form.getlist('target_conditions') # Get list
            target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None

            # --- Validation ---
            if not plan_name: errors.append("Plan Name is required.")
            if not plan_type or plan_type not in plan_types: errors.append("Valid Plan Type is required.")
            def validate_numeric(value, field_name, errors, allow_negative=False, is_float=False):
                if not value: return None
                try:
                    num = float(value) if is_float else int(value)
                    if not allow_negative and num < 0: errors.append(f"{field_name} cannot be negative."); return None
                    return num
                except (ValueError, TypeError): errors.append(f"{field_name} must be a valid number."); return None
            calories_val = validate_numeric(calories, "Calories", errors)
            protein_val = validate_numeric(protein, "Protein", errors); carbs_val = validate_numeric(carbs, "Carbs", errors)
            fat_val = validate_numeric(fat, "Fat", errors); fiber_val = validate_numeric(fiber, "Fiber", errors)
            sodium_val = validate_numeric(sodium, "Sodium", errors)
            if errors: raise ValueError("Validation failed")
            # --- End Validation ---

            conn = get_db_connection();
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor()
            sql = """INSERT INTO diet_plans (plan_name, plan_type, description, calories, protein_grams,
                         carbs_grams, fat_grams, fiber_grams, sodium_mg, is_public, creator_id, target_conditions,
                         created_at, updated_at)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())""" # Use NOW()
            params = (plan_name, plan_type, description, calories_val, protein_val, carbs_val, fat_val,
                      fiber_val, sodium_val, is_public, current_user.user_id, target_conditions_str)
            cursor.execute(sql, params)
            new_plan_id = cursor.lastrowid
            conn.commit()
            flash(f"Diet plan '{plan_name}' added. You can now add meals and food items.", "success")
            return redirect(url_for('.edit_diet_plan', plan_id=new_plan_id))

        except ValueError:
            for err in errors: flash(err, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback(); current_app.logger.error(f"DB Error Adding Diet Plan: {err}")
            flash(f"Database error: {err.msg}", "danger")
        except ConnectionError as ce:
            current_app.logger.error(f"DB Connection Error Adding Diet Plan: {ce}"); flash("Database connection error.", "danger")
        except Exception as e:
            if conn: conn.rollback(); current_app.logger.error(f"Unexpected Error Adding Diet Plan: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error
        form_data = request.form.to_dict()
        form_data['target_conditions'] = selected_conditions_list # Preserve multi-select list
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
            plan=form_data, plan_types=plan_types, conditions=conditions, errors=errors
        )
    # GET request
    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_form.html',
        form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
        plan=None, plan_types=plan_types, conditions=conditions
    )


@diet_plans_bp.route('/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_diet_plan(plan_id):
    """Handles editing an existing diet plan - Restricted to Dietitians or editors of public plans."""
    # EDIT access check (More complex: Dietitian can edit public plans and their own)
    can_edit_this_plan = False
    plan_check_info = None
    conn_check = None; cursor_check = None
    try:
        conn_check = get_db_connection()
        if not conn_check: raise ConnectionError("DB connection failed for auth check")
        cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
        plan_check_info = cursor_check.fetchone()

        if plan_check_info:
            is_dietitian = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)
            is_creator = plan_check_info.get('creator_id') == current_user.id
            is_public = plan_check_info.get('is_public')
            # Allow edit if (Dietitian AND (Public OR Creator))
            if is_dietitian and (is_public or is_creator):
                can_edit_this_plan = True
        else:
             flash("Diet plan not found.", "warning")
             return redirect(url_for('.list_diet_plans'))

    except (ConnectionError, mysql.connector.Error) as db_err:
         current_app.logger.error(f"DB Error checking edit permission for plan {plan_id}: {db_err}")
         flash("Database error checking permissions.", "danger")
         return redirect(url_for('.list_diet_plans'))
    finally:
         if cursor_check: cursor_check.close()
         if conn_check and conn_check.is_connected(): conn_check.close()

    if not can_edit_this_plan:
         flash("Access denied. You do not have permission to edit this diet plan.", "danger")
         # Redirect based on view access
         if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
              return redirect(url_for('.view_diet_plan', plan_id=plan_id))
         else:
              return redirect(url_for('doctor_main.dashboard'))
    # --- End Authorization Check ---

    plan_types = get_enum_values('diet_plans', 'plan_type')
    meal_types = get_enum_values('diet_plan_meals', 'meal_type')
    conditions = get_all_conditions() # Use updated helper

    conn = None; cursor = None
    if request.method == 'POST':
        errors = []
        # Initialize lists to hold potentially selected IDs even if validation fails
        selected_conditions_list = []
        try:
            conn = get_db_connection()
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor()
            conn.start_transaction()

            # --- 1. Update Plan Details ---
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            calories = request.form.get('calories'); protein = request.form.get('protein_grams')
            carbs = request.form.get('carbs_grams'); fat = request.form.get('fat_grams')
            fiber = request.form.get('fiber_grams'); sodium = request.form.get('sodium_mg')
            is_public = request.form.get('is_public') == 'on'
            selected_conditions_list = request.form.getlist('target_conditions')
            target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None

            # --- Plan Validation ---
            def validate_numeric(value, field_name, errors, allow_negative=False, is_float=False):
                if not value: return None
                try:
                    num = float(value) if is_float else int(value)
                    if not allow_negative and num < 0: errors.append(f"{field_name} cannot be negative."); return None
                    return num
                except (ValueError, TypeError): errors.append(f"{field_name} must be a valid number."); return None
            if not plan_name: errors.append("Plan Name is required.")
            # ... validate other plan fields ...
            calories_val = validate_numeric(calories, "Calories", errors); protein_val = validate_numeric(protein, "Protein", errors)
            carbs_val = validate_numeric(carbs, "Carbs", errors); fat_val = validate_numeric(fat, "Fat", errors)
            fiber_val = validate_numeric(fiber, "Fiber", errors); sodium_val = validate_numeric(sodium, "Sodium", errors)
            if errors: raise ValueError("Plan validation failed")

            sql_update_plan = """UPDATE diet_plans SET plan_name=%s, plan_type=%s, description=%s, calories=%s,
                                protein_grams=%s, carbs_grams=%s, fat_grams=%s, fiber_grams=%s, sodium_mg=%s,
                                is_public=%s, target_conditions=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP
                             WHERE plan_id=%s""" # Using updated_by
            params_plan = (plan_name, plan_type, description, calories_val, protein_val, carbs_val, fat_val,
                           fiber_val, sodium_val, is_public, target_conditions_str, current_user.id, plan_id)
            cursor.execute(sql_update_plan, params_plan)
            if cursor.rowcount == 0:
                 # This might happen if the plan was deleted between GET and POST, though unlikely with auth check
                 current_app.logger.warning(f"Update affected 0 rows for plan_id {plan_id}. Plan might be deleted.")
                 # Raise an error to rollback and prevent further processing
                 raise mysql.connector.Error("Plan update affected 0 rows. It might have been deleted.")


            # --- 2. Process Deletions ---
            deleted_meal_ids = request.form.getlist('deleted_meal_ids')
            deleted_item_ids = request.form.getlist('deleted_item_ids')
            if deleted_meal_ids:
                valid_deleted_meal_ids = [int(id) for id in deleted_meal_ids if id.isdigit()]
                if valid_deleted_meal_ids:
                    placeholders = ','.join(['%s'] * len(valid_deleted_meal_ids))
                    # Ensure items are deleted first if CASCADE isn't set
                    cursor.execute(f"DELETE FROM diet_plan_food_items WHERE meal_id IN ({placeholders})", tuple(valid_deleted_meal_ids))
                    sql_delete_meals = f"DELETE FROM diet_plan_meals WHERE meal_id IN ({placeholders}) AND plan_id = %s"
                    cursor.execute(sql_delete_meals, (*valid_deleted_meal_ids, plan_id))
            if deleted_item_ids:
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
                meal_name = request.form.get(f'meal_name[{meal_id}]', '').strip()
                meal_type = request.form.get(f'meal_type[{meal_id}]'); time_of_day = request.form.get(f'meal_time[{meal_id}]') or None
                meal_desc = request.form.get(f'meal_desc[{meal_id}]', '').strip() or None
                meal_cals = validate_numeric(request.form.get(f'meal_calories[{meal_id}]'), f"Calories for Meal {meal_name}", errors) # Validate meal calories
                if not meal_name or not meal_type: continue # Basic validation
                sql_update_meal = "UPDATE diet_plan_meals SET meal_name=%s, meal_type=%s, time_of_day=%s, description=%s, calories=%s WHERE meal_id=%s AND plan_id=%s"
                cursor.execute(sql_update_meal, (meal_name, meal_type, time_of_day, meal_desc, meal_cals, meal_id, plan_id))

                existing_item_ids = request.form.getlist(f'item_id[{meal_id}]')
                for item_id_str in existing_item_ids:
                     if not item_id_str.isdigit() or item_id_str in deleted_item_ids: continue
                     item_id = int(item_id_str)
                     food_name = request.form.get(f'item_food_name[{item_id}]', '').strip()
                     serving = request.form.get(f'item_serving_size[{item_id}]', '').strip()
                     if not food_name or not serving: continue
                     item_notes = request.form.get(f'item_notes[{item_id}]', '').strip() or None
                     alternatives = request.form.get(f'item_alternatives[{item_id}]', '').strip() or None
                     item_cals = validate_numeric(request.form.get(f'item_calories[{item_id}]'), f"Calories for {food_name}", errors)
                     item_prot = validate_numeric(request.form.get(f'item_protein[{item_id}]'), f"Protein for {food_name}", errors, is_float=True)
                     item_carb = validate_numeric(request.form.get(f'item_carbs[{item_id}]'), f"Carbs for {food_name}", errors, is_float=True)
                     item_fat = validate_numeric(request.form.get(f'item_fat[{item_id}]'), f"Fat for {food_name}", errors, is_float=True)
                     if errors: continue # Skip update if validation failed for this item's numerics
                     sql_update_item = """UPDATE diet_plan_food_items SET food_name=%s, serving_size=%s, notes=%s, alternatives=%s,
                                          calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s
                                          WHERE item_id=%s AND meal_id=%s"""
                     cursor.execute(sql_update_item, (food_name, serving, item_notes, alternatives, item_cals, item_prot, item_carb, item_fat, item_id, meal_id))

            # --- 4. Process Inserts (New Meals & Their Items) ---
            new_meal_names = request.form.getlist('new_meal_name')
            new_meal_types = request.form.getlist('new_meal_type'); new_meal_times = request.form.getlist('new_meal_time')
            new_meal_descs = request.form.getlist('new_meal_desc'); new_meal_cals_str = request.form.getlist('new_meal_calories')
            for i, new_name in enumerate(new_meal_names):
                if not new_name.strip(): continue
                new_type = new_meal_types[i] if i < len(new_meal_types) else None
                new_time = new_meal_times[i] if i < len(new_meal_times) and new_meal_times[i] else None
                new_desc = new_meal_descs[i].strip() if i < len(new_meal_descs) else None
                new_cals = validate_numeric(new_meal_cals_str[i] if i < len(new_meal_cals_str) else None, f"Calories for new meal {new_name}", errors)
                if not new_type or new_type not in meal_types or errors: continue # Skip if basic validation fails
                sql_insert_meal = "INSERT INTO diet_plan_meals (plan_id, meal_name, meal_type, time_of_day, description, calories) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(sql_insert_meal, (plan_id, new_name.strip(), new_type, new_time, new_desc, new_cals))
                new_meal_id = cursor.lastrowid

                new_item_names = request.form.getlist(f'new_item_food_name[new_{i}]'); new_item_servings = request.form.getlist(f'new_item_serving_size[new_{i}]')
                new_item_cals_str = request.form.getlist(f'new_item_calories[new_{i}]'); new_item_prot_str = request.form.getlist(f'new_item_protein[new_{i}]')
                new_item_carb_str = request.form.getlist(f'new_item_carbs[new_{i}]'); new_item_fat_str = request.form.getlist(f'new_item_fat[new_{i}]')
                new_item_notes_list = request.form.getlist(f'new_item_notes[new_{i}]'); new_item_alts_list = request.form.getlist(f'new_item_alternatives[new_{i}]')
                for j, item_name in enumerate(new_item_names):
                    if not item_name.strip(): continue
                    item_serving = new_item_servings[j] if j < len(new_item_servings) else '';
                    if not item_serving.strip(): continue
                    item_notes = new_item_notes_list[j].strip() if j < len(new_item_notes_list) else None
                    item_alts = new_item_alts_list[j].strip() if j < len(new_item_alts_list) else None
                    item_cals = validate_numeric(new_item_cals_str[j] if j < len(new_item_cals_str) else None, f"Calories for new item {item_name}", errors)
                    item_prot = validate_numeric(new_item_prot_str[j] if j < len(new_item_prot_str) else None, f"Protein for new item {item_name}", errors, is_float=True)
                    item_carb = validate_numeric(new_item_carb_str[j] if j < len(new_item_carb_str) else None, f"Carbs for new item {item_name}", errors, is_float=True)
                    item_fat = validate_numeric(new_item_fat_str[j] if j < len(new_item_fat_str) else None, f"Fat for new item {item_name}", errors, is_float=True)
                    if errors: continue # Skip insert if validation failed for this item
                    sql_insert_item = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, calories, protein_grams,
                                           carbs_grams, fat_grams, notes, alternatives) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_insert_item, (new_meal_id, item_name.strip(), item_serving.strip(), item_cals, item_prot, item_carb, item_fat, item_notes, item_alts))

            # --- 5. Process Inserts (New Items for EXISTING Meals) ---
            for meal_id_str in existing_meal_ids:
                 if not meal_id_str.isdigit() or meal_id_str in deleted_meal_ids: continue
                 meal_id = int(meal_id_str)
                 new_item_names_ex = request.form.getlist(f'new_item_food_name[{meal_id}]'); new_item_servings_ex = request.form.getlist(f'new_item_serving_size[{meal_id}]')
                 new_item_cals_str_ex = request.form.getlist(f'new_item_calories[{meal_id}]'); new_item_prot_str_ex = request.form.getlist(f'new_item_protein[{meal_id}]')
                 new_item_carb_str_ex = request.form.getlist(f'new_item_carbs[{meal_id}]'); new_item_fat_str_ex = request.form.getlist(f'new_item_fat[{meal_id}]')
                 new_item_notes_ex = request.form.getlist(f'new_item_notes[{meal_id}]'); new_item_alts_ex = request.form.getlist(f'new_item_alternatives[{meal_id}]')
                 for k, item_name in enumerate(new_item_names_ex):
                     if not item_name.strip(): continue
                     item_serving = new_item_servings_ex[k] if k < len(new_item_servings_ex) else '';
                     if not item_serving.strip(): continue
                     item_notes = new_item_notes_ex[k].strip() if k < len(new_item_notes_ex) else None
                     item_alts = new_item_alts_ex[k].strip() if k < len(new_item_alts_ex) else None
                     item_cals = validate_numeric(new_item_cals_str_ex[k] if k < len(new_item_cals_str_ex) else None, f"Calories for new item {item_name} in meal {meal_id}", errors)
                     item_prot = validate_numeric(new_item_prot_str_ex[k] if k < len(new_item_prot_str_ex) else None, f"Protein for new item {item_name} in meal {meal_id}", errors, is_float=True)
                     item_carb = validate_numeric(new_item_carb_str_ex[k] if k < len(new_item_carb_str_ex) else None, f"Carbs for new item {item_name} in meal {meal_id}", errors, is_float=True)
                     item_fat = validate_numeric(new_item_fat_str_ex[k] if k < len(new_item_fat_str_ex) else None, f"Fat for new item {item_name} in meal {meal_id}", errors, is_float=True)
                     if errors: continue # Skip insert if validation failed
                     sql_insert_item_ex = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, calories, protein_grams,
                                            carbs_grams, fat_grams, notes, alternatives) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                     cursor.execute(sql_insert_item_ex, (meal_id, item_name.strip(), item_serving.strip(), item_cals, item_prot, item_carb, item_fat, item_notes, item_alts))

            # --- 6. Check for overall validation errors accumulated during processing ---
            if errors:
                 raise ValueError("Validation errors occurred during meal/item processing.")

            # --- 7. Commit Transaction ---
            conn.commit()
            flash(f"Diet plan '{plan_name}' updated successfully.", "success")
            return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        except ValueError as ve: # Catch validation errors
            if conn and conn.is_connected(): conn.rollback()
            for err in errors: flash(err, 'danger') # Flash specific errors if any
            current_app.logger.warning(f"Validation Error Editing Diet Plan {plan_id}: {ve}")
        except mysql.connector.Error as err: # Catch DB errors
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"DB Error Editing Diet Plan {plan_id}: {err}")
            flash(f"Database error updating plan: {err.msg}", "danger")
        except ConnectionError as ce: # Catch Connection errors
            current_app.logger.error(f"DB Connection Error Editing Diet Plan {plan_id}: {ce}")
            flash("Database connection error.", "danger")
        except Exception as e: # Catch other errors
            if conn and conn.is_connected(): conn.rollback()
            current_app.logger.error(f"Unexpected Error Editing Diet Plan {plan_id}: {e}", exc_info=True)
            flash("An unexpected error occurred during update.", "danger")
        finally: # Clean up
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error - fetch fresh details
        details = get_diet_plan_details(plan_id) or {'plan': {}, 'meals': []}
        # Merge only the top-level plan data from the failed form for repopulation
        submitted_plan_data = {k: v for k, v in request.form.items() if not k.startswith(('meal_', 'item_', 'new_', 'deleted_'))}
        details['plan'].update(submitted_plan_data)
        details['plan']['target_conditions_list'] = request.form.getlist('target_conditions') # Repopulate multi-select
        details['plan']['is_public'] = request.form.get('is_public') == 'on'
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.edit_diet_plan', plan_id=plan_id),
            form_title=f"Edit Diet Plan: {details['plan'].get('plan_name', '')}",
            plan=details['plan'], meals=details.get('meals', []), plan_types=plan_types,
            meal_types=meal_types, conditions=conditions, errors=errors # Pass errors
        )
    # --- GET request ---
    details = get_diet_plan_details(plan_id)
    if not details:
        flash("Diet plan not found.", "warning"); return redirect(url_for('.list_diet_plans'))
    selected_conditions = [];
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

@diet_plans_bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_diet_plan(plan_id):
    """Deletes a diet plan - Restricted based on ownership/public and dietitian role."""
    # DELETE access check (More complex: Dietitian can delete public plans and their own)
    can_delete_this_plan = False
    plan_check_info = None
    conn_check = None; cursor_check = None
    try:
        conn_check = get_db_connection()
        if not conn_check: raise ConnectionError("DB connection failed for auth check")
        cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT plan_name, creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
        plan_check_info = cursor_check.fetchone()

        if plan_check_info:
            is_dietitian = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)
            is_creator = plan_check_info.get('creator_id') == current_user.id
            is_public = plan_check_info.get('is_public')
            # Allow delete if (Dietitian AND (Public OR Creator))
            if is_dietitian and (is_public or is_creator):
                can_delete_this_plan = True
        else:
             # Plan not found, redirect before attempting delete
             flash("Diet plan not found.", "warning")
             return redirect(url_for('.list_diet_plans'))

    except (ConnectionError, mysql.connector.Error) as db_err:
         current_app.logger.error(f"DB Error checking delete permission for plan {plan_id}: {db_err}")
         flash("Database error checking permissions.", "danger")
         return redirect(url_for('.list_diet_plans'))
    finally:
         if cursor_check: cursor_check.close()
         if conn_check and conn_check.is_connected(): conn_check.close()

    if not can_delete_this_plan:
         flash("Access denied. You do not have permission to delete this diet plan.", "danger")
         return redirect(url_for('.view_diet_plan', plan_id=plan_id))
    # --- End Authorization Check ---

    conn = None; cursor = None; plan_name = plan_check_info['plan_name'] # Use name from check
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        conn.start_transaction() # Use transaction

        # Check for active assignments FIRST
        cursor.execute("SELECT 1 FROM user_diet_plans WHERE plan_id = %s AND active = TRUE LIMIT 1", (plan_id,))
        if cursor.fetchone():
             conn.rollback() # Rollback before flashing/redirecting
             flash(f"Cannot delete plan '{plan_name}'. It is actively assigned.", "warning")
             return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        # If CASCADE DELETE is set up in DB for meals/items, this is enough.
        # Otherwise, delete items, then meals, then plan.
        cursor.execute("DELETE FROM diet_plan_food_items WHERE meal_id IN (SELECT meal_id FROM diet_plan_meals WHERE plan_id = %s)", (plan_id,))
        cursor.execute("DELETE FROM diet_plan_meals WHERE plan_id = %s", (plan_id,))
        cursor.execute("DELETE FROM diet_plans WHERE plan_id = %s", (plan_id,))
        conn.commit()
        flash(f"Diet plan '{plan_name}' deleted successfully.", "success")

    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback();
        current_app.logger.error(f"DB Error Deleting Diet Plan {plan_id}: {err}")
        # Foreign key constraint error likely means related inactive assignments exist
        if err.errno == 1451: flash(f"Cannot delete plan '{plan_name}'. Related records (e.g., inactive assignments) exist.", "danger")
        else: flash(f"Database error deleting plan: {err.msg}", "danger")
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


# --- Assignment & Progress Routes ---

@diet_plans_bp.route('/assign', methods=['GET', 'POST'])
@login_required
def assign_diet_plan():
    """Assigns a diet plan to a patient - Restricted to Dietitians."""
    # ASSIGN access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to assign diet plans.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
             return redirect(url_for('.list_assignments'))
        else:
             return redirect(url_for('doctor_main.dashboard'))

    # Fetch lists for form
    patients = get_all_active_patients()
    diet_plans = get_all_selectable_diet_plans(current_user.id)

    if request.method == 'POST':
        patient_user_id = request.form.get('patient_user_id', type=int)
        plan_id = request.form.get('plan_id', type=int)
        start_date_str = request.form.get('start_date'); end_date_str = request.form.get('end_date')
        notes = request.form.get('notes', '').strip() or None; errors = []

        # --- Validation ---
        if not patient_user_id: errors.append("Patient selection is required.")
        if not plan_id: errors.append("Diet Plan selection is required.")
        start_date = None
        if start_date_str:
            try: start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError: errors.append("Invalid Start Date format (YYYY-MM-DD).")
        else: errors.append("Start Date is required.")
        end_date = None
        if end_date_str:
            try: end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError: errors.append("Invalid End Date format (YYYY-MM-DD).")
        if start_date and end_date and end_date < start_date:
            errors.append("End Date cannot be before Start Date.")
        # --- End Validation ---

        if errors:
            for err in errors: flash(err, 'danger')
            return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=request.form)

        conn = None; cursor = None
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            # Optional: Check for existing active plan for the same user (modify as needed)
            cursor.execute("SELECT 1 FROM user_diet_plans WHERE user_id = %s AND active = TRUE LIMIT 1", (patient_user_id,))
            if cursor.fetchone():
                 flash(f"Patient already has an active diet plan assigned. Deactivate the existing one first.", "warning")
                 return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=request.form)

            sql = """INSERT INTO user_diet_plans (user_id, plan_id, assigned_by, start_date, end_date, notes, active, created_at, updated_at)
                     VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())"""
            params = (patient_user_id, plan_id, current_user.user_id, start_date, end_date, notes)
            cursor.execute(sql, params)
            conn.commit()
            flash("Diet plan assigned successfully.", "success")
            return redirect(url_for('.list_assignments'))

        except mysql.connector.Error as err:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"DB Error Assigning Diet Plan: {err}")
             if err.errno == 1062: flash("Failed to assign plan. A similar active assignment might exist.", "warning")
             elif err.errno == 1452: flash("Invalid patient or plan selected.", "danger")
             else: flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"Error Assigning Diet Plan: {e}", exc_info=True)
             flash("An unexpected error occurred during assignment.", "danger")
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()
        # Re-render form on DB error
        return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=request.form)

    # GET Request
    return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans)

@diet_plans_bp.route('/assignments', methods=['GET'])
@login_required
def list_assignments():
    """Lists diet plan assignments - Viewable by any doctor."""
    # VIEW access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor role required to view assignments.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    conn = None; cursor = None; assignments = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT
                udp.user_diet_plan_id, udp.start_date, udp.end_date, udp.active, udp.notes,
                p_user.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                dp.plan_id, dp.plan_name,
                a_user.first_name as assigner_first_name, a_user.last_name as assigner_last_name
            FROM user_diet_plans udp
            JOIN users p_user ON udp.user_id = p_user.user_id
            JOIN diet_plans dp ON udp.plan_id = dp.plan_id
            LEFT JOIN users a_user ON udp.assigned_by = a_user.user_id
            ORDER BY udp.start_date DESC, p_user.last_name
            LIMIT 100 -- Add proper pagination later
        """
        cursor.execute(sql)
        assignments = cursor.fetchall()
    except Exception as e:
        flash("Error fetching diet plan assignments.", "danger")
        current_app.logger.error(f"Error listing assignments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Determine if the user can manage assignments (for Add/Deactivate buttons)
    can_manage_assignments = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template('Doctor_Portal/DietPlans/assignments_list.html',
                           assignments=assignments,
                           can_manage_assignments=can_manage_assignments)

@diet_plans_bp.route('/assignments/<int:assignment_id>/deactivate', methods=['POST'])
@login_required
def deactivate_assignment(assignment_id):
    """Deactivate an assignment - Restricted to Dietitians."""
    # DEACTIVATE access check
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to deactivate assignments.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
             return redirect(url_for('.list_assignments'))
        else:
             return redirect(url_for('doctor_main.dashboard'))

    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        # Optional: Add check if assignment belongs to this dietitian? Or just allow any dietitian to deactivate?
        cursor.execute("UPDATE user_diet_plans SET active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_diet_plan_id = %s", (assignment_id,))
        conn.commit()
        if cursor.rowcount > 0: flash("Assignment deactivated.", "success")
        else: flash("Assignment not found or already inactive.", "warning")
    except Exception as e:
        if conn and conn.is_connected(): conn.rollback()
        flash("Error deactivating assignment.", "danger")
        current_app.logger.error(f"Error deactivating assignment {assignment_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_assignments'))

@diet_plans_bp.route('/progress/<int:patient_user_id>', methods=['GET'])
@login_required
def view_nutrition_progress(patient_user_id):
    """Views nutritional progress logs - Viewable by any doctor or the patient."""
    # VIEW access check: Allow if doctor OR if the user is the patient themselves
    is_doctor = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False)
    is_patient = current_user.user_id == patient_user_id

    if not (is_doctor or is_patient):
         flash("Access denied.", "danger")
         return redirect(url_for('doctor_main.dashboard')) # Redirect non-doctors/non-self

    conn = None; cursor = None; patient_info = None; logs = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_user_id,))
        patient_info = cursor.fetchone()
        if not patient_info:
             flash("Patient not found.", "warning")
             return redirect(url_for('doctor_main.dashboard')) # Redirect if patient doesn't exist

        cursor.execute("SELECT * FROM user_nutrition_logs WHERE user_id = %s ORDER BY log_date DESC", (patient_user_id,))
        logs = cursor.fetchall()
    except Exception as e:
        flash("Error fetching nutrition progress.", "danger")
        current_app.logger.error(f"Error fetching progress for user {patient_user_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Determine if the viewer is the patient themselves (for adding logs)
    can_add_log = is_patient

    return render_template('Doctor_Portal/DietPlans/nutrition_progress.html',
                           patient=patient_info, logs=logs, can_add_log=can_add_log)

# --- END OF FILE diet_plan_management.py ---