# admin_management.py
# Relies on DB connection having autocommit=True
# WARNING: THIS VERSION REMOVES PASSWORD HASHING AND ASSUMES PLAIN TEXT PASSWORDS.
# THIS IS HIGHLY INSECURE AND NOT RECOMMENDED FOR PRODUCTION ENVIRONMENTS.
# It also uses a two-step process for adding admins, relying on a database trigger
# to create the initial 'admins' record.

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
# Removed: from werkzeug.security import generate_password_hash
from db import get_db_connection
from math import ceil
import mysql.connector # For specific error handling if needed
import re # Import regular expressions for parsing

admin_management = Blueprint('admin_management', __name__)

# --- Constants ---
PER_PAGE = 10
ALLOWED_SORT_COLUMNS = {'first_name', 'last_name', 'email', 'admin_level'}

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
            matches = re.findall(r"'([^']*)'", result[0])
            if matches:
                enum_values = matches
            else:
                 current_app.logger.warning(f"Could not parse ENUM string: {result[0]}")
        else:
            current_app.logger.warning(f"Could not find ENUM definition for {table_name}.{column_name}")

    except Exception as e:
        current_app.logger.error(f"Error fetching ENUM values for {table_name}.{column_name}: {e}")
        enum_values = []
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
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
                   a.admin_level
            FROM users u
            JOIN admins a ON u.user_id = a.user_id
            WHERE u.user_id = %s AND u.user_type = 'admin'
        """, (admin_id,))
        admin = cursor.fetchone()
        if not admin:
            current_app.logger.warning(f"Admin not found for ID {admin_id} in get_admin_or_404")
    except Exception as e:
        current_app.logger.error(f"Error in get_admin_or_404 for ID {admin_id}: {e}")
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
    except Exception as e:
        current_app.logger.error(f"Error fetching basic info for user ID {user_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()
    return user_info

# --- Routes ---

@admin_management.route('/admin/admins', methods=['GET'])
@login_required
def index():
    """Displays a paginated list of admins with search and sort."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
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
            search_clause = " AND (u.first_name LIKE %s OR u.last_name LIKE %s OR u.email LIKE %s OR a.admin_level LIKE %s)"
            like_term = f"%{search_term}%"
            params.extend([like_term, like_term, like_term, like_term])

        count_query = f"SELECT COUNT(u.user_id) as total {base_query} {search_clause}"
        cursor.execute(count_query, tuple(params))
        result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / PER_PAGE) if total_items > 0 else 0

        offset = (page - 1) * PER_PAGE
        sort_column_prefix = "a." if sort_by == "admin_level" else "u."
        data_query = f"""
            SELECT u.user_id, u.first_name, u.last_name, u.email, u.phone, a.admin_level
            {base_query} {search_clause} ORDER BY {sort_column_prefix}{sort_by} {sort_order}
            LIMIT %s OFFSET %s
        """
        final_params = params + [PER_PAGE, offset]
        cursor.execute(data_query, tuple(final_params))
        admins = cursor.fetchall()

    except Exception as e:
        flash(f"Database error fetching admins: {str(e)}", "danger")
        current_app.logger.error(f"Error fetching admin list: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return render_template(
        'Admin_Portal/Admins/manage_admins.html',
        admins=admins, page=page, total_pages=total_pages, per_page=PER_PAGE,
        total_items=total_items, search_term=search_term, sort_by=sort_by,
        sort_order=sort_order
    )


# --- Add Admin Step 1 ---

@admin_management.route('/admin/admins/add/step1', methods=['GET'])
@login_required
def add_admin_step1_form():
    """Displays Step 1 of the add admin form (User details)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))
    return render_template('Admin_Portal/Admins/add_admin_step1.html')

@admin_management.route('/admin/admins/add/step1', methods=['POST'])
@login_required
def add_admin_step1():
    """Processes Step 1: Creates the user record (plain text pass)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password') # Plain text
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

    connection = None
    cursor = None
    user_id = None

    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s OR username = %s", (email, username))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email or Username already exists.", "danger")
            return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=request.form)

        cursor.execute("""
            INSERT INTO users (username, email, password, first_name, last_name,
                              user_type, phone)
            VALUES (%s, %s, %s, %s, %s, 'admin', %s)
        """, (username, email, password, first_name, last_name, phone))

        user_id = cursor.lastrowid
        connection.commit() # Explicit commit

        if not user_id:
             current_app.logger.error(f"Failed to get lastrowid for user {username} after explicit commit.")
             flash("Error: User seemed to be created but could not retrieve ID.", "danger")
             return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=request.form)

        current_app.logger.info(f"Step 1: Committed user insert for {username}. lastrowid = {user_id}. Redirecting to Step 2.")
        flash("Step 1 complete: User account created. Now set admin level.", "info")
        return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error creating user: {db_err}", "danger")
        current_app.logger.error(f"DB Error adding user (step 1) for {username}: {db_err}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=request.form)
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error adding user (step 1) for {username}: {e}")
        return render_template('Admin_Portal/Admins/add_admin_step1.html', form_data=request.form)
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.add_admin_step1_form'))


# --- Add Admin Step 2 ---

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
        current_app.logger.error(f"Step 2 Form (GET): User info not found for ID {user_id} after step 1 redirect.")
        flash("Admin user not found or invalid ID.", "danger")
        return redirect(url_for('admin_management.index'))

    admin_levels = get_enum_values('admins', 'admin_level')
    if not admin_levels:
        flash("Warning: Could not dynamically load admin levels. Using defaults.", "warning")
        admin_levels = ['standard', 'super', 'read_only']

    return render_template(
        'Admin_Portal/Admins/add_admin_step2.html',
        user=user_info,
        admin_levels=admin_levels
    )

@admin_management.route('/admin/admins/add/step2/<int:user_id>', methods=['POST'])
@login_required
def add_admin_step2(user_id):
    """Processes Step 2: Updates the admin level."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    admin_level = request.form.get('admin_level')
    current_app.logger.info(f"Step 2 (POST): Received level '{admin_level}' for user_id = {user_id}")

    admin_levels_valid = get_enum_values('admins', 'admin_level') or ['standard', 'super', 'read_only']

    if not admin_level or admin_level not in admin_levels_valid:
        flash("Invalid or missing admin level selected.", "danger")
        user_info = get_user_basic_info(user_id)
        if not user_info:
            current_app.logger.error(f"Step 2 (POST): User info lost for ID {user_id} on validation fail.")
            return redirect(url_for('admin_management.index'))
        return render_template(
            'Admin_Portal/Admins/add_admin_step2.html',
            user=user_info,
            admin_levels=admin_levels_valid,
            selected_level=admin_level
        )

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for step 2 update")
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE admins SET admin_level = %s WHERE user_id = %s
        """, (admin_level, user_id))

        rows_affected = cursor.rowcount
        connection.commit()

        if rows_affected == 0:
             current_app.logger.warning(f"Step 2 (POST): Update admin level for user {user_id} affected 0 rows. Trigger might have failed or record deleted.")
             flash("Warning: Admin level could not be set. The admin record might not exist (trigger issue?) or the level was unchanged.", "warning")
             return redirect(url_for('admin_management.add_admin_step2_form', user_id=user_id))
        else:
            current_app.logger.info(f"Step 2 (POST): Successfully updated admin level for user {user_id} to '{admin_level}'.")
            flash("Admin created successfully with the specified level.", "success")

        return redirect(url_for('admin_management.index'))

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception as rb_err: current_app.logger.error(f"Error during rollback attempt: {rb_err}")
        flash(f"Database error setting admin level: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating admin level (step 2) for user ID {user_id}: {db_err}")
    except Exception as e:
        flash(f"Error setting admin level: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin level (step 2) for user ID {user_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

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

    admin_levels = get_enum_values('admins', 'admin_level')
    if not admin_levels:
        flash("Warning: Could not dynamically load admin levels. Using defaults.", "warning")
        admin_levels = ['standard', 'super', 'read_only']

    return render_template(
        'Admin_Portal/Admins/edit_admin.html',
        admin=admin,
        admin_levels=admin_levels
    )

@admin_management.route('/admin/admins/edit/<int:admin_id>', methods=['POST'])
@login_required
def edit_admin(admin_id):
    """Processes the editing of an admin's details (plain text pass)."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    connection = None
    cursor = None
    current_admin_data = get_admin_or_404(admin_id)
    if not current_admin_data:
        flash("Cannot edit admin: Admin not found.", "danger")
        return redirect(url_for('admin_management.index'))

    admin_data_for_render = current_admin_data.copy()
    redirect_target = url_for('admin_management.index')
    admin_levels_for_render = get_enum_values('admins', 'admin_level') or ['standard', 'super', 'read_only']

    try:
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone') or None
        admin_level = request.form.get('admin_level')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        admin_data_for_render.update({
             'first_name': first_name, 'last_name': last_name, 'email': email,
             'phone': phone, 'admin_level': admin_level
        })

        if not all([first_name, last_name, email]):
             flash("Missing required fields (First Name, Last Name, Email).", "danger")
             return render_template('Admin_Portal/Admins/edit_admin.html',
                                    admin=admin_data_for_render, admin_levels=admin_levels_for_render)

        if admin_level not in admin_levels_for_render:
            flash(f"Invalid admin level selected: {admin_level}", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render)

        update_password = False
        if new_password or confirm_password:
            if not new_password or not confirm_password:
                 flash("Both New Password and Confirm Password are required to change the password.", "warning")
                 return render_template('Admin_Portal/Admins/edit_admin.html',
                                        admin=admin_data_for_render, admin_levels=admin_levels_for_render)
            elif new_password != confirm_password:
                flash("New passwords do not match.", "danger")
                return render_template('Admin_Portal/Admins/edit_admin.html',
                                        admin=admin_data_for_render, admin_levels=admin_levels_for_render)
            else:
                update_password = True

        connection = get_db_connection()
        if not connection or not connection.is_connected():
            raise ConnectionError("DB connection failed for edit admin")
        cursor = connection.cursor()

        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, admin_id))
        existing_email_user = cursor.fetchone()
        if existing_email_user:
            flash("Email address already in use by another user.", "danger")
            return render_template('Admin_Portal/Admins/edit_admin.html',
                                   admin=admin_data_for_render, admin_levels=admin_levels_for_render)

        user_update_query = """
            UPDATE users SET first_name = %s, last_name = %s, email = %s, phone = %s
        """
        user_params = [first_name, last_name, email, phone]
        if update_password:
            user_update_query += ", password = %s"
            user_params.append(new_password)
        user_update_query += " WHERE user_id = %s AND user_type = 'admin'"
        user_params.append(admin_id)

        cursor.execute(user_update_query, tuple(user_params))
        user_rows_affected = cursor.rowcount

        if admin_level != current_admin_data.get('admin_level') or user_rows_affected > 0 or update_password:
             cursor.execute("""
                 UPDATE admins SET admin_level = %s WHERE user_id = %s
             """, (admin_level, admin_id))
             admin_rows_affected = cursor.rowcount
        else:
             admin_rows_affected = 0

        connection.commit()

        if user_rows_affected > 0 or admin_rows_affected > 0:
            flash_msg = "Admin updated successfully"
            if update_password: flash_msg += " (Password Changed)"
            flash(flash_msg, "success")
        else:
            flash("No changes detected for the admin.", "info")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception: pass
        flash(f"Database error updating admin: {db_err}", "danger")
        current_app.logger.error(f"DB Error updating admin {admin_id}: {db_err}")
    except Exception as e:
        flash(f"Error updating admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error updating admin {admin_id}: {e}")
        if "connection" not in str(e).lower():
            try:
                 return render_template('Admin_Portal/Admins/edit_admin.html',
                                        admin=admin_data_for_render, admin_levels=admin_levels_for_render)
            except Exception as render_err:
                 current_app.logger.error(f"Error rendering edit_admin template after non-db error: {render_err}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(redirect_target)


# --- Delete Admin ---

@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['GET'])
@login_required
def delete_admin_form(admin_id):
    """Displays the confirmation page before deleting an admin."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # --- FIX: Use 'id' attribute and convert to int ---
    current_user_id_str = getattr(current_user, 'id', None) # Attempt to get 'id'
    current_user_id = None
    if current_user_id_str is not None:
        try:
            current_user_id = int(current_user_id_str)
        except (ValueError, TypeError):
            flash("Could not identify current user (invalid ID type).", "danger")
            current_app.logger.error(f"Current user ID '{current_user_id_str}' from current_user.id is not an integer.")
            return redirect(url_for('admin_management.index'))
    # ---------------------------------------------------

    if current_user_id is None:
        # Log details if ID couldn't be retrieved
        current_app.logger.warning(f"Could not identify current user in delete_admin_form. current_user object: {current_user}, authenticated: {current_user.is_authenticated}, attributes: {dir(current_user)}")
        flash("Could not identify current user.", "danger")
        return redirect(url_for('admin_management.index'))

    if admin_id == current_user_id:
       flash("You cannot delete your own admin account.", "danger")
       return redirect(url_for('admin_management.index'))

    admin = get_admin_or_404(admin_id)
    if not admin:
        flash("Admin not found.", "danger")
        return redirect(url_for('admin_management.index'))
    return render_template('Admin_Portal/Admins/delete_confirmation.html', admin=admin)


@admin_management.route('/admin/admins/delete/<int:admin_id>', methods=['POST'])
@login_required
def delete_admin(admin_id):
    """Processes the deletion of an admin."""
    if current_user.user_type != "admin":
        flash("Access denied", "danger")
        return redirect(url_for('login.login'))

    # --- FIX: Use 'id' attribute and convert to int ---
    current_user_id_str = getattr(current_user, 'id', None) # Attempt to get 'id'
    current_user_id = None
    if current_user_id_str is not None:
        try:
            current_user_id = int(current_user_id_str)
        except (ValueError, TypeError):
            flash("Could not identify current user for delete check (invalid ID type).", "danger")
            current_app.logger.error(f"Current user ID '{current_user_id_str}' from current_user.id for delete check is not an integer.")
            return redirect(url_for('admin_management.index'))
    # ---------------------------------------------------

    if current_user_id is None:
        current_app.logger.warning(f"Could not identify current user in delete_admin POST. current_user object: {current_user}, authenticated: {current_user.is_authenticated}, attributes: {dir(current_user)}")
        flash("Could not identify current user for delete check.", "danger")
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

        # Delete from admins table first
        cursor.execute("DELETE FROM admins WHERE user_id = %s", (admin_id,))
        admin_rows_deleted = cursor.rowcount

        # Then delete from users table
        cursor.execute("DELETE FROM users WHERE user_id = %s AND user_type = 'admin'", (admin_id,))
        user_rows_deleted = cursor.rowcount

        connection.commit()

        if user_rows_deleted == 0:
             flash("Admin user record not found or already deleted.", "warning")
             current_app.logger.warning(f"Delete request for non-existent admin user ID {admin_id} or wrong user_type.")
        else:
            flash("Admin deleted successfully.", "success")
            current_app.logger.info(f"Successfully deleted admin user ID {admin_id}.")
            if admin_rows_deleted == 0:
                 current_app.logger.warning(f"Admin user {admin_id} deleted, but no corresponding record found in 'admins' table.")

    except mysql.connector.Error as db_err:
        try:
            if connection and connection.is_connected(): connection.rollback()
        except Exception: pass
        flash(f"Database error deleting admin: {db_err}", "danger")
        current_app.logger.error(f"DB Error deleting admin {admin_id}: {db_err}")
    except Exception as e:
        flash(f"Error deleting admin: {str(e)}", "danger")
        current_app.logger.error(f"Non-DB Error deleting admin {admin_id}: {e}")
    finally:
        if cursor: cursor.close()
        if connection and connection.is_connected(): connection.close()

    return redirect(url_for('admin_management.index'))