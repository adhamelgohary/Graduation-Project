# search_users.py (Consolidated)
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from db import get_db_connection
from math import ceil
import mysql.connector
from functools import wraps # Added wraps

# Import helpers if they exist in other modules
try:
    # Example: Use setting helper if defined elsewhere
    from .Appointments import get_int_setting
except ImportError:
    # Fallback
    def get_int_setting(key, default=0):
        try: return int(request.args.get(key, default)) # Simple fallback using request args
        except (ValueError, TypeError): return default
    current_app.logger.warning("Could not import get_int_setting helper in search_users.")


search_users_bp = Blueprint('search_users', __name__, url_prefix='/admin/search')

# --- Constants ---
ITEMS_PER_PAGE = 15 # Default items per page

# --- Decorator ---
def require_admin(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.user_type != "admin":
            flash("Access denied.", "danger")
            return redirect(url_for('login.login_route')) # Adjust login route
        return func(*args, **kwargs)
    return decorated_view

@search_users_bp.route('/users', methods=['GET'])
@require_admin # Apply decorator
def search_users():
    """ Handles global user search and displays results. """
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', '').strip()
    per_page = get_int_setting('default_items_per_page', ITEMS_PER_PAGE) # Use setting

    conn = None; cursor = None
    users = []; total_items = 0; total_pages = 0
    executed_search = bool(search_term)

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected(): raise ConnectionError("DB connection failed")
        cursor = conn.cursor(dictionary=True)

        base_query = "FROM users WHERE 1=1"
        params = []
        search_clause = ""

        if executed_search:
            search_clause = " AND (first_name LIKE %s OR last_name LIKE %s OR email LIKE %s OR username LIKE %s OR phone LIKE %s OR user_type LIKE %s OR account_status LIKE %s) " # Added status search
            like_term = f"%{search_term}%"; params.extend([like_term] * 7) # Match fields

        count_query = f"SELECT COUNT(user_id) as total {base_query} {search_clause}"
        cursor.execute(count_query, tuple(params)); result = cursor.fetchone()
        total_items = result['total'] if result else 0
        total_pages = ceil(total_items / per_page) if per_page > 0 else 0
        if page > total_pages and total_pages > 0: page = total_pages
        offset = (page - 1) * per_page

        data_query = f""" SELECT user_id, username, first_name, last_name, email, user_type, phone, created_at, account_status {base_query} {search_clause} ORDER BY user_type ASC, last_name ASC, first_name ASC LIMIT %s OFFSET %s """
        cursor.execute(data_query, tuple(params + [per_page, offset])); users = cursor.fetchall()

        if not users and executed_search:
            flash("No users found matching search.", "info")

    except Exception as e:
        flash("Error during user search.", "danger")
        current_app.logger.error(f"Error search users '{search_term}': {e}", exc_info=True)
        executed_search = False; users = []; total_items = 0; total_pages = 0
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template(
        'Admin_Portal/Search/search_page.html',
        users=users, page=page, total_pages=total_pages, per_page=per_page,
        total_items=total_items, search_term=search_term, executed_search=executed_search
    )