# routes/Doctor_Portal/food_item_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app
)
from flask_login import login_required, current_user
from db import get_db_connection
import math
import decimal # Import Decimal for handling potential DB types
import datetime # <--- ADD THIS IMPORT

# Assuming utils.py is in the same directory or adjust import path
try:
    from .utils import check_doctor_or_dietitian_authorization
except ImportError:
    # Fallback if utils is one level up (adjust as needed for your structure)
    from ..utils import check_doctor_or_dietitian_authorization


# --- Blueprint Definition ---
food_items_bp = Blueprint(
    'food_items',              # Blueprint name (used in url_for)
    __name__,
    url_prefix='/doctor/food-items', # Base URL for these routes
    template_folder='../../templates' # Path to templates relative to this file
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE = 15 # How many items per page in the list view
VALID_SORT_COLUMNS = { # Allowed columns for sorting the list
    'name': 'fi.item_name', 'calories': 'fi.calories', 'protein': 'fi.protein_grams',
    'carbs': 'fi.carbs_grams', 'fat': 'fi.fat_grams', 'id': 'fi.food_item_id',
    'updated': 'fi.updated_at'
}
DEFAULT_SORT_COLUMN = 'name'
DEFAULT_SORT_DIRECTION = 'ASC'

# --- Helper Function for Numeric Validation ---
def validate_numeric_food_item(value, field_name, errors, allow_negative=False, is_float=False, required=False):
    """Helper for numeric validation specific to food items (handles None/empty)."""
    str_value = str(value).strip() if value is not None else ''

    if not str_value:
        if required:
            errors.append(f"{field_name} is required.")
        return None # Return None if empty and not required

    try:
        num = float(str_value) if is_float else int(str_value)
        if not allow_negative and num < 0:
            errors.append(f"{field_name} cannot be negative.")
            return None
        return num
    except (ValueError, TypeError):
        errors.append(f"{field_name} must be a valid number.")
        return None

# --- Data Fetching Functions ---

def get_paginated_food_items(page=1, per_page=ITEMS_PER_PAGE, search_term=None, sort_by=DEFAULT_SORT_COLUMN, sort_dir=DEFAULT_SORT_DIRECTION):
    """Fetches paginated food items from the library."""
    conn = None
    cursor = None
    result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page

    # Validate sort parameters
    sort_column_sql = VALID_SORT_COLUMNS.get(sort_by, VALID_SORT_COLUMNS[DEFAULT_SORT_COLUMN])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Database connection failed")
        cursor = conn.cursor(dictionary=True)

        sql_select = "SELECT SQL_CALC_FOUND_ROWS fi.*"
        sql_from = " FROM food_item_library fi "
        # Only show active items in the main list
        sql_where = " WHERE fi.is_active = TRUE "
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            # Search name and general notes
            sql_where += " AND (fi.item_name LIKE %s OR fi.notes LIKE %s)"
            params.extend([search_like, search_like])

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()

        # Get total count matching the WHERE clause (ignoring LIMIT)
        cursor.execute("SELECT FOUND_ROWS() as total")
        total_row = cursor.fetchone()
        result['total'] = total_row['total'] if total_row else 0

    except (mysql.connector.Error, ConnectionError) as err:
        current_app.logger.error(f"Error fetching paginated food items: {err}")
        # Optionally flash a message here, though often handled in the route
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return result

def get_food_item_details(item_id):
    """Fetches details for a single food item from the library."""
    conn = None
    cursor = None
    item = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch even if inactive, maybe show a status on the edit form?
        # Or restrict edit/view of inactive: AND is_active = TRUE
        cursor.execute("SELECT * FROM food_item_library WHERE food_item_id = %s", (item_id,))
        item = cursor.fetchone()
    except Exception as e:
        current_app.logger.error(f"Error fetching food item details for ID {item_id}: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
    return item

# --- Routes ---

@food_items_bp.route('/', methods=['GET'])
@login_required
def list_food_items():
    """Lists food items in the library - Viewable by Doctors/Dietitians."""
    # Authorization Check: Allow Doctors and Dietitians to view the library
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
         flash("Access denied. Doctor or Dietitian role required to view food library.", "danger")
         # Redirect to a safe place, e.g., dashboard
         return redirect(url_for('doctor_main.dashboard'))

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION).upper()

    # Validate sort parameters received from request args
    if sort_by not in VALID_SORT_COLUMNS:
        sort_by = DEFAULT_SORT_COLUMN
    if sort_dir not in ['ASC', 'DESC']:
        sort_dir = DEFAULT_SORT_DIRECTION

    # Fetch data using the helper function
    result = get_paginated_food_items(page, ITEMS_PER_PAGE, search_term, sort_by, sort_dir)
    items = result['items']
    total_items = result['total']
    total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if ITEMS_PER_PAGE > 0 else 0

    # Check if the current user can manage items (add/edit/delete) - Restricted to Dietitians
    can_manage_food_items = check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True)

    return render_template(
        'Doctor_Portal/FoodItems/food_item_list.html', # Path to the list template
        items=items,
        search_term=search_term,
        current_page=page,
        total_pages=total_pages,
        sort_by=sort_by,
        sort_dir=sort_dir,
        valid_sort_columns=VALID_SORT_COLUMNS,
        can_manage_food_items=can_manage_food_items,
        request_args=request.args # *** ADD THIS LINE *** Pass request args
    )

@food_items_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_food_item():
    """Handles adding a new food item to the library - Restricted to Dietitians."""
    # Authorization Check: Only Dietitians can add
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Dietitian role required to add food items to the library.", "danger")
        # Redirect back to the list if they lack permission
        return redirect(url_for('.list_food_items'))

    if request.method == 'POST':
        conn = None
        cursor = None
        errors = []
        # Capture form data for repopulation
        form_data = request.form.to_dict()

        try:
            item_name = request.form.get('item_name', '').strip()
            serving_size = request.form.get('serving_size', '').strip()
            notes = request.form.get('notes', '').strip() or None

            # --- Validation ---
            if not item_name: errors.append("Item Name is required.")
            if not serving_size: errors.append("Serving Size is required.")

            # Use the helper for numeric fields (allow empty/null)
            calories = validate_numeric_food_item(request.form.get('calories'), "Calories", errors)
            protein = validate_numeric_food_item(request.form.get('protein_grams'), "Protein (g)", errors, is_float=True)
            carbs = validate_numeric_food_item(request.form.get('carbs_grams'), "Carbs (g)", errors, is_float=True)
            fat = validate_numeric_food_item(request.form.get('fat_grams'), "Fat (g)", errors, is_float=True)
            fiber = validate_numeric_food_item(request.form.get('fiber_grams'), "Fiber (g)", errors, is_float=True)
            sodium = validate_numeric_food_item(request.form.get('sodium_mg'), "Sodium (mg)", errors)

            # Check for unique name constraint before inserting
            if not errors:
                 conn_check = get_db_connection(); cursor_check = conn_check.cursor()
                 cursor_check.execute("SELECT 1 FROM food_item_library WHERE item_name = %s AND is_active = TRUE", (item_name,))
                 if cursor_check.fetchone():
                     errors.append(f"A food item named '{item_name}' already exists in the active library.")
                 cursor_check.close(); conn_check.close()

            if errors:
                raise ValueError("Validation failed")
            # --- End Validation ---

            conn = get_db_connection()
            cursor = conn.cursor()
            sql = """INSERT INTO food_item_library
                     (item_name, serving_size, calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, notes, creator_id, is_active)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)""" # Default to active
            params = (item_name, serving_size, calories, protein, carbs, fat, fiber, sodium, notes, current_user.id)
            cursor.execute(sql, params)
            conn.commit()
            flash(f"Food item '{item_name}' added successfully.", "success")
            return redirect(url_for('.list_food_items'))

        except ValueError: # Catch validation errors
            for err in errors: flash(err, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB Error Adding Food Item: {err}")
            if err.errno == 1062: # Duplicate entry based on DB constraint (e.g., UNIQUE index)
                flash(f"Error: A food item with the name '{item_name}' might already exist (possibly inactive).", "danger")
            else:
                flash(f"Database error occurred: {err.msg}", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Unexpected Error Adding Food Item: {e}", exc_info=True)
            flash("An unexpected error occurred while adding the food item.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error, passing back submitted data and errors
        return render_template(
            'Doctor_Portal/FoodItems/food_item_form.html',
            form_action=url_for('.add_food_item'),
            form_title="Add New Food Item",
            item=form_data, # Pass submitted data back
            errors=errors
        )

    # GET request: Render empty form
    return render_template(
        'Doctor_Portal/FoodItems/food_item_form.html',
        form_action=url_for('.add_food_item'),
        form_title="Add New Food Item",
        item=None, # No existing item data for add form
        errors=[]
    )

@food_items_bp.route('/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_food_item(item_id):
    """Handles editing an existing food item - Restricted to Dietitians."""
    # Authorization Check: Only Dietitians can edit
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Dietitian role required to edit food items.", "danger")
        return redirect(url_for('.list_food_items'))

    conn = None
    cursor = None
    item = get_food_item_details(item_id) # Fetch existing item details for GET and check

    if not item:
        flash("Food item not found.", "warning")
        return redirect(url_for('.list_food_items'))

    if request.method == 'POST':
        errors = []
        form_data = request.form.to_dict() # Capture form data

        try:
            item_name = request.form.get('item_name', '').strip()
            serving_size = request.form.get('serving_size', '').strip()
            notes = request.form.get('notes', '').strip() or None
            # Optionally handle is_active status if you add a checkbox to the form
            is_active = request.form.get('is_active') == 'on' if 'is_active' in request.form else item.get('is_active', True)


            # --- Validation ---
            if not item_name: errors.append("Item Name is required.")
            if not serving_size: errors.append("Serving Size is required.")

            calories = validate_numeric_food_item(request.form.get('calories'), "Calories", errors)
            protein = validate_numeric_food_item(request.form.get('protein_grams'), "Protein (g)", errors, is_float=True)
            carbs = validate_numeric_food_item(request.form.get('carbs_grams'), "Carbs (g)", errors, is_float=True)
            fat = validate_numeric_food_item(request.form.get('fat_grams'), "Fat (g)", errors, is_float=True)
            fiber = validate_numeric_food_item(request.form.get('fiber_grams'), "Fiber (g)", errors, is_float=True)
            sodium = validate_numeric_food_item(request.form.get('sodium_mg'), "Sodium (mg)", errors)

             # Check for unique name constraint (excluding the current item being edited)
            if not errors and item_name != item.get('item_name'): # Only check if name changed
                 conn_check = get_db_connection(); cursor_check = conn_check.cursor()
                 cursor_check.execute("SELECT 1 FROM food_item_library WHERE item_name = %s AND food_item_id != %s AND is_active = TRUE", (item_name, item_id))
                 if cursor_check.fetchone():
                     errors.append(f"Another active food item named '{item_name}' already exists.")
                 cursor_check.close(); conn_check.close()

            if errors:
                raise ValueError("Validation failed")
            # --- End Validation ---

            conn = get_db_connection()
            cursor = conn.cursor()
            sql = """UPDATE food_item_library SET
                        item_name=%s, serving_size=%s, calories=%s, protein_grams=%s, carbs_grams=%s,
                        fat_grams=%s, fiber_grams=%s, sodium_mg=%s, notes=%s, is_active=%s,
                        updated_at=CURRENT_TIMESTAMP
                     WHERE food_item_id=%s"""
            params = (item_name, serving_size, calories, protein, carbs, fat, fiber, sodium, notes, is_active, item_id)
            cursor.execute(sql, params)

            if cursor.rowcount == 0:
                 # This might mean the item was deleted between GET/POST or no change was made
                 current_app.logger.warning(f"Food item edit for ID {item_id} affected 0 rows.")
                 # Don't necessarily flash error, maybe no change was intended

            conn.commit()
            flash(f"Food item '{item_name}' updated successfully.", "success")
            return redirect(url_for('.list_food_items')) # Redirect to list after successful edit

        except ValueError:
            for err in errors: flash(err, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB Error Editing Food Item {item_id}: {err}")
            if err.errno == 1062:
                flash(f"Error: A food item with the name '{item_name}' might already exist.", "danger")
            else:
                flash(f"Database error: {err.msg}", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Unexpected Error Editing Food Item {item_id}: {e}", exc_info=True)
            flash("An unexpected error occurred while updating the food item.", "danger")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

        # Re-render form on error, using submitted data merged with original item ID
        # Ensure item ID is preserved for the form action URL
        form_data['food_item_id'] = item_id
        form_data['is_active'] = is_active # Preserve checkbox state
        return render_template(
            'Doctor_Portal/FoodItems/food_item_form.html',
            form_action=url_for('.edit_food_item', item_id=item_id),
            form_title=f"Edit Food Item: {form_data.get('item_name', item.get('item_name', ''))}",
            item=form_data, # Pass submitted data back
            errors=errors
        )

    # GET request: Render form with existing item data
    return render_template(
        'Doctor_Portal/FoodItems/food_item_form.html',
        form_action=url_for('.edit_food_item', item_id=item_id),
        form_title=f"Edit Food Item: {item['item_name']}",
        item=item, # Pass fetched item data
        errors=[]
    )

@food_items_bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_food_item(item_id):
    """
    Soft deletes (deactivates) a food item from the library.
    Restricted to Dietitians.
    """
    # Authorization Check: Only Dietitians can delete/deactivate
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=True):
        flash("Access denied. Dietitian role required to deactivate food items.", "danger")
        return redirect(url_for('.list_food_items'))

    conn = None
    cursor = None
    item_name = ""

    try:
        # First, get the item name for the flash message
        conn_check = get_db_connection()
        cursor_check = conn_check.cursor(dictionary=True)
        cursor_check.execute("SELECT item_name FROM food_item_library WHERE food_item_id = %s", (item_id,))
        item = cursor_check.fetchone()
        if not item:
            flash("Food item not found.", "warning")
            return redirect(url_for('.list_food_items'))
        item_name = item['item_name']
        cursor_check.close()
        conn_check.close()

        # Proceed with deactivation
        conn = get_db_connection()
        cursor = conn.cursor()

        # Soft delete: Set is_active to FALSE
        cursor.execute("UPDATE food_item_library SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE food_item_id = %s", (item_id,))
        # For Hard delete (use with caution):
        # cursor.execute("DELETE FROM food_item_library WHERE food_item_id = %s", (item_id,))

        conn.commit()

        if cursor.rowcount > 0:
            flash(f"Food item '{item_name}' deactivated successfully.", "success")
        else:
            # Should not happen if fetch above succeeded, but check anyway
            flash(f"Could not deactivate food item '{item_name}'. It might already be inactive.", "warning")

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB Error Deactivating Food Item {item_id}: {err}")
        # If using hard delete, FK constraint error (1451) might occur if referenced
        flash(f"Database error occurred: {err.msg}", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected Error Deactivating Food Item {item_id}: {e}", exc_info=True)
        flash(f"An unexpected error occurred while deactivating '{item_name}'.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.list_food_items'))


# --- AJAX Search Endpoint ---
@food_items_bp.route('/search', methods=['GET'])
@login_required
def search_food_items_json():
    """
    Provides JSON search results for the food item library.
    Used via AJAX by the diet plan form.
    Accessible by logged-in Doctors/Dietitians.
    """
    # Authorization Check: Ensure user is a doctor or dietitian
    if not check_doctor_or_dietitian_authorization(current_user, require_dietitian_for_edit=False):
        # Return JSON error for AJAX request
        return jsonify({"error": "Access Denied. Doctor or Dietitian role required."}), 403

    search_query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int) # Limit results

    # Basic validation for search query length
    if not search_query or len(search_query) < 2:
        return jsonify([]) # Return empty list if query is too short or missing

    conn = None
    cursor = None
    items = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        search_like = f"%{search_query}%"
        search_prefix_like = f"{search_query}%" # For prioritizing prefix matches

        # Search active items, prioritizing name matches starting with the query
        query = """
            SELECT
                food_item_id, item_name, serving_size, calories,
                protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, notes
            FROM food_item_library
            WHERE is_active = TRUE AND (item_name LIKE %s OR notes LIKE %s)
            ORDER BY
                CASE WHEN item_name LIKE %s THEN 0 ELSE 1 END,  -- Prioritize prefix matches
                item_name                                       -- Then sort alphabetically
            LIMIT %s
        """
        cursor.execute(query, (search_like, search_like, search_prefix_like, limit))
        items_raw = cursor.fetchall()

        # Convert Decimal to float/string for JSON serialization if necessary
        items = []
        for item_raw in items_raw:
            item_processed = {}
            for key, value in item_raw.items():
                if isinstance(value, decimal.Decimal):
                    # Convert Decimal to float (suitable for most JS)
                    item_processed[key] = float(value)
                    # Or format as string if precise decimal places are critical:
                    # item_processed[key] = "{:.2f}".format(value)
                elif isinstance(value, (datetime.date, datetime.datetime)):
                     # Dates/Timestamps usually not needed for search results, but handle if they are
                     item_processed[key] = value.isoformat()
                else:
                    item_processed[key] = value
            items.append(item_processed)


    except mysql.connector.Error as db_err:
         current_app.logger.error(f"Database error searching food items library (JSON): {db_err}")
         return jsonify({"error": "Database search failed"}), 500
    except Exception as e:
        current_app.logger.error(f"Error searching food items library (JSON): {e}", exc_info=True)
        # Return a generic error for unexpected issues
        return jsonify({"error": "An unexpected error occurred during search"}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return jsonify(items) # Return the list of found items as JSON