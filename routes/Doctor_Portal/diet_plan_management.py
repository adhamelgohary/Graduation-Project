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
import decimal # For handling decimal types from DB
import re # For regex in get_all_simple
import logging

logger = logging.getLogger(__name__)

try:
    from .utils import check_doctor_or_dietitian_authorization
except ImportError:
    # Fallback if utils is one level up (adjust as needed for your structure)
    from ..utils import check_doctor_or_dietitian_authorization

def get_provider_id(user):
    if hasattr(user, 'is_authenticated') and user.is_authenticated and hasattr(user, 'id'):
        return user.id
    return None

def is_doctor_authorized_for_patient(doctor_user, patient_user_id):
    # Placeholder: In a real app, check if this doctor is assigned to this patient
    # or has general permissions based on department/clinic rules.
    # For now, allowing if the doctor is a doctor/dietitian.
    return check_doctor_or_dietitian_authorization(doctor_user, require_dietitian_for_edit=False)

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
    'protein': 'dp.protein_grams', 'carbs': 'dp.carbs_grams', 'fat': 'dp.fat_grams',
    'id': 'dp.plan_id', 'updated': 'dp.updated_at', 'creator': 'u.last_name'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'

# --- Custom Jinja Filter (or make it a context processor) ---
def timedelta_to_time_filter(delta):
    if isinstance(delta, timedelta):
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        # seconds = total_seconds % 60 # Usually not needed for display
        try:
            return time(hours % 24, minutes) # Return as time object
        except ValueError:
            logger.warning(f"Could not convert timedelta {delta} to time object.")
            return None # Or return original delta string
    elif isinstance(delta, time):
        return delta # Already a time object
    return None

# Register the filter with the Blueprint's Jinja environment
@diet_plans_bp.app_template_filter()
def format_timedelta_as_time(delta):
    time_obj = timedelta_to_time_filter(delta)
    if time_obj:
        return time_obj.strftime('%I:%M %p')
    return "N/A" # Fallback for None or unconvertible types


# --- INTERNALIZED Helper Functions ---
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
    except (ValueError, TypeError): 
        try: return datetime.strptime(time_str, '%H:%M:%S').time() # Attempt with seconds
        except (ValueError, TypeError): return None


def calculate_nutrient_totals(items_list):
    totals = {
        'calories': 0, 'protein_grams': 0.0, 'carbs_grams': 0.0, 'fat_grams': 0.0,
        'fiber_grams': 0.0, 'sodium_mg': 0
    }
    found_data = {key: False for key in totals}
    nutrient_keys = list(totals.keys()) 

    for item in items_list:
        for key in nutrient_keys:
            item_val = item.get(key) 
            if item_val is not None:
                try:
                    if key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams']:
                        num_val = float(item_val)
                    else: 
                        num_val = int(item_val)
                    
                    totals[key] += num_val
                    found_data[key] = True
                except (ValueError, TypeError):
                    current_app.logger.debug(f"NutrientCalc: Could not convert item value '{item_val}' for nutrient '{key}'.")
                    pass
    
    for key in nutrient_keys:
        if not found_data[key]:
            totals[key] = None
        elif key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams'] and totals[key] is not None:
            totals[key] = round(totals[key], 2) 
    return totals

def get_all_simple(table_name, 
                   id_column, 
                   name_column_expression, 
                   display_name_alias="display_name", 
                   order_by=None, 
                   where_clause="1=1"):
    """
    Fetches a list of items (ID and display name) from a specified table.

    Args:
        table_name (str): The name of the database table.
        id_column (str): The name of the column to be used as the ID/value.
        name_column_expression (str): The column name or SQL expression (e.g., CONCAT) 
                                      for the display name.
        display_name_alias (str, optional): The alias for the name_column_expression 
                                            in the SQL query. Defaults to "display_name".
        order_by (str, optional): SQL ORDER BY clause content (e.g., "column_name ASC"). 
                                  If None, defaults to ordering by display_name_alias ASC.
        where_clause (str, optional): SQL WHERE clause content (without "WHERE" keyword). 
                                      Defaults to "1=1" (no filtering).

    Returns:
        list: A list of dictionaries, each with id_column and display_name_alias keys, 
              or an empty list on error.
    """
    conn = None
    cursor = None
    results = []

    # Basic validation for table and fixed column names
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name) or \
       not re.match(r'^[a-zA-Z0-9_]+$', id_column) or \
       not re.match(r'^[a-zA-Z0-9_]+$', display_name_alias):
        if current_app:
            current_app.logger.error(f"Invalid table_name, id_column, or display_name_alias in get_all_simple for table '{table_name}'.")
        else:
            print(f"ERROR: Invalid table_name, id_column, or display_name_alias in get_all_simple for table '{table_name}'.")
        return []

    # name_column_expression can be complex (e.g., CONCAT function call),
    # so direct backtick quoting might be problematic. It's used as is in the SELECT.
    # Ensure it's constructed safely if it ever comes from untrusted input (not the case here).

    try:
        conn = get_db_connection()
        if not conn:
            if current_app: current_app.logger.error("get_all_simple: Database connection failed.")
            else: print("ERROR: get_all_simple: Database connection failed.")
            return []
            
        cursor = conn.cursor(dictionary=True)

        safe_table = f"`{table_name}`"
        safe_id_col = f"`{id_column}`"
        
        # Construct ORDER BY clause
        order_by_sql = ""
        if order_by:
            # Basic sanitization for order_by: allow column names, ASC/DESC, commas, spaces, backticks, dots for table.column
            # This regex aims to be somewhat permissive for valid SQL ORDER BY clauses but block obvious SQL injection.
            # It allows for things like `table_alias`.`column_name` ASC, `another_column` DESC
            if not re.match(r"^[a-zA-Z0-9_`,\s\.]+(?i:\s+(ASC|DESC))?(?:\s*,\s*[a-zA-Z0-9_`,\s\.]+(?i:\s+(ASC|DESC))?)*$", order_by):
                if current_app:
                    current_app.logger.warning(f"Potentially unsafe characters in order_by clause: '{order_by}'. Defaulting order.")
                else:
                    print(f"WARNING: Potentially unsafe characters in order_by clause: '{order_by}'. Defaulting order.")
                order_by_sql = f"ORDER BY `{display_name_alias}` ASC" 
            else:
                order_by_sql = f"ORDER BY {order_by}" 
        else: 
            order_by_sql = f"ORDER BY `{display_name_alias}` ASC" # Default order by the display name alias

        # Ensure where_clause is reasonably safe if it's ever dynamic (here it's hardcoded or trusted)
        # For this specific use case where `where_clause` is hardcoded in calling functions,
        # extensive sanitization here might be overkill, but good for a general utility.
        # A very basic check:
        if where_clause.lower().strip() not in ["1=1", "is_active = true", "user_type = 'patient' and account_status = 'active'"] and \
           not all(char.isalnum() or char in ['=', "'", " ", "_", "%", "(", ")", "AND", "OR", "IS", "NULL", ".", "<", ">", "!"] for char in where_clause.upper()): # Added more allowed chars
            if current_app:
                current_app.logger.warning(f"Potentially unsafe WHERE clause provided: '{where_clause}'. Using default '1=1'.")
            else:
                 print(f"WARNING: Potentially unsafe WHERE clause provided: '{where_clause}'. Using default '1=1'.")
            where_clause_to_use = "1=1"
        else:
            where_clause_to_use = where_clause


        query = f"SELECT {safe_id_col} AS value, {name_column_expression} AS {display_name_alias} FROM {safe_table} WHERE {where_clause_to_use} {order_by_sql}"
        # Aliasing id_column as 'value' for consistency if templates expect that, or keep as original id_column name.
        # For your current usage, using the original id_column name is fine as you access patient.user_id etc.
        # So let's revert that part of the change if your templates expect the original id_column name.
        query = f"SELECT {safe_id_col}, {name_column_expression} AS {display_name_alias} FROM {safe_table} WHERE {where_clause_to_use} {order_by_sql}"


        if current_app:
            current_app.logger.debug(f"Executing get_all_simple query: {query}")
        else:
            print(f"DEBUG: Executing get_all_simple query: {query}")
            
        cursor.execute(query)
        results = cursor.fetchall()

    except mysql.connector.Error as err:
        if current_app:
            current_app.logger.error(f"Database error in get_all_simple for {table_name}: {err}", exc_info=True)
        else:
            print(f"DATABASE ERROR in get_all_simple for {table_name}: {err}")
    except Exception as e: 
        if current_app:
            current_app.logger.error(f"Unexpected error in get_all_simple for {table_name}: {e}", exc_info=True)
        else:
            print(f"UNEXPECTED ERROR in get_all_simple for {table_name}: {e}")
    finally:
        if cursor: 
            cursor.close()
        if conn and conn.is_connected(): 
            conn.close()
            
    # Ensure each result has the id_column and the display_name_alias
    # If the id_column was aliased to 'value', then we need to make sure the template uses 'value'
    # Or, we can rename it back here or not alias it in the query.
    # Given your template uses patient.user_id, we should NOT alias id_column to 'value'.
    # The query `SELECT {safe_id_col}, {name_column_expression} AS {display_name_alias}` is correct for that.

    return results

# --- Specific Fetchers using the internalized get_all_simple ---
def get_all_conditions(): 
    return get_all_simple(
        table_name='conditions', 
        id_column='condition_name', 
        name_column_expression='condition_name', 
        display_name_alias='condition_display_name', # Template will use condition.condition_display_name
        order_by='condition_name ASC', 
        where_clause='is_active = TRUE'
    )

def get_all_active_patients(): 
    return get_all_simple(
        table_name='users', 
        id_column='user_id', # Template will use patient.user_id
        name_column_expression="CONCAT(first_name, ' ', last_name)", 
        display_name_alias="patient_display_name", # Template will use patient.patient_display_name
        order_by="last_name ASC, first_name ASC",
        where_clause="user_type = 'patient' AND account_status = 'active'"
    )

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


# --- Data Fetching Functions (get_paginated_diet_plans, get_diet_plan_details) ---
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
        sql_where = " WHERE 1=1 " # Start with a true condition
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (dp.plan_name LIKE %s OR dp.description LIKE %s OR dp.target_conditions LIKE %s)"
            params.extend([search_like, search_like, search_like])
        if valid_filters.get('plan_type'):
            sql_where += " AND dp.plan_type = %s"; params.append(valid_filters['plan_type'])
        if 'is_public' in valid_filters and valid_filters['is_public'] is not None: # Check specific key presence
            sql_where += " AND dp.is_public = %s"
            params.append(1 if valid_filters['is_public'] else 0)

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
        meals_raw = cursor.fetchall()
        
        meals_processed = []
        if meals_raw:
            meal_ids = [meal['meal_id'] for meal in meals_raw]
            placeholders = ', '.join(['%s'] * len(meal_ids))
            query_items = f"SELECT * FROM diet_plan_food_items WHERE meal_id IN ({placeholders}) ORDER BY meal_id, item_id"
            cursor.execute(query_items, tuple(meal_ids))
            all_items_raw = cursor.fetchall()
            
            items_by_meal = {}
            for item_raw in all_items_raw:
                item = item_raw.copy() # Work on a copy
                for key, value in item.items():
                     if isinstance(value, decimal.Decimal):
                         item[key] = float(value) 
                meal_id = item['meal_id']
                if meal_id not in items_by_meal: items_by_meal[meal_id] = []
                items_by_meal[meal_id].append(item)

            for meal_raw in meals_raw:
                meal = meal_raw.copy() # Work on a copy
                # Use the timedelta_to_time_filter for consistent time object handling
                meal['time_of_day_obj'] = timedelta_to_time_filter(meal.get('time_of_day'))
                
                # If you also want a formatted string directly in the meal dict (optional)
                # meal['time_of_day_formatted'] = format_timedelta_as_time(meal.get('time_of_day'))
                
                meal['food_items'] = items_by_meal.get(meal['meal_id'], [])
                meals_processed.append(meal)
            details['meals'] = meals_processed

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
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view diet plans.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()
    filter_type = request.args.get('filter_type', '')
    filter_public_str = request.args.get('filter_public', '')

    if sort_by not in VALID_SORT_COLUMNS: sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION

    filters = {}
    if filter_type: filters['plan_type'] = filter_type
    if filter_public_str == 'true': filters['is_public'] = True
    elif filter_public_str == 'false': filters['is_public'] = False
    
    result = get_paginated_diet_plans(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir, filters)
    plans = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0
    
    plan_types_enum_list = get_enum_values('diet_plans', 'plan_type')

    can_manage_plans = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_list.html',
        plans=plans, search_term=search_term, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters, plan_types=plan_types_enum_list, 
        valid_sort_columns=VALID_SORT_COLUMNS,
        can_manage_plans=can_manage_plans,
        request_args=request.args
    )

@diet_plans_bp.route('/<int:plan_id>', methods=['GET'])
@login_required
def view_diet_plan(plan_id):
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view diet plan details.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    details = get_diet_plan_details(plan_id)
    if not details or not details['plan']: 
        flash("Diet plan not found.", "warning")
        return redirect(url_for('.list_diet_plans'))

    target_conditions_list = []
    if details['plan'].get('target_conditions'):
        target_conditions_list = [c.strip() for c in details['plan']['target_conditions'].split(',') if c.strip()]
    details['plan']['target_conditions_list'] = target_conditions_list

    is_dietitian_creator = (
        check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
        details['plan'].get('creator_id') == current_user.id
    )
    can_edit_this_plan = (
        check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True) and
        details['plan'].get('is_public')
    ) or is_dietitian_creator
    
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

    plan_types_enum_list = get_enum_values('diet_plans', 'plan_type')
    conditions_for_dropdown = get_all_conditions() 
    meal_types_enum_list = get_enum_values('diet_plan_meals', 'meal_type')

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        plan_name = request.form.get('plan_name', '').strip()
        plan_type_form = request.form.get('plan_type') 
        description = request.form.get('description', '').strip() or None
        is_public = request.form.get('is_public') == 'on'
        selected_conditions_list = request.form.getlist('target_conditions')
        target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None
        
        plan_calories, plan_protein, plan_carbs, plan_fat, plan_fiber, plan_sodium = [None] * 6

        if not plan_name: errors.append("Plan Name is required.")
        if not plan_type_form or plan_type_form not in plan_types_enum_list: errors.append("Valid Plan Type is required.")
        
        plan_calories = validate_numeric(request.form.get('plan_calories'), "Plan Calories", errors, required=False)
        plan_protein = validate_numeric(request.form.get('plan_protein_grams'), "Plan Protein", errors, is_float=True, required=False)
        plan_carbs = validate_numeric(request.form.get('plan_carbs_grams'), "Plan Carbs", errors, is_float=True, required=False)
        plan_fat = validate_numeric(request.form.get('plan_fat_grams'), "Plan Fat", errors, is_float=True, required=False)
        plan_fiber = validate_numeric(request.form.get('plan_fiber_grams'), "Plan Fiber", errors, is_float=True, required=False)
        plan_sodium = validate_numeric(request.form.get('plan_sodium_mg'), "Plan Sodium", errors, required=False)

        if errors: 
            form_data = request.form.to_dict()
            form_data['target_conditions_list'] = selected_conditions_list 
            form_data['is_public'] = is_public
            return render_template(
                'Doctor_Portal/DietPlans/diet_plan_form.html',
                form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
                plan=form_data, meals=[], plan_types=plan_types_enum_list,
                meal_types=meal_types_enum_list, conditions=conditions_for_dropdown, errors=errors
            )
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            conn.start_transaction()
            sql_insert_plan = """INSERT INTO diet_plans (plan_name, plan_type, description,
                                 calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg,
                                 is_public, creator_id, target_conditions,
                                 created_at, updated_at, updated_by)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)"""
            params_plan = (plan_name, plan_type_form, description,
                           plan_calories, plan_protein, plan_carbs, plan_fat, plan_fiber, plan_sodium,
                           is_public, current_user.id, target_conditions_str, current_user.id)
            cursor.execute(sql_insert_plan, params_plan)
            new_plan_id = cursor.lastrowid
            conn.commit()
            flash(f"Diet plan '{plan_name}' created. You can now add meals and food items.", "success")
            return redirect(url_for('.edit_diet_plan', plan_id=new_plan_id))
        except mysql.connector.Error as err:
            if conn: conn.rollback(); 
            current_app.logger.error(f"DB Error Adding Diet Plan: {err}")
            flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
            if conn: conn.rollback(); 
            current_app.logger.error(f"Unexpected Error Adding Diet Plan: {e}", exc_info=True)
            flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
        form_data = request.form.to_dict()
        form_data['target_conditions_list'] = selected_conditions_list
        form_data['is_public'] = is_public
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
            plan=form_data, meals=[], plan_types=plan_types_enum_list,
            meal_types=meal_types_enum_list, conditions=conditions_for_dropdown, errors=errors 
        )
    return render_template(
        'Doctor_Portal/DietPlans/diet_plan_form.html',
        form_action=url_for('.add_diet_plan'), form_title="Add New Diet Plan",
        plan=None, meals=[],
        plan_types=plan_types_enum_list, meal_types=meal_types_enum_list, conditions=conditions_for_dropdown
    )


@diet_plans_bp.route('/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_diet_plan(plan_id):
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

    plan_types_enum_list = get_enum_values('diet_plans', 'plan_type')
    meal_types_enum_list = get_enum_values('diet_plan_meals', 'meal_type')
    conditions_for_dropdown = get_all_conditions()

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        overall_plan_nutrients = {'calories': 0, 'protein_grams': 0.0, 'carbs_grams': 0.0, 'fat_grams': 0.0, 'fiber_grams': 0.0, 'sodium_mg': 0}
        plan_has_nutrient_data = {key: False for key in overall_plan_nutrients}

        try:
            conn = get_db_connection(); cursor = conn.cursor()
            conn.start_transaction()

            plan_name = request.form.get('plan_name', '').strip()
            plan_type_form = request.form.get('plan_type')
            description = request.form.get('description', '').strip() or None
            is_public = request.form.get('is_public') == 'on'
            selected_conditions_list = request.form.getlist('target_conditions')
            target_conditions_str = ','.join(selected_conditions_list) if selected_conditions_list else None
            
            # Plan-level direct nutrient inputs (for manual override if needed)
            plan_calories_form = validate_numeric(request.form.get('plan_calories'), "Plan Calories", errors, required=False)
            plan_protein_form = validate_numeric(request.form.get('plan_protein_grams'), "Plan Protein", errors, is_float=True, required=False)
            plan_carbs_form = validate_numeric(request.form.get('plan_carbs_grams'), "Plan Carbs", errors, is_float=True, required=False)
            plan_fat_form = validate_numeric(request.form.get('plan_fat_grams'), "Plan Fat", errors, is_float=True, required=False)
            plan_fiber_form = validate_numeric(request.form.get('plan_fiber_grams'), "Plan Fiber", errors, is_float=True, required=False)
            plan_sodium_form = validate_numeric(request.form.get('plan_sodium_mg'), "Plan Sodium", errors, required=False)

            if not plan_name: errors.append("Plan Name is required.")
            if not plan_type_form or plan_type_form not in plan_types_enum_list: errors.append("Valid Plan Type is required.")
            if errors: raise ValueError("Plan details validation failed.")

            # Update plan details - nutrients initially set from form, then recalculated
            sql_update_plan_initial = """UPDATE diet_plans SET plan_name=%s, plan_type=%s, description=%s,
                                       is_public=%s, target_conditions=%s, 
                                       calories=%s, protein_grams=%s, carbs_grams=%s, 
                                       fat_grams=%s, fiber_grams=%s, sodium_mg=%s,
                                       updated_by=%s, updated_at=CURRENT_TIMESTAMP
                                       WHERE plan_id=%s"""
            params_plan_initial = (plan_name, plan_type_form, description,
                                   is_public, target_conditions_str,
                                   plan_calories_form, plan_protein_form, plan_carbs_form, 
                                   plan_fat_form, plan_fiber_form, plan_sodium_form,
                                   current_user.id, plan_id)
            cursor.execute(sql_update_plan_initial, params_plan_initial)

            # Process Deletions
            deleted_meal_ids_str = request.form.getlist('deleted_meal_ids')
            deleted_item_ids_str = request.form.getlist('deleted_item_ids')
            deleted_meal_ids = [int(id) for id in deleted_meal_ids_str if id.isdigit()]
            deleted_item_ids = [int(id) for id in deleted_item_ids_str if id.isdigit()]

            if deleted_meal_ids:
                placeholders_meals = ','.join(['%s'] * len(deleted_meal_ids))
                cursor.execute(f"DELETE FROM diet_plan_food_items WHERE meal_id IN ({placeholders_meals})", tuple(deleted_meal_ids))
                cursor.execute(f"DELETE FROM diet_plan_meals WHERE meal_id IN ({placeholders_meals}) AND plan_id = %s", (*deleted_meal_ids, plan_id))
            if deleted_item_ids:
                placeholders_items = ','.join(['%s'] * len(deleted_item_ids))
                cursor.execute(f"DELETE FROM diet_plan_food_items WHERE item_id IN ({placeholders_items})", tuple(deleted_item_ids))

            # Process Updates (Existing Meals and Items)
            existing_meal_ids = request.form.getlist('meal_id')
            for meal_id_str in existing_meal_ids:
                if not meal_id_str.isdigit() or int(meal_id_str) in deleted_meal_ids: continue
                meal_id = int(meal_id_str)
                meal_food_items_data = []

                # Update existing items for this meal
                existing_item_ids_for_meal = request.form.getlist(f'item_id[{meal_id}]')
                for item_id_str in existing_item_ids_for_meal:
                    if not item_id_str.isdigit() or int(item_id_str) in deleted_item_ids: continue
                    item_id = int(item_id_str)
                    item_data = {
                        'food_name': request.form.get(f'item_food_name[{item_id}]', '').strip(),
                        'serving_size': request.form.get(f'item_serving_size[{item_id}]', '').strip(),
                        'notes': request.form.get(f'item_notes[{item_id}]', '').strip() or None,
                        'alternatives': request.form.get(f'item_alternatives[{item_id}]', '').strip() or None,
                        'calories': validate_numeric(request.form.get(f'item_calories[{item_id}]'), "Item Calories", errors),
                        'protein_grams': validate_numeric(request.form.get(f'item_protein[{item_id}]'), "Item Protein", errors, is_float=True),
                        'carbs_grams': validate_numeric(request.form.get(f'item_carbs[{item_id}]'), "Item Carbs", errors, is_float=True),
                        'fat_grams': validate_numeric(request.form.get(f'item_fat[{item_id}]'), "Item Fat", errors, is_float=True)
                        # diet_plan_food_items schema does not have fiber or sodium per item
                    }
                    if not item_data['food_name'] or not item_data['serving_size']:
                        errors.append(f"Food Name and Serving Size are required for item ID {item_id}.")
                        continue
                    if errors: continue # Skip if errors found in this item's nutrients

                    sql_update_item = """UPDATE diet_plan_food_items SET food_name=%s, serving_size=%s, notes=%s, alternatives=%s,
                                         calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s, updated_at=NOW()
                                         WHERE item_id=%s AND meal_id=%s"""
                    cursor.execute(sql_update_item, (
                        item_data['food_name'], item_data['serving_size'], item_data['notes'], item_data['alternatives'],
                        item_data['calories'], item_data['protein_grams'], item_data['carbs_grams'], item_data['fat_grams'],
                        item_id, meal_id
                    ))
                    meal_food_items_data.append(item_data)
                
                # Add new items for this existing meal
                meal_ref_ex = str(meal_id)
                new_item_names_ex = request.form.getlist(f'new_item_food_name[{meal_ref_ex}]')
                for k, item_name_ex in enumerate(new_item_names_ex):
                    item_name_ex = item_name_ex.strip()
                    if not item_name_ex: continue
                    item_data_ex = {
                        'food_name': item_name_ex,
                        'serving_size': (request.form.getlist(f'new_item_serving_size[{meal_ref_ex}]')[k] if k < len(request.form.getlist(f'new_item_serving_size[{meal_ref_ex}]')) else '').strip(),
                        'notes': (request.form.getlist(f'new_item_notes[{meal_ref_ex}]')[k].strip() if k < len(request.form.getlist(f'new_item_notes[{meal_ref_ex}]')) else None) or None,
                        'alternatives': (request.form.getlist(f'new_item_alternatives[{meal_ref_ex}]')[k].strip() if k < len(request.form.getlist(f'new_item_alternatives[{meal_ref_ex}]')) else None) or None,
                        'calories': validate_numeric(request.form.getlist(f'new_item_calories[{meal_ref_ex}]')[k] if k < len(request.form.getlist(f'new_item_calories[{meal_ref_ex}]')) else None, "New Item Calories", errors),
                        'protein_grams': validate_numeric(request.form.getlist(f'new_item_protein[{meal_ref_ex}]')[k] if k < len(request.form.getlist(f'new_item_protein[{meal_ref_ex}]')) else None, "New Item Protein", errors, is_float=True),
                        'carbs_grams': validate_numeric(request.form.getlist(f'new_item_carbs[{meal_ref_ex}]')[k] if k < len(request.form.getlist(f'new_item_carbs[{meal_ref_ex}]')) else None, "New Item Carbs", errors, is_float=True),
                        'fat_grams': validate_numeric(request.form.getlist(f'new_item_fat[{meal_ref_ex}]')[k] if k < len(request.form.getlist(f'new_item_fat[{meal_ref_ex}]')) else None, "New Item Fat", errors, is_float=True)
                    }
                    if not item_data_ex['serving_size']: errors.append(f"Serving Size required for new item '{item_data_ex['food_name']}'."); continue
                    if errors: continue
                    sql_insert_item_ex = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives, calories, protein_grams, carbs_grams, fat_grams)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_insert_item_ex, (meal_id, item_data_ex['food_name'], item_data_ex['serving_size'], item_data_ex['notes'], item_data_ex['alternatives'], item_data_ex['calories'], item_data_ex['protein_grams'], item_data_ex['carbs_grams'], item_data_ex['fat_grams']))
                    meal_food_items_data.append(item_data_ex)

                # Calculate and update this existing meal's nutrients
                calculated_meal_nutrients = calculate_nutrient_totals(meal_food_items_data)
                meal_name_form = request.form.get(f'meal_name[{meal_id}]', '').strip()
                meal_type_form = request.form.get(f'meal_type[{meal_id}]')
                time_of_day_str_form = request.form.get(f'meal_time[{meal_id}]')
                meal_time_obj_form = parse_time_string(time_of_day_str_form)
                meal_desc_form = request.form.get(f'meal_desc[{meal_id}]', '').strip() or None
                if not meal_name_form: errors.append(f"Meal Name required for meal ID {meal_id}.")
                if not meal_type_form or meal_type_form not in meal_types_enum_list: errors.append(f"Meal Type for '{meal_name_form}'.")
                if errors: continue

                sql_update_meal = """UPDATE diet_plan_meals SET meal_name=%s, meal_type=%s, time_of_day=%s, description=%s,
                                     calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s, fiber_grams=%s, sodium_mg=%s,
                                     updated_at=NOW() WHERE meal_id=%s AND plan_id=%s"""
                cursor.execute(sql_update_meal, (
                    meal_name_form, meal_type_form, meal_time_obj_form, meal_desc_form,
                    calculated_meal_nutrients['calories'], calculated_meal_nutrients['protein_grams'],
                    calculated_meal_nutrients['carbs_grams'], calculated_meal_nutrients['fat_grams'],
                    calculated_meal_nutrients['fiber_grams'], calculated_meal_nutrients['sodium_mg'],
                    meal_id, plan_id))
                
                for key, value in calculated_meal_nutrients.items():
                    if value is not None:
                        if isinstance(overall_plan_nutrients[key], (int, float)): overall_plan_nutrients[key] += value
                        elif overall_plan_nutrients[key] is None: overall_plan_nutrients[key] = value
                        plan_has_nutrient_data[key] = True
            
            # Process New Meals
            new_meal_names = request.form.getlist('new_meal_name')
            for i, new_meal_name_form in enumerate(new_meal_names):
                new_meal_name_form = new_meal_name_form.strip()
                if not new_meal_name_form: continue
                new_meal_food_items_data = []
                new_type_form = request.form.getlist('new_meal_type')[i] if i < len(request.form.getlist('new_meal_type')) else None
                new_time_str_form = request.form.getlist('new_meal_time')[i] if i < len(request.form.getlist('new_meal_time')) else None
                new_time_obj_form = parse_time_string(new_time_str_form)
                new_desc_form = (request.form.getlist('new_meal_desc')[i].strip() if i < len(request.form.getlist('new_meal_desc')) else None) or None
                if not new_type_form or new_type_form not in meal_types_enum_list: errors.append(f"Meal Type for new meal '{new_meal_name_form}'."); continue
                
                sql_insert_meal = """INSERT INTO diet_plan_meals (plan_id, meal_name, meal_type, time_of_day, description) 
                                     VALUES (%s, %s, %s, %s, %s)""" # Nutrients inserted later
                cursor.execute(sql_insert_meal, (plan_id, new_meal_name_form, new_type_form, new_time_obj_form, new_desc_form))
                new_meal_id = cursor.lastrowid

                meal_ref_new = f'new_{i}'
                new_item_names_for_new_meal = request.form.getlist(f'new_item_food_name[{meal_ref_new}]')
                for j, item_name_new_meal in enumerate(new_item_names_for_new_meal):
                    item_name_new_meal = item_name_new_meal.strip()
                    if not item_name_new_meal: continue
                    item_data_new_meal = {
                        'food_name': item_name_new_meal,
                        'serving_size': (request.form.getlist(f'new_item_serving_size[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_serving_size[{meal_ref_new}]')) else '').strip(),
                        'notes': (request.form.getlist(f'new_item_notes[{meal_ref_new}]')[j].strip() if j < len(request.form.getlist(f'new_item_notes[{meal_ref_new}]')) else None) or None,
                        'alternatives': (request.form.getlist(f'new_item_alternatives[{meal_ref_new}]')[j].strip() if j < len(request.form.getlist(f'new_item_alternatives[{meal_ref_new}]')) else None) or None,
                        'calories': validate_numeric(request.form.getlist(f'new_item_calories[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_calories[{meal_ref_new}]')) else None, "New Item Calories", errors),
                        'protein_grams': validate_numeric(request.form.getlist(f'new_item_protein[{meal_ref_new}]')[j] if j < len(request.form.getlist(f'new_item_protein[{meal_ref_new}]')) else None, "New Item Protein", errors, is_float=True),
                        'carbs_grams': validate_numeric(request.form.getlist(f'new_item_carbs[{meal_ref_new}]')[j] if k < len(request.form.getlist(f'new_item_carbs[{meal_ref_new}]')) else None, "New Item Carbs", errors, is_float=True),
                        'fat_grams': validate_numeric(request.form.getlist(f'new_item_fat[{meal_ref_new}]')[j] if k < len(request.form.getlist(f'new_item_fat[{meal_ref_new}]')) else None, "New Item Fat", errors, is_float=True)
                    }
                    if not item_data_new_meal['serving_size']: errors.append(f"Serving Size required for new item '{item_data_new_meal['food_name']}'."); continue
                    if errors: continue
                    sql_insert_item = """INSERT INTO diet_plan_food_items (meal_id, food_name, serving_size, notes, alternatives, calories, protein_grams, carbs_grams, fat_grams)
                                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                    cursor.execute(sql_insert_item, (new_meal_id, item_data_new_meal['food_name'], item_data_new_meal['serving_size'], item_data_new_meal['notes'], item_data_new_meal['alternatives'], item_data_new_meal['calories'], item_data_new_meal['protein_grams'], item_data_new_meal['carbs_grams'], item_data_new_meal['fat_grams']))
                    new_meal_food_items_data.append(item_data_new_meal)
                
                calculated_new_meal_nutrients = calculate_nutrient_totals(new_meal_food_items_data)
                sql_update_new_meal_nutrients = """UPDATE diet_plan_meals SET 
                                                calories=%s, protein_grams=%s, carbs_grams=%s, fat_grams=%s, 
                                                fiber_grams=%s, sodium_mg=%s, updated_at=NOW() 
                                                WHERE meal_id=%s"""
                cursor.execute(sql_update_new_meal_nutrients, (
                    calculated_new_meal_nutrients['calories'], calculated_new_meal_nutrients['protein_grams'],
                    calculated_new_meal_nutrients['carbs_grams'], calculated_new_meal_nutrients['fat_grams'],
                    calculated_new_meal_nutrients['fiber_grams'], calculated_new_meal_nutrients['sodium_mg'],
                    new_meal_id))
                for key, value in calculated_new_meal_nutrients.items():
                    if value is not None:
                        if isinstance(overall_plan_nutrients[key], (int, float)): overall_plan_nutrients[key] += value
                        elif overall_plan_nutrients[key] is None: overall_plan_nutrients[key] = value
                        plan_has_nutrient_data[key] = True
            
            # Final update for plan nutrients if not manually entered or if calculation is preferred
            if not (plan_calories_form or plan_protein_form or plan_carbs_form or plan_fat_form or plan_fiber_form or plan_sodium_form):
                # If no plan-level nutrients were manually entered, use calculated totals
                final_plan_nutrients_to_save = {}
                for key in overall_plan_nutrients.keys():
                    final_plan_nutrients_to_save[key] = overall_plan_nutrients[key] if plan_has_nutrient_data[key] else None
                    if key in ['protein_grams', 'carbs_grams', 'fat_grams', 'fiber_grams'] and final_plan_nutrients_to_save[key] is not None:
                        final_plan_nutrients_to_save[key] = round(final_plan_nutrients_to_save[key], 2)

                sql_update_plan_calculated_nutrients = """UPDATE diet_plans SET 
                                                    calories = %s, protein_grams = %s, carbs_grams = %s, 
                                                    fat_grams = %s, fiber_grams = %s, sodium_mg = %s,
                                                    updated_at = CURRENT_TIMESTAMP 
                                                    WHERE plan_id = %s"""
                cursor.execute(sql_update_plan_calculated_nutrients, (
                    final_plan_nutrients_to_save['calories'], final_plan_nutrients_to_save['protein_grams'],
                    final_plan_nutrients_to_save['carbs_grams'], final_plan_nutrients_to_save['fat_grams'],
                    final_plan_nutrients_to_save['fiber_grams'], final_plan_nutrients_to_save['sodium_mg'],
                    plan_id
                ))


            if errors:
                 unique_errors = list(dict.fromkeys(errors)) # Remove duplicate error messages
                 raise ValueError("Validation errors occurred: " + "; ".join(unique_errors))

            conn.commit()
            flash(f"Diet plan '{plan_name}' updated successfully.", "success")
            return redirect(url_for('.view_diet_plan', plan_id=plan_id))

        except ValueError as ve:
            if conn and conn.is_connected(): conn.rollback()
            unique_errors = list(dict.fromkeys(errors)) if 'errors' in locals() and errors else []
            for err_msg in unique_errors: flash(err_msg, 'danger')
            if not unique_errors and str(ve) and "Validation errors occurred" not in str(ve): flash(str(ve), 'danger')
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
        # Repopulate form with a mix of submitted data and existing data to show correct state after error
        submitted_plan_data = {
            'plan_name': request.form.get('plan_name', current_details['plan'].get('plan_name', '')),
            'plan_type': request.form.get('plan_type', current_details['plan'].get('plan_type', '')),
            'description': request.form.get('description', current_details['plan'].get('description', '')),
            'is_public': request.form.get('is_public') == 'on',
            'target_conditions_list': request.form.getlist('target_conditions'),
            'plan_id': plan_id,
            'calories': request.form.get('plan_calories', current_details['plan'].get('calories')),
            'protein_grams': request.form.get('plan_protein_grams', current_details['plan'].get('protein_grams')),
            'carbs_grams': request.form.get('plan_carbs_grams', current_details['plan'].get('carbs_grams')),
            'fat_grams': request.form.get('plan_fat_grams', current_details['plan'].get('fat_grams')),
            'fiber_grams': request.form.get('plan_fiber_grams', current_details['plan'].get('fiber_grams')),
            'sodium_mg': request.form.get('plan_sodium_mg', current_details['plan'].get('sodium_mg')),
        }
        
        return render_template(
            'Doctor_Portal/DietPlans/diet_plan_form.html',
            form_action=url_for('.edit_diet_plan', plan_id=plan_id),
            form_title=f"Edit Diet Plan: {submitted_plan_data.get('plan_name', '')}",
            plan=submitted_plan_data, 
            meals=current_details.get('meals', []), # Show meals from DB after failed attempt
            plan_types=plan_types_enum_list,
            meal_types=meal_types_enum_list, 
            conditions=conditions_for_dropdown,
            errors=list(dict.fromkeys(errors)) if 'errors' in locals() and errors else []
        )

    # GET Request
    details = get_diet_plan_details(plan_id)
    if not details or not details['plan']: # Added check for plan existence within details
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
        plan_types=plan_types_enum_list, meal_types=meal_types_enum_list, 
        conditions=conditions_for_dropdown
    )


@diet_plans_bp.route('/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_diet_plan(plan_id):
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
        return redirect(url_for('.view_diet_plan', plan_id=plan_id) if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False) else url_for('doctor_main.dashboard'))

    conn = None; cursor = None; plan_name = plan_check_info['plan_name']
    try:
        conn = get_db_connection();
        if not conn: raise ConnectionError("DB Connection failed")
        cursor = conn.cursor()
        conn.start_transaction()
        cursor.execute("SELECT 1 FROM user_diet_plans WHERE plan_id = %s AND active = TRUE LIMIT 1", (plan_id,))
        if cursor.fetchone():
             conn.rollback()
             flash(f"Cannot delete plan '{plan_name}'. It is actively assigned to one or more patients.", "warning")
             return redirect(url_for('.view_diet_plan', plan_id=plan_id))
        cursor.execute("DELETE FROM diet_plan_food_items WHERE meal_id IN (SELECT meal_id FROM diet_plan_meals WHERE plan_id = %s)", (plan_id,))
        cursor.execute("DELETE FROM diet_plan_meals WHERE plan_id = %s", (plan_id,))
        cursor.execute("DELETE FROM diet_plans WHERE plan_id = %s", (plan_id,))
        if cursor.rowcount == 0:
             conn.rollback() 
             flash(f"Could not delete plan '{plan_name}'. It might have historical assignments or related data preventing deletion.", "danger")
             current_app.logger.warning(f"Deletion attempt failed for plan_id {plan_id} (rowcount 0), possibly due to FK constraints.")
        else:
            conn.commit()
            flash(f"Diet plan '{plan_name}' deleted successfully.", "success")
    except mysql.connector.Error as err:
        if conn and conn.is_connected(): conn.rollback();
        current_app.logger.error(f"DB Error Deleting Diet Plan {plan_id}: {err}")
        if err.errno == 1451: 
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


@diet_plans_bp.route('/assign', methods=['GET', 'POST'])
@login_required
def assign_diet_plan():
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to assign diet plans.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
             return redirect(url_for('.list_assignments'))
        else: return redirect(url_for('doctor_main.dashboard'))
    patients = get_all_active_patients()
    diet_plans_list = get_all_selectable_diet_plans(current_user.id) 
    form_data_repop = {} 
    if request.method == 'POST':
        form_data_repop = request.form.to_dict() 
        patient_user_id = request.form.get('patient_user_id', type=int)
        plan_id = request.form.get('plan_id', type=int)
        start_date_str = request.form.get('start_date'); end_date_str = request.form.get('end_date')
        notes = request.form.get('notes', '').strip() or None; errors = []
        if not patient_user_id: errors.append("Patient selection is required.")
        if not plan_id: errors.append("Diet Plan selection is required.")
        start_date_obj = None; end_date_obj = None # Renamed
        try:
            if start_date_str: start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            else: errors.append("Start Date is required.")
        except ValueError: errors.append("Invalid Start Date format (YYYY-MM-DD).")
        try:
            if end_date_str: end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError: errors.append("Invalid End Date format (YYYY-MM-DD).")
        if start_date_obj and end_date_obj and end_date_obj < start_date_obj: # Use renamed vars
            errors.append("End Date cannot be before Start Date.")
        if errors:
            for err in errors: flash(err, 'danger')
            return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans_list, form_data=form_data_repop)
        conn = None; cursor = None
        try:
            conn = get_db_connection(); cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM user_diet_plans WHERE user_id = %s AND active = TRUE LIMIT 1", (patient_user_id,))
            if cursor.fetchone():
                 flash(f"Patient already has an active diet plan assigned. Deactivate the existing one first or edit its end date.", "warning")
                 return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans_list, form_data=form_data_repop)
            sql = """INSERT INTO user_diet_plans (user_id, plan_id, assigned_by, start_date, end_date, notes, active, created_at, updated_at)
                     VALUES (%s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())"""
            params = (patient_user_id, plan_id, current_user.id, start_date_obj, end_date_obj, notes) # Use renamed vars
            cursor.execute(sql, params)
            conn.commit()
            flash("Diet plan assigned successfully.", "success")
            return redirect(url_for('.list_assignments'))
        except mysql.connector.Error as err:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"DB Error Assigning Diet Plan: {err}")
             if err.errno == 1062: flash("Failed to assign plan. A similar active assignment might exist.", "warning")
             elif err.errno == 1452: flash("Invalid patient or plan selected. Please check your selections.", "danger") 
             else: flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
             if conn and conn.is_connected(): conn.rollback()
             current_app.logger.error(f"Error Assigning Diet Plan: {e}", exc_info=True)
             flash("An unexpected error occurred during assignment.", "danger")
        finally:
             if cursor: cursor.close()
             if conn and conn.is_connected(): conn.close()
        return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans_list, form_data=form_data_repop)
    return render_template('Doctor_Portal/DietPlans/assign_plan_form.html', patients=patients, diet_plans=diet_plans_list, form_data=None)

@diet_plans_bp.route('/assignments', methods=['GET'])
@login_required
def list_assignments():
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        flash("Access denied. Doctor or Dietitian role required to view assignments.", "danger")
        return redirect(url_for('doctor_main.dashboard'))
    conn = None; cursor = None; assignments = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT
                udp.user_diet_plan_id, udp.start_date, udp.end_date, udp.active, udp.notes,
                p_user.user_id as patient_user_id, p_user.first_name as patient_first_name, p_user.last_name as patient_last_name,
                dp.plan_id, dp.plan_name, dp.calories as plan_calories, 
                a_user.user_id as assigner_user_id, a_user.first_name as assigner_first_name, a_user.last_name as assigner_last_name
            FROM user_diet_plans udp
            JOIN users p_user ON udp.user_id = p_user.user_id
            JOIN diet_plans dp ON udp.plan_id = dp.plan_id
            LEFT JOIN users a_user ON udp.assigned_by = a_user.user_id
            ORDER BY udp.active DESC, udp.start_date DESC, p_user.last_name
            LIMIT 200 
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
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Registered Dietitian role required to deactivate assignments.", "danger")
        if check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
            return redirect(url_for('.list_assignments'))
        else:
            return redirect(url_for('doctor_main.dashboard'))
    conn = None; cursor = None;
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("UPDATE user_diet_plans SET active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE user_diet_plan_id = %s", (assignment_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Assignment deactivated successfully.", "success")
        else:
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
    is_patient_self = current_user.id == patient_user_id and current_user.user_type == 'patient'
    is_provider_authorized = is_doctor_authorized_for_patient(current_user, patient_user_id)

    if not (is_patient_self or is_provider_authorized):
        flash("Access denied to view this nutrition progress.", "danger")
        return redirect(url_for('doctor_main.dashboard'))

    conn = None; cursor = None; patient_info = None; logs = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, first_name, last_name FROM users WHERE user_id = %s AND user_type = 'patient'", (patient_user_id,))
        patient_info = cursor.fetchone()
        if not patient_info:
             flash("Patient not found.", "warning")
             return redirect(url_for('.list_assignments'))
        cursor.execute("SELECT * FROM user_nutrition_logs WHERE user_id = %s ORDER BY log_date DESC LIMIT 100", (patient_user_id,))
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

    can_add_log = is_patient_self 
    from datetime import datetime as dt 
    now = dt.now()

    return render_template('Doctor_Portal/DietPlans/nutrition_progress.html',
                           patient=patient_info,
                           logs=logs,
                           can_add_log=can_add_log,
                           now=now 
                           )