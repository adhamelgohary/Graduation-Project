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

# --- Authorization Helper ---
def check_nutritionist_authorization(user):
    if not user or not user.is_authenticated: return False
    return getattr(user, 'user_type', None) == 'nutritionist'

# --- Blueprint Definition ---
diet_plans_bp = Blueprint(
    'diet_plans',
    __name__,
    url_prefix='/nutritionist/diet-plans',
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

# --- Helper Functions ---

# (Keep get_enum_values as before)
def get_enum_values(table_name, column_name):
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
            values = [val.strip("'") for val in enum_str[enum_str.find("(")+1:enum_str.find(")")].split(",")]
        ENUM_CACHE[cache_key] = values; return values
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Generic helper to fetch simple lists (like potential conditions)
def get_all_simple(table_name, id_col, name_col, order_by=None):
    conn = None; cursor = None; items = []
    order_clause = f"ORDER BY {order_by}" if order_by else f"ORDER BY {name_col}"
    try:
        conn = get_db_connection()
        if not conn: raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        query = f"SELECT {id_col}, {name_col} FROM {table_name} {order_clause}"
        cursor.execute(query)
        items = cursor.fetchall()
    except (mysql.connector.Error, ConnectionError) as e:
        current_app.logger.error(f"Error fetching from {table_name}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return items


# (Keep get_paginated_diet_plans as before)
def get_paginated_diet_plans(page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION, filters=None):
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

        # Example Filter: Only show user's own plans + public ones
        if current_user and current_user.is_authenticated:
             sql_where += " AND (dp.creator_id = %s OR dp.is_public = TRUE OR dp.creator_id IS NULL)" # Include system plans (NULL creator)
             params.append(current_user.user_id)

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (dp.plan_name LIKE %s OR dp.description LIKE %s OR dp.target_conditions LIKE %s)"
            params.extend([search_like, search_like, search_like])
        if valid_filters.get('plan_type'):
            sql_where += " AND dp.plan_type = %s"; params.append(valid_filters['plan_type'])
        if valid_filters.get('is_public') is not None:
            sql_where += " AND dp.is_public = %s"; params.append(bool(valid_filters['is_public']))

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total"); total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0
    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching paginated diet plans: {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

# (Keep get_diet_plan_details as before)
def get_diet_plan_details(plan_id):
    conn = None; cursor = None; details = {'plan': None, 'meals': []}
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)
        query_plan = """SELECT dp.*, u.first_name as creator_first_name, u.last_name as creator_last_name
                        FROM diet_plans dp LEFT JOIN users u ON dp.creator_id = u.user_id WHERE dp.plan_id = %s"""
        cursor.execute(query_plan, (plan_id,))
        details['plan'] = cursor.fetchone()
        if not details['plan']: return None
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
            items_by_meal = {}
            for item in all_items:
                meal_id = item['meal_id']
                if meal_id not in items_by_meal: items_by_meal[meal_id] = []
                items_by_meal[meal_id].append(item)
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
    if not check_nutritionist_authorization(current_user):
        flash("Access denied. Nutritionist role required.", "danger")
        return redirect(url_for('doctor_main.dashboard')) # Or appropriate non-auth page

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
    # No else needed, None indicates no filter in get_paginated_diet_plans

    result = get_paginated_diet_plans(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    plans = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    plan_types = get_enum_values('diet_plans', 'plan_type')

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_list.html',
        plans=plans, search_term=search_term, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters, plan_types=plan_types,
        valid_sort_columns=VALID_SORT_COLUMNS
    )

@diet_plans_bp.route('/<int:plan_id>', methods=['GET'])
@login_required
def view_diet_plan(plan_id):
    if not check_nutritionist_authorization(current_user): abort(403)
    details = get_diet_plan_details(plan_id)
    if not details:
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    # Prepare conditions list for display
    target_conditions_list = []
    if details['plan'].get('target_conditions'):
        target_conditions_list = [c.strip() for c in details['plan']['target_conditions'].split(',') if c.strip()]
    details['plan']['target_conditions_list'] = target_conditions_list

    return render_template('Doctor_Portal/DietPlans/diet_plan_detail.html', details=details)

@diet_plans_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_diet_plan():
    """Handles adding a new diet plan. Meals/Items are added via the Edit form."""
    if not check_nutritionist_authorization(current_user): abort(403)

    plan_types = get_enum_values('diet_plans', 'plan_type')
    # Fetch conditions for multi-select
    conditions = get_all_simple('potential_conditions', 'condition_name', 'condition_name', order_by='condition_name') # Use name as value for simplicity

    if request.method == 'POST':
        # Consider using Flask-WTF for robust form handling and validation
        conn = None; cursor = None; errors = []
        try:
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            calories = request.form.get('calories')
            protein = request.form.get('protein_grams')
            carbs = request.form.get('carbs_grams')
            fat = request.form.get('fat_grams')
            fiber = request.form.get('fiber_grams')
            sodium = request.form.get('sodium_mg')
            is_public = request.form.get('is_public') == 'on'
            # Get list of selected conditions from multi-select
            target_conditions_list = request.form.getlist('target_conditions') # Use getlist
            target_conditions_str = ','.join(target_conditions_list) if target_conditions_list else None # Join to string

            # --- Basic Server-Side Validation ---
            if not plan_name: errors.append("Plan Name is required.")
            if not plan_type or plan_type not in plan_types: errors.append("Valid Plan Type is required.")
            # Helper to safely convert to int/float, adds error if invalid format
            def validate_numeric(value, field_name, errors, allow_negative=False, is_float=False):
                if not value: return None # Allow empty
                try:
                    num = float(value) if is_float else int(value)
                    if not allow_negative and num < 0:
                         errors.append(f"{field_name} cannot be negative.")
                         return None # Invalid
                    return num
                except (ValueError, TypeError):
                    errors.append(f"{field_name} must be a valid number.")
                    return None # Invalid
            calories_val = validate_numeric(calories, "Calories", errors)
            protein_val = validate_numeric(protein, "Protein", errors)
            carbs_val = validate_numeric(carbs, "Carbs", errors)
            fat_val = validate_numeric(fat, "Fat", errors)
            fiber_val = validate_numeric(fiber, "Fiber", errors)
            sodium_val = validate_numeric(sodium, "Sodium", errors)

            if errors: raise ValueError("Validation failed")
            # --- End Validation ---

            conn = get_db_connection()
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor()
            sql = """INSERT INTO diet_plans (plan_name, plan_type, description, calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, is_public, creator_id, target_conditions, created_by, updated_by)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            params = (plan_name, plan_type, description, calories_val, protein_val, carbs_val, fat_val, fiber_val, sodium_val, is_public, current_user.user_id, target_conditions_str, current_user.user_id, current_user.user_id)
            cursor.execute(sql, params)
            new_plan_id = cursor.lastrowid
            conn.commit()
            flash(f"Diet plan '{plan_name}' added. You can now add meals and food items.", "success")
            return redirect(url_for('.edit_diet_plan', plan_id=new_plan_id)) # Redirect to edit

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
        form_data['target_conditions'] = request.form.getlist('target_conditions') # Preserve multi-select
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
            plan=form_data, # Pass form data back
            plan_types=plan_types, conditions=conditions, errors=errors
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
    """Handles editing an existing diet plan, including its meals and items."""
    if not check_nutritionist_authorization(current_user): abort(403)

    plan_types = get_enum_values('diet_plans', 'plan_type')
    meal_types = get_enum_values('diet_plan_meals', 'meal_type')
    conditions = get_all_simple('potential_conditions', 'condition_name', 'condition_name', order_by='condition_name')

    conn = None; cursor = None

    # --- Authorization Check ---
    # Fetch plan creator/public status first
    conn_check = get_db_connection()
    if not conn_check: flash("Database connection error.", "danger"); return redirect(url_for('.list_diet_plans'))
    cursor_check = conn_check.cursor(dictionary=True)
    cursor_check.execute("SELECT creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
    plan_check_info = cursor_check.fetchone()
    cursor_check.close(); conn_check.close()

    if not plan_check_info:
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    # Allow editing if public OR if the user is the creator
    can_edit = plan_check_info['is_public'] or plan_check_info['creator_id'] == current_user.user_id
    if not can_edit:
         flash("You do not have permission to edit this diet plan.", "danger")
         return redirect(url_for('.view_diet_plan', plan_id=plan_id))
    # --- End Authorization Check ---


    if request.method == 'POST':
        # NOTE: This section becomes complex due to nested form data.
        # Using Flask-WTF with FieldList and FormField would simplify this significantly.
        errors = []
        try:
            conn = get_db_connection()
            if not conn: raise ConnectionError("DB Connection failed")
            cursor = conn.cursor()
            conn.start_transaction() # Start transaction

            # --- 1. Update Plan Details ---
            plan_name = request.form.get('plan_name', '').strip()
            plan_type = request.form.get('plan_type')
            # ... (get other plan fields as in add_diet_plan POST) ...
            description = request.form.get('description', '').strip() or None
            calories = request.form.get('calories')
            protein = request.form.get('protein_grams')
            carbs = request.form.get('carbs_grams')
            fat = request.form.get('fat_grams')
            fiber = request.form.get('fiber_grams')
            sodium = request.form.get('sodium_mg')
            is_public = request.form.get('is_public') == 'on'
            target_conditions_list = request.form.getlist('target_conditions')
            target_conditions_str = ','.join(target_conditions_list) if target_conditions_list else None

            # --- Plan Validation (reuse helper) ---
            def validate_numeric(value, field_name, errors, allow_negative=False, is_float=False):
                # (same validation helper as in add_diet_plan)
                if not value: return None
                try:
                    num = float(value) if is_float else int(value)
                    if not allow_negative and num < 0: errors.append(f"{field_name} cannot be negative."); return None
                    return num
                except (ValueError, TypeError): errors.append(f"{field_name} must be a valid number."); return None
            if not plan_name: errors.append("Plan Name is required.")
            # ... (validate other plan fields) ...
            calories_val = validate_numeric(calories, "Calories", errors)
            protein_val = validate_numeric(protein, "Protein", errors)
            carbs_val = validate_numeric(carbs, "Carbs", errors)
            fat_val = validate_numeric(fat, "Fat", errors)
            fiber_val = validate_numeric(fiber, "Fiber", errors)
            sodium_val = validate_numeric(sodium, "Sodium", errors)

            if errors: raise ValueError("Plan validation failed")

            sql_update_plan = """UPDATE diet_plans SET plan_name=%s, plan_type=%s, description=%s, calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s, fiber_grams=%s, sodium_mg=%s, is_public=%s, target_conditions=%s, updated_by=%s, updated_at=CURRENT_TIMESTAMP WHERE plan_id=%s"""
            params_plan = (plan_name, plan_type, description, calories_val, protein_val, carbs_val, fat_val, fiber_val, sodium_val, is_public, target_conditions_str, current_user.user_id, plan_id)
            cursor.execute(sql_update_plan, params_plan)

            # --- 2. Process Deletions ---
            deleted_meal_ids = request.form.getlist('deleted_meal_ids')
            deleted_item_ids = request.form.getlist('deleted_item_ids')

            if deleted_meal_ids:
                # Ensure IDs are integers before using in query
                valid_deleted_meal_ids = [int(id) for id in deleted_meal_ids if id.isdigit()]
                if valid_deleted_meal_ids:
                    placeholders = ','.join(['%s'] * len(valid_deleted_meal_ids))
                    # Also deletes associated items due to potential CASCADE or handled in next step
                    sql_delete_meals = f"DELETE FROM diet_plan_meals WHERE meal_id IN ({placeholders}) AND plan_id = %s"
                    cursor.execute(sql_delete_meals, (*valid_deleted_meal_ids, plan_id)) # Add plan_id for safety

            if deleted_item_ids:
                valid_deleted_item_ids = [int(id) for id in deleted_item_ids if id.isdigit()]
                if valid_deleted_item_ids:
                    placeholders = ','.join(['%s'] * len(valid_deleted_item_ids))
                    sql_delete_items = f"DELETE FROM diet_plan_food_items WHERE item_id IN ({placeholders})"
                    cursor.execute(sql_delete_items, tuple(valid_deleted_item_ids))


            # --- 3. Process Updates (Existing Meals/Items) ---
            # Assumes form sends data like meal_name[EXISTING_MEAL_ID], item_food_name[EXISTING_ITEM_ID]
            existing_meal_ids = request.form.getlist('meal_id')
            for meal_id_str in existing_meal_ids:
                if not meal_id_str.isdigit() or meal_id_str in deleted_meal_ids: continue # Skip deleted or invalid
                meal_id = int(meal_id_str)
                meal_name = request.form.get(f'meal_name[{meal_id}]', '').strip()
                meal_type = request.form.get(f'meal_type[{meal_id}]')
                time_of_day = request.form.get(f'meal_time[{meal_id}]') or None
                meal_desc = request.form.get(f'meal_desc[{meal_id}]', '').strip() or None
                # Add validation if needed
                sql_update_meal = "UPDATE diet_plan_meals SET meal_name=%s, meal_type=%s, time_of_day=%s, description=%s WHERE meal_id=%s AND plan_id=%s"
                cursor.execute(sql_update_meal, (meal_name, meal_type, time_of_day, meal_desc, meal_id, plan_id))

                # Update existing items for this meal
                existing_item_ids = request.form.getlist(f'item_id[{meal_id}]')
                for item_id_str in existing_item_ids:
                     if not item_id_str.isdigit() or item_id_str in deleted_item_ids: continue
                     item_id = int(item_id_str)
                     food_name = request.form.get(f'item_food_name[{item_id}]', '').strip()
                     serving = request.form.get(f'item_serving_size[{item_id}]', '').strip()
                     # Add validation
                     if not food_name or not serving: continue # Skip if essential info missing
                     item_notes = request.form.get(f'item_notes[{item_id}]', '').strip() or None
                     alternatives = request.form.get(f'item_alternatives[{item_id}]', '').strip() or None
                     # Get other numeric values and validate them...
                     sql_update_item = "UPDATE diet_plan_food_items SET food_name=%s, serving_size=%s, notes=%s, alternatives=%s WHERE item_id=%s AND meal_id=%s"
                     cursor.execute(sql_update_item, (food_name, serving, item_notes, alternatives, item_id, meal_id))


            # --- 4. Process Inserts (New Meals & Their Items) ---
            # Assumes form sends data like new_meal_name[], new_item_food_name[new_meal_INDEX][]
            new_meal_names = request.form.getlist('new_meal_name')
            new_meal_types = request.form.getlist('new_meal_type')
            new_meal_times = request.form.getlist('new_meal_time')
            new_meal_descs = request.form.getlist('new_meal_desc')

            for i, new_name in enumerate(new_meal_names):
                if not new_name.strip(): continue # Skip empty new meals
                new_type = new_meal_types[i] if i < len(new_meal_types) else None
                new_time = new_meal_times[i] if i < len(new_meal_times) and new_meal_times[i] else None
                new_desc = new_meal_descs[i].strip() if i < len(new_meal_descs) else None
                # Add validation
                if not new_type or new_type not in meal_types: continue # Skip invalid type

                sql_insert_meal = "INSERT INTO diet_plan_meals (plan_id, meal_name, meal_type, time_of_day, description) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql_insert_meal, (plan_id, new_name.strip(), new_type, new_time, new_desc))
                new_meal_id = cursor.lastrowid

                # Add new items associated with this *new* meal (indexed by 'i')
                new_item_names = request.form.getlist(f'new_item_food_name[new_{i}]')
                new_item_servings = request.form.getlist(f'new_item_serving_size[new_{i}]')
                new_item_notes_list = request.form.getlist(f'new_item_notes[new_{i}]')
                new_item_alts_list = request.form.getlist(f'new_item_alternatives[new_{i}]')

                for j, item_name in enumerate(new_item_names):
                    if not item_name.strip(): continue
                    item_serving = new_item_servings[j] if j < len(new_item_servings) else ''
                    # Add validation
                    if not item_serving.strip(): continue
                    item_notes = new_item_notes_list[j].strip() if j < len(new_item_notes_list) else None
                    item_alts = new_item_alts_list[j].strip() if j < len(new_item_alts_list) else None
                    # Get other numeric values...
                    sql_insert_item = "INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives) VALUES (%s, %s, %s, %s, %s)"
                    cursor.execute(sql_insert_item, (new_meal_id, item_name.strip(), item_serving.strip(), item_notes, item_alts))


            # --- 5. Process Inserts (New Items for EXISTING Meals) ---
            # Assumes form sends data like new_item_food_name[EXISTING_MEAL_ID][]
            for meal_id_str in existing_meal_ids:
                 if not meal_id_str.isdigit() or meal_id_str in deleted_meal_ids: continue
                 meal_id = int(meal_id_str)
                 new_item_names_ex = request.form.getlist(f'new_item_food_name[{meal_id}]')
                 new_item_servings_ex = request.form.getlist(f'new_item_serving_size[{meal_id}]')
                 new_item_notes_ex = request.form.getlist(f'new_item_notes[{meal_id}]')
                 new_item_alts_ex = request.form.getlist(f'new_item_alternatives[{meal_id}]')

                 for k, item_name in enumerate(new_item_names_ex):
                     if not item_name.strip(): continue
                     item_serving = new_item_servings_ex[k] if k < len(new_item_servings_ex) else ''
                     if not item_serving.strip(): continue
                     item_notes = new_item_notes_ex[k].strip() if k < len(new_item_notes_ex) else None
                     item_alts = new_item_alts_ex[k].strip() if k < len(new_item_alts_ex) else None
                     # Get other numeric values...
                     sql_insert_item_ex = "INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives) VALUES (%s, %s, %s, %s, %s)"
                     cursor.execute(sql_insert_item_ex, (meal_id, item_name.strip(), item_serving.strip(), item_notes, item_alts))


            # --- 6. Commit Transaction ---
            conn.commit()
            flash(f"Diet plan '{plan_name}' updated successfully.", "success")
            return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        except ValueError as ve: # Catch validation errors explicitly
            if conn: conn.rollback()
            # Don't flash the generic message, specific errors already flashed potentially
            current_app.logger.warning(f"Validation Error Editing Diet Plan {plan_id}: {ve}")
            # Fall through to re-render form
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB Error Editing Diet Plan {plan_id}: {err}")
            flash(f"Database error updating plan: {err.msg}", "danger")
        except ConnectionError as ce:
            current_app.logger.error(f"DB Connection Error Editing Diet Plan {plan_id}: {ce}")
            flash("Database connection error.", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Unexpected Error Editing Diet Plan {plan_id}: {e}", exc_info=True)
            flash("An unexpected error occurred during update.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error - fetch fresh details to avoid stale meal/item data if tx failed mid-way
        details = get_diet_plan_details(plan_id) or {'plan': {}, 'meals': []} # Handle fetch failure
        # Merge submitted form data back into the plan details for repopulation
        submitted_plan_data = request.form.to_dict()
        submitted_plan_data['target_conditions_list'] = request.form.getlist('target_conditions') # Get list
        details['plan'].update(submitted_plan_data)
        details['plan']['is_public'] = request.form.get('is_public') == 'on' # Handle checkbox

        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.edit_diet_plan', plan_id=plan_id),
            form_title=f"Edit Diet Plan: {details['plan'].get('plan_name', '')}",
            plan=details['plan'],
            meals=details.get('meals', []), # Pass potentially updated meal structure if fetch needed
            plan_types=plan_types,
            meal_types=meal_types,
            conditions=conditions,
            errors=errors # Pass validation errors
        )

    # --- GET request ---
    details = get_diet_plan_details(plan_id)
    if not details: # Already checked auth, so this is likely 404 after check
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    # Prepare conditions list for multi-select pre-selection
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

@diet_plans_bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_diet_plan(plan_id):
    """Deletes a diet plan after authorization check."""
    if not check_nutritionist_authorization(current_user): abort(403)

    conn = None; cursor = None; plan_name = f"ID {plan_id}" # Default name
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor(dictionary=True)

        # Fetch info needed for Auth check and flash message
        cursor.execute("SELECT plan_name, creator_id, is_public FROM diet_plans WHERE plan_id = %s", (plan_id,))
        plan_info = cursor.fetchone()
        if not plan_info:
            flash("Diet plan not found.", "warning"); return redirect(url_for('.list_diet_plans'))
        plan_name = plan_info['plan_name'] # Update name for flash message

        # Authorization Check: Allow deleting if public OR if the user is the creator
        can_delete = plan_info['is_public'] or plan_info['creator_id'] == current_user.user_id
        if not can_delete:
            flash("You do not have permission to delete this diet plan.", "danger")
            return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        # Check for active assignments
        cursor.execute("SELECT 1 FROM user_diet_plans WHERE plan_id = %s AND active = TRUE LIMIT 1", (plan_id,))
        if cursor.fetchone():
             flash(f"Cannot delete plan '{plan_name}'. It is actively assigned.", "warning")
             return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        # Perform deletion (assuming CASCADE delete for meals/items is set up in DB)
        cursor.execute("DELETE FROM diet_plans WHERE plan_id = %s", (plan_id,))
        conn.commit()
        flash(f"Diet plan '{plan_name}' deleted successfully.", "success")

    except mysql.connector.Error as err:
        if conn: conn.rollback(); current_app.logger.error(f"DB Error Deleting Diet Plan {plan_id}: {err}")
        if err.errno == 1451: flash(f"Cannot delete plan '{plan_name}'. Related records (e.g., inactive assignments) exist.", "danger")
        else: flash(f"Database error deleting plan: {err.msg}", "danger")
    except ConnectionError as ce:
        current_app.logger.error(f"DB Connection Error Deleting Diet Plan {plan_id}: {ce}"); flash("Database connection error.", "danger")
    except Exception as e:
        if conn: conn.rollback(); current_app.logger.error(f"Unexpected Error Deleting Diet Plan {plan_id}: {e}", exc_info=True)
        flash(f"An unexpected error occurred while deleting '{plan_name}'.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.list_diet_plans'))


# --- Assignment & Progress Routes (Basic Structure) ---

@diet_plans_bp.route('/assign', methods=['GET', 'POST'])
@login_required
def assign_diet_plan():
    """Assigns a diet plan to a patient."""
    if not check_nutritionist_authorization(current_user): abort(403)

    if request.method == 'POST':
        patient_user_id = request.form.get('patient_user_id', type=int)
        plan_id = request.form.get('plan_id', type=int)
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        notes = request.form.get('notes', '').strip() or None
        errors = []

        # Validation
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

        if errors:
            for err in errors: flash(err, 'danger')
            # Re-render form (need to pass lists again)
            patients = get_all_simple('users', 'user_id', "CONCAT(first_name, ' ', last_name)", order_by="last_name, first_name") # Fetch patients again
            diet_plans = get_all_simple('diet_plans', 'plan_id', 'plan_name') # Fetch plans again
            return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=request.form)


        conn = None; cursor = None
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            # Check for existing active plan for the same user (optional - based on unique constraint)
            # cursor.execute("SELECT 1 FROM user_diet_plans WHERE user_id = %s AND plan_id = %s AND active = TRUE", (patient_user_id, plan_id))
            # if cursor.fetchone():
            #     flash("This patient is already actively assigned this diet plan.", "warning")
            #     return redirect(url_for('.assign_diet_plan')) # Or back to form

            sql = """INSERT INTO user_diet_plans (user_id, plan_id, assigned_by, start_date, end_date, notes, active)
                     VALUES (%s, %s, %s, %s, %s, %s, TRUE)"""
            params = (patient_user_id, plan_id, current_user.user_id, start_date, end_date, notes)
            cursor.execute(sql, params)
            conn.commit()
            flash("Diet plan assigned successfully.", "success")
            return redirect(url_for('.list_assignments')) # Redirect to assignments list

        except mysql.connector.Error as err:
             if conn: conn.rollback(); current_app.logger.error(f"DB Error Assigning Diet Plan: {err}")
             # Handle specific errors like duplicate entry if constraint is strict
             if err.errno == 1062: flash("Failed to assign plan. This plan might already be assigned to this user.", "warning")
             else: flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
             if conn: conn.rollback(); current_app.logger.error(f"Error Assigning Diet Plan: {e}", exc_info=True)
             flash("An unexpected error occurred during assignment.", "danger")
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()

        # Re-render form if DB error occurred after validation
        patients = get_all_simple('users', 'user_id', "CONCAT(first_name, ' ', last_name)", order_by="last_name, first_name")
        diet_plans = get_all_simple('diet_plans', 'plan_id', 'plan_name')
        return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans, form_data=request.form)


    # GET Request
    # Fetch lists needed for the assignment form dropdowns
    # Filter users to only show 'patient' type
    patients = get_all_simple('users', 'user_id', "CONCAT(first_name, ' ', last_name)", order_by="last_name, first_name") # Ideally, filter WHERE user_type='patient'
    # Filter plans to show public or created by current user
    diet_plans = get_all_simple('diet_plans', 'plan_id', 'plan_name') # Ideally, filter WHERE is_public=TRUE OR creator_id=current_user.user_id
    return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans)


@diet_plans_bp.route('/assignments', methods=['GET'])
@login_required
def list_assignments():
    """Lists diet plan assignments."""
    if not check_nutritionist_authorization(current_user): abort(403)

    # TODO: Implement pagination, filtering (by patient, by plan), sorting
    conn = None; cursor = None; assignments = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        # Query to get assignments, joining with users (patient) and diet_plans
        sql = """
            SELECT
                udp.user_diet_plan_id, udp.start_date, udp.end_date, udp.active, udp.notes,
                p.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                dp.plan_id, dp.plan_name,
                a_user.first_name as assigner_first_name, a_user.last_name as assigner_last_name
            FROM user_diet_plans udp
            JOIN users p_user ON udp.user_id = p_user.user_id
            JOIN patients p ON udp.user_id = p.user_id -- Assuming patient record always exists
            JOIN diet_plans dp ON udp.plan_id = dp.plan_id
            LEFT JOIN users a_user ON udp.assigned_by = a_user.user_id
            ORDER BY udp.start_date DESC, p_user.last_name
            LIMIT 100 -- Add proper pagination later
        """
        # Add WHERE clause if filtering needed, e.g., WHERE udp.assigned_by = %s
        cursor.execute(sql)
        assignments = cursor.fetchall()
    except Exception as e:
        flash("Error fetching diet plan assignments.", "danger")
        current_app.logger.error(f"Error listing assignments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Doctor_Portal/DietPlans/assignments_list.html', assignments=assignments)

# Example route to deactivate an assignment (could be AJAX)
@diet_plans_bp.route('/assignments/<int:assignment_id>/deactivate', methods=['POST'])
@login_required
def deactivate_assignment(assignment_id):
    if not check_nutritionist_authorization(current_user): abort(403)
    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        # Optional: Check if current user is the one who assigned it
        cursor.execute("UPDATE user_diet_plans SET active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_diet_plan_id = %s", (assignment_id,))
        conn.commit()
        if cursor.rowcount > 0: flash("Assignment deactivated.", "success")
        else: flash("Assignment not found.", "warning")
    except Exception as e:
        if conn: conn.rollback()
        flash("Error deactivating assignment.", "danger")
        current_app.logger.error(f"Error deactivating assignment {assignment_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return redirect(url_for('.list_assignments'))


@diet_plans_bp.route('/progress/<int:patient_user_id>', methods=['GET'])
@login_required
def view_nutrition_progress(patient_user_id):
    """Views nutritional progress logs for a specific patient."""
    # Authorization: Allow nutritionist or the patient themselves
    if not check_nutritionist_authorization(current_user) and current_user.user_id != patient_user_id:
         abort(403) # Or redirect with error

    # Fetch patient info
    conn = None; cursor = None; patient_info = None; logs = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_user_id,))
        patient_info = cursor.fetchone()
        if not patient_info:
             flash("Patient not found.", "warning")
             # Redirect based on user type
             if check_nutritionist_authorization(current_user): return redirect(url_for('.list_assignments')) # Or patient list
             else: return redirect(url_for('doctor_main.dashboard')) # Patient's own dashboard

        # Fetch nutrition logs for this patient
        cursor.execute("SELECT * FROM user_nutrition_logs WHERE user_id = %s ORDER BY log_date DESC", (patient_user_id,))
        logs = cursor.fetchall()

    except Exception as e:
        flash("Error fetching nutrition progress.", "danger")
        current_app.logger.error(f"Error fetching progress for user {patient_user_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Patient might want to add a new log from this page
    can_add_log = current_user.user_id == patient_user_id

    return render_template('Doctor_Portal/DietPlans/nutrition_progress.html',
                           patient=patient_info,
                           logs=logs,
                           can_add_log=can_add_log)