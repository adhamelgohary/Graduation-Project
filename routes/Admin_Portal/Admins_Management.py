# admin_management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash # Added for password hashing
from db import get_db_connection
from math import ceil
import mysql.connector # For specific error handling
import re # Import regular expressions for parsing

admin_management = Blueprint('admin_management', __name__)

# --- Constants ---
PER_PAGE = 10
ALLOWED_SORT_COLUMNS = {'first_name', 'last_name', 'email', 'admin_level', 'account_status'}
DEFAULT_ADMIN_LEVELS = ['regular', 'super']
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
            current_app.logger.error(f"DB connection object invalid or not connected for ENUM fetch {table_name}.{column_name}")
            raise ConnectionError("DB connection failed for ENUM fetch")

        cursor = connection.cursor()
        db_name = connection.database
        if not db_name:
            db_name = current_app.config.get('MYSQL_DB')
        if not db_name:
            current_app.logger.warning("Could not determine database name to fetch ENUMs.")
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
            enum_def = result[0]
            if enum_def.lower().startswith("enum("):
                content = enum_def[5:-1]
                enum_values = [val.strip().strip("'").strip('"') for val in content.split(',')]
            else:
                 current_app.logger.warning(f"Could not parse ENUM string: {result[0]} for {table_name}.{column_name}")
        else:
            current_app.logger.warning(f"Could not find ENUM definition for {table_name}.{column_name}")

    except mysql.connector.Error as db_err:
        current_app.logger.error(f"Database error fetching ENUM values for {table_name}.{column_name}: {db_err}")
        enum_values = []
    except ConnectionError as conn_err:
        current_app.logger.error(f"Connection error during ENUM fetch for {table_name}.{column_name}: {conn_err}")
        enum_values = []
    except Exception as e:
        current_app.logger.error(f"General error fetching ENUM values for {table_name}.{column_name}: {e}")
        enum_values = []
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

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
            current_app.logger.error(f"DB connection failed in get_admin_or_404 for admin_id {admin_id}")
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.email, u.phone,
                   u.account_status, u.created_at, u.updated_at,
                   a.admin_level
            FROM users u
            JOIN admins a ON u.user_id = a.user_id
            WHERE u.user_id = %s AND u.user_type = 'admin'
        """, (admin_id,))
        admin = cursor.fetchone()
        if not admin:
            current_app.logger.warning(f"Admin not found for ID {admin_id} in get_admin_or_404 (user_type check might be relevant).")
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error in get_admin_or_404 for ID {admin_id}: {db_err}")
        admin = None
    except ConnectionError as conn_err:
        current_app.logger.error(f"Connection Error in get_admin_or_404 for ID {admin_id}: {conn_err}")
        admin = None
    except Exception as e:
        current_app.logger.error(f"General Error in get_admin_or_404 for ID {admin_id}: {e}")
        admin = None
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return admin

def get_user_basic_info(user_id):
    """Fetches basic user info (username, names) for display. Ensures user_type is 'admin'."""
    connection = None
    cursor = None
    user_info = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed for basic user info (user_id: {user_id})")
            raise ConnectionError("DB connection failed for basic user info")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT user_id, username, first_name, last_name
            FROM users
            WHERE user_id = %s AND user_type = 'admin'
        """, (user_id,))
        user_info = cursor.fetchone()
        if user_info:
            current_app.logger.debug(f"get_user_basic_info for admin user {user_id} found: {user_info}")
        else:
            current_app.logger.warning(f"get_user_basic_info for user_id {user_id} returned no data (is user_type 'admin'?).")
    except mysql.connector.Error as db_err:
         current_app.logger.error(f"DB error fetching basic info for user ID {user_id}: {db_err}")
    except ConnectionError as conn_err:
        current_app.logger.error(f"Connection error fetching basic info for user ID {user_id}: {conn_err}")
    except Exception as e:
        current_app.logger.error(f"General error fetching basic info for user ID {user_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user_info


# --- Admin User Routes ---

@admin_management.route('/admin/admins', methods=['GET'])
@login_required
def index():
    if current_user.user_type != "admin":
        flash("Access denied. You must be an admin to view this page.", "danger")
        return redirect(url_for('login.login'))

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
            current_app.logger.error("DB connection failed in admin index route.")
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
        if sort_by == "admin_level":
            sort_column_prefix = "a."
        elif sort_by == "account_status":
            sort_column_prefix = "u."
        else:
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
    except ConnectionError as conn_err:
        flash("Error connecting to the database to fetch admins.", "danger")
        current_app.logger.error(f"Connection error fetching admin list: {conn_err}")
    except Exception as e:
        flash(f"Error fetching admins: {str(e)}", "danger")
        current_app.logger.error(f"General Error fetching admin list: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Admins/manage_admins.html',
        admins=admins, page=page, total_pages=total_pages, per_page=PER_PAGE,
        total_items=total_items, search_term=search_term, sort_by=sort_by,
        sort_order=sort_order,
        allowed_sort_columns=ALLOWED_SORT_COLUMNS
    )


@admin_management.route('/admin/admins/add/step1', methods=['GET'])
@login_required
def add_admin_step1_form():
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))
    return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data={})

@admin_management.route('/admin/admins/add/step1', methods=['POST'])
@login_required
def add_admin_step1():
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    phone = request.form.get('phone') or None

    form_data_for_render = request.form.copy()
    form_data_for_render['password'] = ''
    form_data_for_render['confirm_password'] = ''

    if not all([username, email, password, confirm_password, first_name, last_name]):
        flash("Missing required fields (Username, Email, Password, Confirm Password, First Name, Last Name).", "danger")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

    hashed_password = generate_password_hash(password)

    connection = None
    cursor = None
    user_id = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error("DB connection failed in add_admin_step1 POST.")
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email or Username already exists.", "danger")
            return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name,
                               user_type, phone, account_status)
            VALUES (%s, %s, %s, %s, %s, 'admin', %s, %s)
        """, (username, email, hashed_password, first_name, last_name, phone, 'pending'))

        user_id = cursor.lastrowid
        if not user_id:
             connection.rollback()
             current_app.logger.error(f"Failed to get lastrowid for user {username} after INSERT.")
             flash("Error: Could not retrieve user ID after creation.", "danger")
             return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)

        # The trigger 'after_users_insert_professional' should create the 'admins' record.
        # If it doesn't, Step 2 will encounter issues.

        connection.commit()

        current_app.logger.info(f"Step 1: Committed user insert for {username} (ID: {user_id}) with HASHED password. Trigger should create admins record. Redirecting to Step 2.")
        flash("Step 1 complete: User account created with default admin settings and 'pending' status. Now confirm admin level.", "info")
        return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        if db_err.errno == 1062:
             flash(f"Database error: Username or Email likely already exists.", "danger")
             current_app.logger.warning(f"Duplicate entry error adding admin {username}/{email}: {db_err}")
        else:
             flash(f"Database error creating user: {db_err}", "danger")
             current_app.logger.error(f"DB Error adding user (step 1) for {username}: {db_err}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)
    except ConnectionError as conn_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback after connection error: {rb_err}")
        flash("Error connecting to the database. Could not create user.", "danger")
        current_app.logger.error(f"Connection error during add admin step 1 for {username}: {conn_err}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error creating user: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error adding user (step 1) for {username}: {e}", exc_info=True)
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=form_data_for_render)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.add_admin_step1_form'))


@admin_management.route('/admin/admins/add/step2/<int:user_id>', methods=['GET'])
@login_required
def add_admin_step2_form(user_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    current_app.logger.info(f"Step 2 Form (GET): Received request for user_id = {user_id}")
    user_info = get_user_basic_info(user_id)

    if not user_info:
        current_app.logger.error(f"Step 2 Form (GET): Admin user info not found for ID {user_id}. User might not exist or is not an admin type.")
        flash("Admin user not found or invalid ID. Ensure user was created as an admin type.", "danger")
        return redirect(url_for('admin_management.index'))

    admin_levels = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS

    connection = None
    cursor = None
    current_level = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in add_admin_step2_form for user {user_id}")
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT admin_level FROM admins WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        if result:
            current_level = result['admin_level']
        else:
            current_app.logger.warning(f"Step 2 Form (GET): No record found in 'admins' table for user_id {user_id}. Trigger might have failed or not run yet.")
    except mysql.connector.Error as db_err:
        current_app.logger.error(f"DB Error fetching current admin level for {user_id} in Step 2 GET: {db_err}")
    except ConnectionError as conn_err:
        current_app.logger.error(f"Connection Error fetching current admin level for {user_id} in Step 2 GET: {conn_err}")
    except Exception as e:
        current_app.logger.error(f"Error fetching current admin level for {user_id} in Step 2 GET: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Admins/add_admin_step2.html',
        user=user_info,
        admin_levels=admin_levels,
        current_level=current_level
    )

@admin_management.route('/admin/admins/add/step2/<int:user_id>', methods=['POST'])
@login_required
def add_admin_step2(user_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    admin_level = request.form.get('admin_level')
    current_app.logger.info(f"Step 2 (POST): Received level '{admin_level}' for user_id = {user_id}")

    admin_levels_valid = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS

    user_info = get_user_basic_info(user_id)
    if not user_info:
        current_app.logger.error(f"Step 2 (POST): User info lost for ID {user_id} (not an admin type or does not exist).")
        flash("Admin user not found. Cannot set admin level.", "danger")
        return redirect(url_for('admin_management.index'))

    if not admin_level or admin_level not in admin_levels_valid:
        flash("Invalid or missing admin level selected.", "danger")
        return render_template(
            'Admin_Portal/Admins/add_admin_step2.html',
            user=user_info,
            admin_levels=admin_levels_valid,
            selected_level=admin_level,
            current_level=request.form.get('current_level_hidden')
        )

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in add_admin_step2 POST for user {user_id}")
            raise ConnectionError("DB connection failed for step 2 update")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (user_id,))
        admin_record_exists = cursor.fetchone()

        if not admin_record_exists:
            current_app.logger.warning(f"Step 2 (POST): No record in 'admins' for user_id {user_id}. Attempting to create it.")
            cursor.execute("""
                INSERT INTO admins (user_id, admin_level) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE admin_level = VALUES(admin_level)
            """, (user_id, admin_level))
        else:
            cursor.execute("""
                UPDATE admins SET admin_level = %s WHERE user_id = %s
            """, (admin_level, user_id))

        rows_affected = cursor.rowcount
        connection.commit()

        if rows_affected == 0 and admin_record_exists:
             cursor.execute("SELECT admin_level FROM admins WHERE user_id = %s", (user_id,))
             current_db_level = cursor.fetchone()
             if current_db_level and current_db_level[0] == admin_level:
                 current_app.logger.info(f"Step 2 (POST): Admin level for user {user_id} was already '{admin_level}'. No change made.")
                 flash(f"Admin level was already '{admin_level}'. No changes applied.", "info")
             else:
                 current_app.logger.error(f"Step 2 (POST): FAILED to update. 'admins' record for user_id {user_id} exists, but update reported 0 rows affected and level is different.")
                 flash("ERROR: Admin setup failed. Could not update admin-specific record. Please check logs.", "danger")
                 return redirect(url_for('admin_management.index'))
        elif rows_affected > 0 or (not admin_record_exists and cursor.lastrowid):
            current_app.logger.info(f"Step 2 (POST): Successfully set/updated admin level for user {user_id} to '{admin_level}'.")
            flash("Admin created/updated successfully with the specified level.", "success")
        else:
            current_app.logger.error(f"Step 2 (POST): FAILED. No record in 'admins' for user_id {user_id} and attempt to create failed.")
            flash("ERROR: Admin setup failed. Could not create/update admin-specific record. Trigger may have failed and manual insert also failed.", "danger")
            return redirect(url_for('admin_management.index'))

        return redirect(url_for('admin_management.index'))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error setting admin level: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating admin level (step 2) for user ID {user_id}: {db_err}")
    except ConnectionError as conn_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback after connection error: {rb_err}")
        flash("Error connecting to the database. Could not set admin level.", "danger")
        current_app.logger.error(f"Connection Error updating admin level (step 2) for user ID {user_id}: {conn_err}")
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error setting admin level: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin level (step 2) for user ID {user_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))


@admin_management.route('/admin/admins/edit/<int:admin_id>', methods=['GET'])
@login_required
def edit_admin_form(admin_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    admin = get_admin_or_404(admin_id)
    if not admin:
         flash("Admin not found or user is not an admin type.", "danger")
         return redirect(url_for('admin_management.index'))

    admin_levels = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS
    account_statuses = get_enum_values('users', 'account_status') or DEFAULT_ACCOUNT_STATUSES

    return render_template(
        'Admin_Portal/Admins/edit_admin.html',
        admin=admin,
        admin_levels=admin_levels,
        account_statuses=account_statuses
    )

@admin_management.route('/admin/admins/edit/<int:admin_id>', methods=['POST'])
@login_required
def edit_admin(admin_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    current_admin_data = get_admin_or_404(admin_id)
    if not current_admin_data:
        flash("Cannot edit admin: Admin not found or user is not an admin type.", "danger")
        return redirect(url_for('admin_management.index'))

    admin_data_for_render = current_admin_data.copy()
    redirect_target = url_for('admin_management.index')
    admin_levels_for_render = get_enum_values('admins', 'admin_level') or DEFAULT_ADMIN_LEVELS
    account_statuses_for_render = get_enum_values('users', 'account_status') or DEFAULT_ACCOUNT_STATUSES

    try:
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone') or None
        admin_level = request.form.get('admin_level')
        account_status = request.form.get('account_status')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        admin_data_for_render.update({
             'first_name': first_name, 'last_name': last_name, 'email': email,
             'phone': phone, 'admin_level': admin_level, 'account_status': account_status
        })

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

        update_password = False
        hashed_password_to_update = None
        if new_password or confirm_password:
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
                hashed_password_to_update = generate_password_hash(new_password)
                update_password = True
                current_app.logger.info(f"Password will be updated (hashed) for admin {admin_id}.")

        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in edit_admin POST for admin {admin_id}")
            raise ConnectionError("DB connection failed for edit admin")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, admin_id))
        existing_email_user = cursor.fetchone()
        if existing_email_user:
            flash("Email address already in use by another user.", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                   account_statuses=account_statuses_for_render)

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
        if phone != current_admin_data.get('phone'):
            user_update_fields.append("phone = %s")
            user_params.append(phone)
        if account_status != current_admin_data.get('account_status'):
             user_update_fields.append("account_status = %s")
             user_params.append(account_status)
        if update_password:
            user_update_fields.append("password = %s")
            user_params.append(hashed_password_to_update)

        user_rows_affected = 0
        if user_update_fields:
            user_update_query = f"UPDATE users SET {', '.join(user_update_fields)}, updated_at = NOW() WHERE user_id = %s AND user_type = 'admin'"
            user_params.append(admin_id)
            cursor.execute(user_update_query, tuple(user_params))
            user_rows_affected = cursor.rowcount

        admin_rows_affected = 0
        if admin_level != current_admin_data.get('admin_level'):
             cursor.execute("""
                 UPDATE admins SET admin_level = %s WHERE user_id = %s
             """, (admin_level, admin_id))
             admin_rows_affected = cursor.rowcount

        if user_rows_affected > 0 or admin_rows_affected > 0:
            connection.commit()
            flash_msg_parts = ["Admin updated successfully"]
            if update_password: flash_msg_parts.append("(Password Changed)")
            if account_status != current_admin_data.get('account_status'):
                flash_msg_parts.append(f"(Status set to {account_status})")
            flash(" ".join(flash_msg_parts), "success")
            current_app.logger.info(f"Admin {admin_id} updated. UserRows:{user_rows_affected}, AdminRows:{admin_rows_affected}. PW changed: {update_password} (hashed). Status changed: {account_status != current_admin_data.get('account_status')}")
        else:
            flash("No changes detected for the admin.", "info")
            current_app.logger.info(f"No changes detected during edit for admin {admin_id}.")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        if db_err.errno == 1062:
            flash(f"Database error: Could not update admin, possibly due to duplicate email. {db_err}", "danger")
            current_app.logger.warning(f"Duplicate entry error editing admin {admin_id}: {db_err}")
        else:
            flash(f"Database error updating admin: {db_err}", "danger")
            current_app.logger.error(f"DB Error updating admin {admin_id}: {db_err}")
        redirect_target = url_for('admin_management.edit_admin_form', admin_id=admin_id)
        return render_template('Admin_Portal/Admins/edit_admin.html',
                               admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                               account_statuses=account_statuses_for_render)
    except ConnectionError as conn_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback after connection error: {rb_err}")
        flash("Error connecting to the database. Could not update admin.", "danger")
        current_app.logger.error(f"Connection Error updating admin {admin_id}: {conn_err}")
        redirect_target = url_for('admin_management.edit_admin_form', admin_id=admin_id)
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"An unexpected error occurred updating admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin {admin_id}: {e}", exc_info=True)
        if "connection" not in str(e).lower():
             redirect_target = url_for('admin_management.edit_admin_form', admin_id=admin_id)
             return render_template('Admin_Portal/Admins/edit_admin.html',
                                    admin=admin_data_for_render, admin_levels=admin_levels_for_render,
                                    account_statuses=account_statuses_for_render)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)


@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['GET'])
@login_required
def delete_admin_form(admin_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    current_user_id_int = None
    try:
        current_user_id_int = int(current_user.id)
    except (ValueError, TypeError, AttributeError) as e:
        current_app.logger.error(f"Could not get valid integer ID from current_user.id ({getattr(current_user, 'id', 'N/A')}): {e}")
        flash("Error identifying current user. Cannot proceed with deletion check.", "danger")
        return redirect(url_for('admin_management.index'))

    if admin_id == current_user_id_int:
       flash("You cannot delete your own admin account.", "danger")
       return redirect(url_for('admin_management.index'))

    admin = get_admin_or_404(admin_id)
    if not admin:
        flash("Admin not found or user is not an admin type.", "danger")
        return redirect(url_for('admin_management.index'))

    return render_template('Admin_Portal/Admins/delete_confirmation.html', admin=admin)

@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['POST'])
@login_required
def delete_admin(admin_id):
    if current_user.user_type != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for('login.login'))

    current_user_id_int = None
    try:
        current_user_id_int = int(current_user.id)
    except (ValueError, TypeError, AttributeError) as e:
        current_app.logger.error(f"Could not get valid integer ID from current_user.id for delete POST ({getattr(current_user, 'id', 'N/A')}): {e}")
        flash("Error identifying current user for delete confirmation.", "danger")
        return redirect(url_for('admin_management.index'))

    if admin_id == current_user_id_int:
        flash("You cannot delete your own admin account. This action is prohibited.", "danger")
        return redirect(url_for('admin_management.index'))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            current_app.logger.error(f"DB connection failed in delete_admin POST for admin {admin_id}")
            raise ConnectionError("DB connection failed for delete admin")
        cursor = connection.cursor()

        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'admin'", (admin_id,))
        user_rows_deleted = cursor.rowcount

        connection.commit()

        if user_rows_deleted == 0:
             flash("Admin user record not found, was not an admin type, or already deleted.", "warning")
             current_app.logger.warning(f"Delete request for admin user ID {admin_id} resulted in 0 rows affected. User might not exist or user_type was not 'admin'.")
        else:
            flash("Admin deleted successfully.", "success")
            current_app.logger.info(f"Successfully deleted admin user ID {admin_id}. Related records in 'admins' should be handled by ON DELETE CASCADE.") # Removed 'user_roles'

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")

        if db_err.errno == 1451:
             flash(f"Database error: Could not delete admin. There might be related data (e.g., audit logs, assigned tasks) that needs to be removed or reassigned first. (Error: {db_err.msg})", "danger")
             current_app.logger.error(f"FK Constraint Error deleting admin {admin_id}: {db_err}. Cascade might be missing or other tables might be referencing this user.", exc_info=True)
        else:
            flash(f"Database error deleting admin: {db_err.msg}", "danger")
            current_app.logger.error(f"DB Error deleting admin {admin_id}: {db_err}", exc_info=True)
    except ConnectionError as conn_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback after connection error: {rb_err}")
        flash("Error connecting to the database. Could not delete admin.", "danger")
        current_app.logger.error(f"Connection Error deleting admin {admin_id}: {conn_err}")
    except Exception as e:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt after general error: {rb_err}")
        flash(f"Error deleting admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error deleting admin {admin_id}: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.index'))