# admin_management.py
# Adapted for the new schema structure BUT reverts to PLAIN TEXT PASSWORDS.
# WARNING: THIS VERSION STORES PASSWORDS IN PLAIN TEXT IN THE 'password' COLUMN.
# THIS IS HIGHLY INSECURE AND NOT RECOMMENDED FOR PRODUCTION ENVIRONMENTS.
# Relies on explicit commit/rollback. Assumes db connection has autocommit=False.
# Also relies on the database trigger 'after_users_insert_professional' for subtype record creation.
#
# ADDED FEATURES:
#   * Suspend/Deactivate users via account_status in Edit Admin.
#   * Password Reset is handled via the existing Edit Admin password fields.
#   * Role Definition management (List, Add, Edit, Delete Roles).

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
# Removed: from werkzeug.security import generate_password
from db import get_db_connection
from math import ceil
import mysql.connector # For specific error handling
import re # Import regular expressions for parsing

admin_management = Blueprint('admin_management', __name__)

# --- Constants ---
PER_PAGE = 10
# Allowed sort columns remain the same as they map to users/admins tables
ALLOWED_SORT_COLUMNS = {'first_name', 'last_name', 'email', 'admin_level', 'account_status'} # Added account_status
# Default/fallback admin levels matching the new schema
DEFAULT_ADMIN_LEVELS = ['regular', 'super']
# Default/fallback account statuses matching the new schema
DEFAULT_ACCOUNT_STATUSES = ['active', 'inactive', 'suspended', 'pending']


# --- Helper Functions ---

def get_enum_values(table_name, column_name):
    """Fetches possible ENUM values for a given table and column."""
    connection = None
    cursor = None
    enum_values = []
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for ENUM fetch")
        cursor = connection.cursor()
        db_name = connection.database
        if not db_name:
            db_name = current_app.config.get('MYSQL_DB')
        if not db_name:
            current_app.logger.warning("Could not determine database name to fetch ENUMs.")
            # Return defaults based on common columns if name unknown
            if table_name == 'admins' and column_name == 'admin_level': return DEFAULT_ADMIN_LEVELS
            if table_name == 'users' and column_name == 'account_status': return DEFAULT_ACCOUNT_STATUSES
            return []

        cursor.execute("""
            SELECT COLUMN_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
        """, (db_name, table_name, column_name))
        result = cursor.fetchone()

        if result and result[0]:
            # Improved parsing for ENUM('val1','val2',...)
            enum_def = result[0]
            if enum_def.lower().startswith("enum("):
                # Extract content between parentheses and split by comma
                content = enum_def[5:-1] # Remove "enum(" and ")"
                # Split by comma, remove surrounding quotes (single or double)
                enum_values = [val.strip().strip("'").strip('"') for val in content.split(',')]
            else:
                 current_app.logger.warning(f"Could not parse ENUM string: {result[0]}")
        else:
            current_app.logger.warning(f"Could not find ENUM definition for {table_name}.{column_name}")

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching ENUM values for {table_name}.{column_name}: {db_err}")
        enum_values = [] # Ensure empty list on error
    except Exception as e:
        current_app.logger.error(f"General error fetching ENUM values for {table_name}.{column_name}: {e}")
        enum_values = []
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Use defaults if fetching failed for known columns
    if not enum_values:
        if table_name == 'admins' and column_name == 'admin_level':
            current_app.logger.warning("ENUM fetch failed for admin_level, using defaults.")
            return DEFAULT_ADMIN_LEVELS
        if table_name == 'users' and column_name == 'account_status':
            current_app.logger.warning("ENUM fetch failed for account_status, using defaults.")
            return DEFAULT_ACCOUNT_STATUSES
    return enum_values

def get_admin_or_404(admin_id):
    """Fetches admin details (user + admin level) or returns None."""
    connection = None
    cursor = None
    admin = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in get_admin_or_404")
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone,
                   u.account_status, u.created_at, u.updated_at, -- Added user fields
                   a.admin_level
            FROM users u
            JOIN admins a ON u.user_id = a.user_id
            WHERE u.user_id = %s AND u.user_type = 'admin'
        """, (admin_id,))
        admin = cursor.fetchone()
        if not admin:
            current_app.logger.warning(f"Admin not found for ID {admin_id} in get_admin_or_404")
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error in get_admin_or_404 for ID {admin_id}: {db_err}")
        admin = None # Ensure None on error
    except Exception as e:
        current_app.logger.error(f"General Error in get_admin_or_404 for ID {admin_id}: {e}")
        admin = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return admin

def get_user_basic_info(user_id):
    """Fetches basic user info (username, names) for display."""
    connection = None
    cursor = None
    user_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for basic user info")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id, username, first_name, last_name
            FROM users
            WHERE user_id = %s AND user_type = 'admin'
        """, (user_id,))
        user_info = cursor.fetchone()
        current_app.logger.debug(f"get_user_basic_info for {user_id} found: {user_info}")
    except mysql.connector.Error as db_err:
         current_app.logger.error(f"DB error fetching basic info for user ID {user_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"General error fetching basic info for user ID {user_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user_info

def get_role_id(role_name):
    """Fetches the role_id for a given role_name."""
    connection = None
    cursor = None
    role_id = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for role ID fetch")
        cursor = connection.cursor()
        cursor.execute("SELECT role_id FROM roles WHERE role_name = %s", (role_name,))
        result = cursor.fetchone()
        if result:
            role_id = result[0]
        else:
            current_app.logger.error(f"Role '{role_name}' not found in roles table.")
    except mysql.connector.Error as db_err:
         current_app.logger.error(f"DB error fetching role ID for '{role_name}': {db_err}")
    except Exception as e:
        current_app.logger.error(f"General error fetching role ID for '{role_name}': {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return role_id

# --- NEW HELPER ---
def get_role_or_404(role_id):
    """Fetches role details by ID or returns None."""
    connection = None
    cursor = None
    role = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed getting role")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT role_id, role_name, description, created_at, updated_at FROM roles WHERE role_id = %s", (role_id,))
        role = cursor.fetchone()
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error fetching role ID {role_id}: {db_err}")
    except Exception as e:
        current_app.logger.error(f"General Error fetching role ID {role_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return role

# --- Admin User Routes ---

@admin_management.route('/admin/admins', methods=['GET'])
@login_required
def index():
    """Displays a paginated list of admins with search and sort."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login')) # Or wherever non-admins should go

    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    sort_by = request.args.get('sort_by', 'last_name').lower()
    if sort_by not in ALLOWED_SORT_COLUMNS: sort_by = 'last_name'
    sort_order = request.args.get('sort_order', 'asc').lower()
    if sort_order not in ['asc', 'desc']: sort_order = 'asc'

    connection = None
    cursor = None
    admins = []
    total_items = 0
    total_pages = 0

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed in admin index")
        cursor = connection.cursor(dictionary=True)

        base_query = """
            FROM users u
            JOIN admins a ON u.user_id = a.user_id
            WHERE u.user_type = 'admin'
        """
        params = []
        search_clause = ""
        if search_term:
            search_clause = """ AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s
                                 OR a.admin_level LIKE %s OR u.account_status LIKE %s)"""
            like_term = f"%{search_term}%"
            params.extend([like_term, like_term, like_term, like_term, like_term])

        count_query = f"SELECT COUNT(u.user_id) as total {base_query} {search_clause}"
        cursor.execute(count_query, tuple(params))
        result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE) if total_items > 0 else 0

        offset = (page - 1) * PER_PAGE
        # Determine prefix for sort column
        if sort_by == "admin_level":
            sort_column_prefix = "a."
        elif sort_by == "account_status":
            sort_column_prefix = "u."
        else: # first_name, last_name, email are in users table
            sort_column_prefix = "u."

        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, a.admin_level, u.account_status
            {base_query} {search_clause} ORDER BY {sort_column_prefix}{sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE, offset]
        cursor.execute(data_query, tuple(final_params))
        admins = cursor.fetchall()

    except mysql.connector.Error as db_err:
        flash(f"Database error fetching admins: {db_err}", "danger")
        current_app.logger.error(f"DB Error fetching admin list: {db_err}")
    except Exception as e:
        flash(f"Error fetching admins: {str(e)}", "danger")
        current_app.logger.error(f"General Error fetching admin list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Admins/manage_admins.html', # Assuming this is the template name
        admins=admins, page=page, total_pages=total_pages, per_page=PER_PAGE,
        total_items=total_items, search_term=search_term, sort_by=sort_by,
        sort_order=sort_order,
        allowed_sort_columns=ALLOWED_SORT_COLUMNS # Pass allowed columns for template links
    )


# --- Add Admin Step 1 (No changes needed here for the requested features) ---

@admin_management.route('/admin/admins/add/step1', methods=['GET'])
@login_required
def add_admin_step1_form():
    """Displays Step 1 of the add admin form (User details)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data={}) # Assuming template name

@admin_management.route('/admin/admins/add/step1', methods=['POST'])
@login_required
def add_admin_step1():
    """Processes Step 1: Creates user, stores PLAIN TEXT password, assigns role."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password') # Plain text password
    confirm_password = request.form.get('confirm_password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None

    form_data_for_render = request.form.copy()
    form_data_for_render['password'] = '' # Clear passwords for re-render
    form_data_for_render['confirm_password'] = ''

    if not all([username, email, password, confirm_password, first_name, last_name]):
        flash("Missing required fields (Username, Email, Password, Confirm Password, First Name, Last Name).", "danger")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

    # WARNING: No Hashing - Storing plain text password
    # hashed_password = generate_password(password) # Removed

    connection = None
    cursor = None
    user_id = None
    admin_role_id = get_role_id('Admin') # Fetch Admin role ID

    if not admin_role_id:
        flash("Critical Error: 'Admin' role not found in the database.", "danger")
        current_app.logger.error("Could not find role_id for 'Admin' during admin creation.")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email or Username already exists.", "danger")
            return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

        # Insert into users table with PLAIN TEXT password into password column
        # Default account_status should be handled by DB default or trigger. Assuming 'pending' or 'active'.
        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name,
                               user_type, phone)
            VALUES (%s, %s, %s, %s, %s, 'admin', %s)
        """, (username, email, password, first_name, last_name, phone)) # Using plain 'password' here

        user_id = cursor.lastrowid
        if not user_id:
             connection.rollback()
             current_app.logger.error(f"Failed to get lastrowid for user {username} even after INSERT seemed okay.")
             flash("Error: Could not retrieve user ID after creation.", "danger")
             return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

        # Insert into user_roles table
        cursor.execute("""
            INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)
        """, (user_id, admin_role_id))

        # Trigger 'after_users_insert_professional' should create the 'admins' record.

        connection.commit() # Commit both inserts

        current_app.logger.info(f"Step 1: Committed user insert for {username} (ID: {user_id}) with PLAIN TEXT password and assigned Admin role. Trigger should create admins record. Redirecting to Step 2.")
        flash("Step 1 complete: User account created with default admin settings. Now confirm or change admin level.", "info")
        return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        if db_err.errno == 1062: # Duplicate entry
             flash(f"Database error: Username or Email likely already exists.", "danger")
             current_app.logger.warning(f"Duplicate entry error adding admin {username}/{email}: {db_err}")
        else:
             flash(f"Database error creating user: {db_err}", "danger")
             current_app.logger.error(f"DB Error adding user/role (step 1) for {username}: {db_err}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error creating user: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error adding user/role (step 1) for {username}: {e}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Fallback redirect in case of unexpected flow
    return redirect(url_for('admin_management.add_admin_step1_form'))


# --- Add Admin Step 2 (No changes needed here for the requested features) ---

@admin_management.route('/admin/admins/add/step2/<int:user_id>', methods=['GET'])
@login_required
def add_admin_step2_form(user_id):
    """Displays Step 2 of the add admin form (Set Admin Level)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    current_app.logger.info(f"Step 2 Form (GET): Received request for user_id = {user_id}")
    user_info = get_user_basic_info(user_id)

    if not user_info:
        current_app.logger.error(f"Step 2 Form (GET): User info not found for ID {user_id}. User might not exist or is not an admin.")
        flash("Admin user not found or invalid ID.", "danger")
        return redirect(url_for('admin_management.index'))

    admin_levels = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS

    # Fetch the current admin level set by the trigger (or previous step)
    connection = None
    cursor = None
    current_level = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT admin_level FROM admins WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            current_level = result[0]
        else:
            current_app.logger.warning(f"Step 2 Form (GET): No record found in 'admins' table for user_id {user_id}. Trigger might have failed.")
            # Don't flash here, let the POST handle it if it fails
    except Exception as e:
        current_app.logger.error(f"Error fetching current admin level for {user_id} in Step 2 GET: {e}")
        # Don't flash, proceed with defaults
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Admins/add_admin_step2.html', # Assuming template name
        user=user_info,
        admin_levels=admin_levels,
        current_level=current_level
    )

@admin_management.route('/admin/admins/add/step2/<int:user_id>', methods=['POST'])
@login_required
def add_admin_step2(user_id):
    """Processes Step 2: Updates the admin level in the 'admins' table."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    admin_level = request.form.get('admin_level')
    current_app.logger.info(f"Step 2 (POST): Received level '{admin_level}' for user_id = {user_id}")

    admin_levels_valid = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS

    if not admin_level or admin_level not in admin_levels_valid:
        flash("Invalid or missing admin level selected.", "danger")
        user_info = get_user_basic_info(user_id) # Refetch needed info for re-render
        if not user_info:
            current_app.logger.error(f"Step 2 (POST): User info lost for ID {user_id} on validation fail.")
            return redirect(url_for('admin_management.index')) # Redirect if user info lost
        return render_template(
            'Admin_Portal/Admins/add_admin_step2.html',
            user=user_info,
            admin_levels=admin_levels_valid,
            selected_level=admin_level # Pass back invalid selection
        )

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for step 2 update")
        cursor = connection.cursor()

        # Use INSERT ... ON DUPLICATE KEY UPDATE or check existence first if trigger might fail
        # Simpler approach: Just try UPDATE. If trigger failed, this won't find the row.
        cursor.execute("""
            UPDATE admins SET admin_level = %s WHERE user_id = %s
        """, (admin_level, user_id))

        rows_affected = cursor.rowcount
        connection.commit()

        if rows_affected == 0:
             # Could be trigger failure OR the level selected was the same as current
             # Check if the record exists at all to differentiate
             cursor.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
             exists = cursor.fetchone()
             if not exists:
                 current_app.logger.error(f"Step 2 (POST): FAILED. No record in 'admins' table for user_id {user_id}. Trigger likely failed.")
                 flash("ERROR: Admin setup failed. Could not find admin-specific record. Please delete user and retry.", "danger")
                 # Redirect to index might be confusing, maybe back to step 1 or show user details?
                 return redirect(url_for('admin_management.index')) # Or specific error page
             else:
                 current_app.logger.info(f"Step 2 (POST): Admin level for user {user_id} was likely unchanged.")
                 flash("Admin level was not changed.", "info") # Inform user no change occurred
        else:
            current_app.logger.info(f"Step 2 (POST): Successfully updated admin level for user {user_id} to '{admin_level}'.")
            flash("Admin created/updated successfully with the specified level.", "success")

        return redirect(url_for('admin_management.index'))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error setting admin level: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating admin level (step 2) for user ID {user_id}: {db_err}")
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error setting admin level: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin level (step 2) for user ID {user_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # Fallback redirect if errors occurred before successful redirect
    return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))


# --- Edit Admin ---

@admin_management.route('/admin/admins/edit/<int:admin_id>', methods=['GET'])
@login_required
def edit_admin_form(admin_id):
    """Displays the form to edit an existing admin."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    admin = get_admin_or_404(admin_id)
    if not admin:
         flash("Admin not found.", "danger")
         return redirect(url_for('admin_management.index'))

    admin_levels = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS
    account_statuses = get_enum_values('users', 'account_status') or DEFAULT_ACCOUNT_STATUSES # Fetch statuses

    return render_template(
        'Admin_Portal/Admins/edit_admin.html', # Assuming template name
        admin=admin,
        admin_levels=admin_levels,
        account_statuses=account_statuses # Pass statuses to template
    )

@admin_management.route('/admin/admins/edit/<int:admin_id>', methods=['POST'])
@login_required
def edit_admin(admin_id):
    """Processes editing of admin details, including status, PLAIN TEXT password updates/reset."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    current_admin_data = get_admin_or_404(admin_id) # Fetch current data for comparison and re-render
    if not current_admin_data:
        flash("Cannot edit admin: Admin not found.", "danger")
        return redirect(url_for('admin_management.index'))

    # Prepare data needed for re-rendering the form in case of error
    admin_data_for_render = current_admin_data.copy() # Start with current data
    redirect_target = url_for('admin_management.index') # Default redirect target
    admin_levels_for_render = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS
    account_statuses_for_render = get_enum_values('users', 'account_status') or DEFAULT_ACCOUNT_STATUSES

    try:
        # Get form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone') or None
        admin_level = request.form.get('admin_level')
        account_status = request.form.get('account_status') # Get selected status
        new_password = request.form.get('new_password') # Plain text for reset/change
        confirm_password = request.form.get('confirm_password') # Plain text

        # Update the dictionary we'll use for re-rendering if there's an error
        admin_data_for_render.update({
             'first_name': first_name, 'last_name': last_name, 'email': email,
             'phone': phone, 'admin_level': admin_level, 'account_status': account_status
        })

        # --- Validation ---
        if not all([first_name, last_name, email, admin_level, account_status]):
             flash("Missing required fields (First Name, Last Name, Email, Admin Level, Account Status).", "danger")
             return render_template('Admin_Portal/Admins/edit_admin.html',
                                    admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                    account_statuses=account_statuses_for_render)

        if admin_level not in admin_levels_for_render:
            flash(f"Invalid admin level selected: {admin_level}", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                   account_statuses=account_statuses_for_render)

        if account_status not in account_statuses_for_render:
            flash(f"Invalid account status selected: {account_status}", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                   account_statuses=account_statuses_for_render)

        # Password change/reset logic (plain text)
        update_password = False
        password_to_update = None # Will store the plain text password if changing
        if new_password or confirm_password: # If either field is touched, assume intent to change
            if not new_password or not confirm_password:
                 flash("Both New Password and Confirm Password are required to change/reset the password.", "warning")
                 return render_template('Admin_Portal/Admins/edit_admin.html',
                                        admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                        account_statuses=account_statuses_for_render)
            elif new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return render_template('Admin_Portal/Admins/edit_admin.html',
                                        admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                        account_statuses=account_statuses_for_render)
            else:
                # WARNING: Using plain text password directly
                password_to_update = new_password
                update_password = True
                current_app.logger.warning(f"Updating password for admin {admin_id} with PLAIN TEXT.")


        # --- Database Operations ---
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for edit admin")
        cursor = connection.cursor()

        # Check for email uniqueness (excluding the current user)
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, admin_id))
        existing_email_user = cursor.fetchone()
        if existing_email_user:
            flash("Email address already in use by another user.", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                   account_statuses=account_statuses_for_render)

        # Build UPDATE for users table only if fields changed
        user_update_fields = []
        user_params = []

        if first_name != current_admin_data.get('first_name'):
            user_update_fields.append("first_name = %s")
            user_params.append(first_name)
        if last_name != current_admin_data.get('last_name'):
            user_update_fields.append("last_name = %s")
            user_params.append(last_name)
        if email != current_admin_data.get('email'):
            user_update_fields.append("email = %s")
            user_params.append(email)
        if phone != current_admin_data.get('phone'): # Handles None correctly
            user_update_fields.append("phone = %s")
            user_params.append(phone)
        # Check if account status changed
        if account_status != current_admin_data.get('account_status'):
             user_update_fields.append("account_status = %s")
             user_params.append(account_status)
        if update_password:
            # Updating the password column with the plain text password
            user_update_fields.append("password = %s")
            user_params.append(password_to_update) # Plain text password

        user_rows_affected = 0
        if user_update_fields:
            user_update_query = f"UPDATE users SET {', '.join(user_update_fields)}, updated_at = NOW() WHERE user_id = %s AND user_type = 'admin'"
            user_params.append(admin_id)
            cursor.execute(user_update_query, tuple(user_params))
            user_rows_affected = cursor.rowcount

        # Update admin_level in admins table if it changed
        admin_rows_affected = 0
        if admin_level != current_admin_data.get('admin_level'):
             cursor.execute("""
                 UPDATE admins SET admin_level = %s WHERE user_id = %s
             """, (admin_level, admin_id))
             admin_rows_affected = cursor.rowcount

        # Commit changes if any were made
        if user_rows_affected > 0 or admin_rows_affected > 0:
            connection.commit()
            flash_msg = "Admin updated successfully"
            if update_password: flash_msg += " (Plain Text Password Changed - INSECURE)"
            if account_status != current_admin_data.get('account_status'): flash_msg += f" (Status set to {account_status})"
            flash(flash_msg, "success")
            current_app.logger.info(f"Admin {admin_id} updated. UserRows:{user_rows_affected}, AdminRows:{admin_rows_affected}. PW changed: {update_password} (plain text). Status changed: {account_status != current_admin_data.get('account_status')}")
        else:
            flash("No changes detected for the admin.", "info")
            current_app.logger.info(f"No changes detected during edit for admin {admin_id}.")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        if db_err.errno == 1062: # Duplicate entry (likely email if check failed somehow)
            flash(f"Database error: Could not update admin, possibly due to duplicate email. {db_err}", "danger")
            current_app.logger.warning(f"Duplicate entry error editing admin {admin_id}: {db_err}")
        else:
            flash(f"Database error updating admin: {db_err}", "danger")
            current_app.logger.error(f"DB Error updating admin {admin_id}: {db_err}")
        # Ensure we redirect back to the edit form on DB error
        redirect_target = url_for('admin_management.edit_admin_form', admin_id=admin_id)
        # Re-render template with error message and submitted data
        return render_template('Admin_Portal/Admins/edit_admin.html',
                               admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                               account_statuses=account_statuses_for_render)

    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"An unexpected error occurred updating admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin {admin_id}: {e}", exc_info=True)
        # Redirect back to edit form on general error unless it's a connection issue
        if "connection" not in str(e).lower():
             redirect_target = url_for('admin_management.edit_admin_form', admin_id=admin_id)
             return render_template('Admin_Portal/Admins/edit_admin.html',
                                    admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                    account_statuses=account_statuses_for_render)
        else: # If connection error, redirecting to index might be safer
             redirect_target = url_for('admin_management.index')

    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target) # Redirect to index on success or specific error cases


# --- Delete Admin (No changes needed here for the requested features) ---

@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['GET'])
@login_required
def delete_admin_form(admin_id):
    """Displays the confirmation page before deleting an admin."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # Prevent self-deletion
    current_user_id = None
    try:
        current_user_id = int(current_user.id)
    except (ValueError, TypeError, AttributeError):
        current_app.logger.error(f"Could not get valid integer ID from current_user.id ({getattr(current_user, 'id', 'N/A')})")
        flash("Error identifying current user.", "danger")
        return redirect(url_for('admin_management.index'))

    if admin_id == current_user_id:
       flash("You cannot delete your own admin account.", "danger")
       return redirect(url_for('admin_management.index'))

    admin = get_admin_or_404(admin_id)
    if not admin:
        flash("Admin not found.", "danger")
        return redirect(url_for('admin_management.index'))

    return render_template('Admin_Portal/Admins/delete_confirmation.html', admin=admin) # Assuming template name

@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['POST'])
@login_required
def delete_admin(admin_id):
    """Processes the deletion of an admin (relies on FK cascade or manual cleanup)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # Prevent self-deletion (double check)
    current_user_id = None
    try:
        current_user_id = int(current_user.id)
    except (ValueError, TypeError, AttributeError):
        current_app.logger.error(f"Could not get valid integer ID from current_user.id for delete POST ({getattr(current_user, 'id', 'N/A')})")
        flash("Error identifying current user for delete confirmation.", "danger")
        return redirect(url_for('admin_management.index'))

    if admin_id == current_user_id:
        flash("You cannot delete your own admin account.", "danger")
        return redirect(url_for('admin_management.index'))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for delete admin")
        cursor = connection.cursor()

        # IMPORTANT: Assumes Foreign Key constraints with ON DELETE CASCADE are set up
        # for 'admins' table and 'user_roles' table referencing 'users.user_id'.
        # If not, you would need to manually delete from those tables FIRST.
        # e.g., cursor.execute("DELETE FROM admins WHERE user_id = %s", (admin_id,))
        # e.g., cursor.execute("DELETE FROM user_roles WHERE user_id = %s", (admin_id,))

        # Delete ONLY from the users table.
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'admin'", (admin_id,))
        user_rows_deleted = cursor.rowcount

        connection.commit()

        if user_rows_deleted == 0:
             flash("Admin user record not found or already deleted.", "warning")
             current_app.logger.warning(f"Delete request for non-existent admin user ID {admin_id} or wrong user_type. 0 rows affected.")
        else:
            flash("Admin deleted successfully.", "success")
            current_app.logger.info(f"Successfully deleted admin user ID {admin_id}. Related records should be handled by cascade delete.")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")

        if db_err.errno == 1451: # Foreign Key Constraint violation
             flash(f"Database error: Could not delete admin. There might be related data (e.g., audit logs, assigned tasks) that needs to be removed or reassigned first. Check foreign key constraints. (Error: {db_err})", "danger")
             current_app.logger.error(f"FK Constraint Error deleting admin {admin_id}: {db_err}. Cascade might be missing or pointing to other tables not handled.")
        else:
            flash(f"Database error deleting admin: {db_err}", "danger")
            current_app.logger.error(f"DB Error deleting admin {admin_id}: {db_err}")
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error deleting admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error deleting admin {admin_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.index'))


# ==============================================
# --- NEW: Role Definition Management Routes ---
# ==============================================

@admin_management.route('/admin/roles', methods=['GET'])
@login_required
def manage_roles():
    """Displays a list of defined roles."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    roles = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT role_id, role_name, description, created_at, updated_at FROM roles ORDER BY role_name")
        roles = cursor.fetchall()
    except mysql.connector.Error as db_err:
        flash(f"Database error fetching roles: {db_err}", "danger")
        current_app.logger.error(f"DB Error fetching role list: {db_err}")
    except Exception as e:
        flash(f"Error fetching roles: {str(e)}", "danger")
        current_app.logger.error(f"General Error fetching role list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    # You'll need a template for this: 'Admin_Portal/Roles/manage_roles.html'
    return render_template('Admin_Portal/Roles/manage_roles.html', roles=roles)

@admin_management.route('/admin/roles/add', methods=['GET', 'POST'])
@login_required
def add_role():
    """Handles adding a new role definition."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    if request.method == 'POST':
        role_name = request.form.get('role_name', '').strip()
        description = request.form.get('description', '').strip() or None # Allow empty description

        if not role_name:
            flash("Role Name is required.", "danger")
            # Re-render form with submitted data
            return render_template('Admin_Portal/Roles/add_role.html', role_name=role_name, description=description) # Assuming template name

        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT INTO roles (role_name, description) VALUES (%s, %s)", (role_name, description))
            connection.commit()
            flash(f"Role '{role_name}' created successfully.", "success")
            current_app.logger.info(f"Admin {current_user.id} created role '{role_name}'.")
            return redirect(url_for('admin_management.manage_roles'))
        except mysql.connector.Error as db_err:
            try:
                if connection and connection.is_connected(): connection.rollback()
            except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
            if db_err.errno == 1062: # Duplicate entry
                flash(f"Role name '{role_name}' already exists.", "danger")
                current_app.logger.warning(f"Attempt to add duplicate role name '{role_name}': {db_err}")
            else:
                flash(f"Database error creating role: {db_err}", "danger")
                current_app.logger.error(f"DB error creating role '{role_name}': {db_err}")
            # Re-render form with submitted data on error
            return render_template('Admin_Portal/Roles/add_role.html', role_name=role_name, description=description)
        except Exception as e:
            try:
                if connection and connection.is_connected(): connection.rollback()
            except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
            flash(f"Error creating role: {str(e)}", "danger")
            current_app.logger.error(f"Non-DB error creating role '{role_name}': {e}")
            # Re-render form with submitted data on error
            return render_template('Admin_Portal/Roles/add_role.html', role_name=role_name, description=description)
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()

    # GET request: Display the add role form
    # You'll need a template for this: 'Admin_Portal/Roles/add_role.html'
    return render_template('Admin_Portal/Roles/add_role.html')


@admin_management.route('/admin/roles/edit/<int:role_id>', methods=['GET', 'POST'])
@login_required
def edit_role(role_id):
    """Handles editing an existing role definition."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    role = get_role_or_404(role_id)
    if not role:
        flash("Role not found.", "danger")
        return redirect(url_for('admin_management.manage_roles'))

    if request.method == 'POST':
        role_name = request.form.get('role_name', '').strip()
        description = request.form.get('description', '').strip() or None

        if not role_name:
            flash("Role Name is required.", "danger")
            # Re-render form with submitted data and original role ID
            return render_template('Admin_Portal/Roles/edit_role.html', role=role, role_name=role_name, description=description) # Template name

        # Check if changes were actually made
        if role_name == role['role_name'] and description == role['description']:
             flash("No changes detected for the role.", "info")
             return redirect(url_for('admin_management.manage_roles'))


        connection = None
        cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE roles SET role_name = %s, description = %s, updated_at = NOW()
                WHERE role_id = %s
            """, (role_name, description, role_id))
            connection.commit()
            flash(f"Role '{role_name}' updated successfully.", "success")
            current_app.logger.info(f"Admin {current_user.id} updated role ID {role_id} to name '{role_name}'.")
            return redirect(url_for('admin_management.manage_roles'))
        except mysql.connector.Error as db_err:
            try:
                if connection and connection.is_connected(): connection.rollback()
            except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
            if db_err.errno == 1062: # Duplicate entry
                flash(f"Another role with the name '{role_name}' already exists.", "danger")
                current_app.logger.warning(f"Attempt to update role ID {role_id} to duplicate name '{role_name}': {db_err}")
            else:
                flash(f"Database error updating role: {db_err}", "danger")
                current_app.logger.error(f"DB error updating role ID {role_id}: {db_err}")
            # Re-render edit form with submitted data on error
            role['role_name'] = role_name # Update dict for render
            role['description'] = description
            return render_template('Admin_Portal/Roles/edit_role.html', role=role)
        except Exception as e:
            try:
                if connection and connection.is_connected(): connection.rollback()
            except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
            flash(f"Error updating role: {str(e)}", "danger")
            current_app.logger.error(f"Non-DB error updating role ID {role_id}: {e}")
            # Re-render edit form with submitted data on error
            role['role_name'] = role_name # Update dict for render
            role['description'] = description
            return render_template('Admin_Portal/Roles/edit_role.html', role=role)
        finally:
            if cursor: cursor.close()
            if connection and connection.is_connected(): connection.close()

    # GET request: Display the edit role form, pre-filled
    # You'll need a template for this: 'Admin_Portal/Roles/edit_role.html'
    return render_template('Admin_Portal/Roles/edit_role.html', role=role)


@admin_management.route('/admin/roles/delete/<int:role_id>', methods=['POST'])
@login_required
def delete_role(role_id):
    """Processes the deletion of a role definition."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # Optional: Add GET route for confirmation page if desired
    # Optional: Prevent deletion of core roles like 'Admin'
    role = get_role_or_404(role_id) # Get role info for logging/messages
    if not role:
        flash("Role not found.", "warning") # Warning as it might have just been deleted
        return redirect(url_for('admin_management.manage_roles'))

    # Simple check for core role (adjust name if needed)
    if role['role_name'].lower() == 'admin':
         flash("The core 'Admin' role cannot be deleted.", "danger")
         return redirect(url_for('admin_management.manage_roles'))

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM roles WHERE role_id = %s", (role_id,))
        rows_deleted = cursor.rowcount
        connection.commit()

        if rows_deleted > 0:
            flash(f"Role '{role['role_name']}' deleted successfully.", "success")
            current_app.logger.info(f"Admin {current_user.id} deleted role '{role['role_name']}' (ID: {role_id}).")
        else:
            flash(f"Role '{role['role_name']}' not found or already deleted.", "warning")
            current_app.logger.warning(f"Attempted delete for non-existent role ID {role_id} ('{role['role_name']}').")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        if db_err.errno == 1451: # Foreign Key constraint violation
            flash(f"Cannot delete role '{role['role_name']}'. It is currently assigned to users or has associated permissions.", "danger")
            current_app.logger.warning(f"FK constraint prevented deletion of role ID {role_id} ('{role['role_name']}'): {db_err}")
        else:
            flash(f"Database error deleting role: {db_err}", "danger")
            current_app.logger.error(f"DB error deleting role ID {role_id} ('{role['role_name']}'): {db_err}")
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Error deleting role: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB error deleting role ID {role_id} ('{role['role_name']}'): {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.manage_roles'))