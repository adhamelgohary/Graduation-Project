# routes/Website/department.py

from flask import Blueprint, render_template, current_app, abort, url_for
import mysql.connector
import sys
import os
import re # Import regex for potential cleanup

# --- Database Connection Setup ---
# ... (keep as is) ...
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from db import get_db_connection
except ImportError:
    try:
        from db import get_db_connection
    except ImportError:
        print("CRITICAL ERROR: Failed to import get_db_connection. Check PYTHONPATH and db.py location.", file=sys.stderr)
        def get_db_connection():
            print("CRITICAL ERROR: get_db_connection is not available.", file=sys.stderr)
            return None

# --- Import Shared Functions ---
# ... (keep as is) ...
try:
    from .home import get_all_departments_from_db
except ImportError as e:
    print(f"WARNING: Could not import get_all_departments_from_db from .home. Error: {e}", file=sys.stderr)
    def get_all_departments_from_db():
        if current_app:
             current_app.logger.warning("Using fallback get_all_departments_from_db due to import error.")
        else:
             print("WARNING: Using fallback get_all_departments_from_db due to import error.", file=sys.stderr)
        return []


# --- Blueprint Definition ---
# ... (keep as is) ...
department_bp = Blueprint(
    'department',
    __name__,
    template_folder='../../templates',
    url_prefix='/departments'
)

# --- Helper: Simple Text Snippet Generation ---
def create_snippet(text, max_length=250, indicator="..."):
    """
    Creates a snippet from text if it exceeds max_length.
    Tries to break cleanly at sentence ends or spaces near the limit.
    Returns the snippet and a boolean indicating if more content exists.
    """
    if not text or len(text) <= max_length:
        return text, False # No snippet needed or text is short

    # Try to find a sentence end near the max_length
    end_sentence = text.rfind('.', 0, max_length + 1)
    if end_sentence > max_length * 0.7: # Found a sentence end reasonably close
        snippet = text[:end_sentence + 1]
        return snippet, True

    # Try to find a space near the max_length
    end_space = text.rfind(' ', 0, max_length + 1)
    if end_space > max_length * 0.7: # Found a space reasonably close
         snippet = text[:end_space] + indicator
         return snippet, True

    # Fallback: hard cut
    snippet = text[:max_length] + indicator
    return snippet, True

# --- Helper Functions ---

def get_department_by_id(dept_id):
    # ... (keep as is - no changes needed here for read more) ...
    """Fetches department details by ID, adds image URL and specific theme info."""
    department = None
    conn = None
    cursor = None
    logger = current_app.logger if current_app else print
    log_method_error = logger.error if hasattr(logger, 'error') else logger
    log_method_exception = logger.exception if hasattr(logger, 'exception') else logger

    try:
        conn = get_db_connection()
        if not conn:
             log_method_error(f"Failed to get DB connection for department ID {dept_id}")
             return None
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM departments WHERE department_id = %s"
        cursor.execute(query, (dept_id,))
        department = cursor.fetchone()

        if department:
            # Image URL construction using url_for (keep for images)
            db_filename = department.get('image_filename')
            department['image_url'] = url_for('static', filename=f"images/departments/{db_filename}") if db_filename else url_for('static', filename="images/departments/placeholder.jpg")

            # Theme/CSS mapping (Add your specific logic here)
            # REMOVED url_for for CSS paths - using direct strings relative to static folder
            # ASSUMPTION: CSS files are in 'static/website/' directory
            dept_name = department.get('name', '')
            if dept_name == 'Cardiology':
                department['specific_css'] = 'website/cardio.css' # FIXED
                department['hero_icon'] = 'fa-heart-pulse'
                department['hero_highlight'] = 'Cardiology'
                department['hero_main'] = 'Care'
            elif dept_name == 'Neurology':
                department['specific_css'] = 'website/neuro.css' # FIXED
                department['hero_icon'] = 'fa-brain'
                department['hero_highlight'] = 'Neurology'
                department['hero_main'] = 'Expertise'
            # Add elif blocks for other specific departments...
            else: # Default fallback
                department['specific_css'] = 'website/generic_department.css' # FIXED
                department['hero_icon'] = 'fa-stethoscope'
                department['hero_highlight'] = department.get('name', 'Medical')
                department['hero_main'] = 'Services'
                department['hero_images'] = []

    except mysql.connector.Error as db_err:
        log_method_error(f"Database error fetching department ID {dept_id}: {db_err}")
    except Exception as e:
        log_method_exception(f"Unexpected error fetching department ID {dept_id}: {e}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

# --- Routes ---

@department_bp.route('/')
def list_departments():
    # ... (keep as is) ...
    """Renders the page listing all available departments."""
    all_departments = get_all_departments_from_db()
    if not all_departments and current_app:
        current_app.logger.warning("Department list page: get_all_departments_from_db returned empty. Check logs for that function.")

    return render_template(
        'Website/Departments/department_list.html',
        departments=all_departments
    )

@department_bp.route('/<int:dept_id>/')
def department_landing(dept_id):
    # ... (keep as is) ...
    """Renders the landing page for a specific department."""
    department = get_department_by_id(dept_id)
    if not department:
        if current_app:
            current_app.logger.warning(f"Department landing page requested for non-existent ID {dept_id}.")
        abort(404, description=f"Department with ID {dept_id} not found.")

    department_conditions = get_conditions_by_department(dept_id)
    if current_app:
        current_app.logger.debug(f"Rendering landing page for dept {dept_id} ('{department.get('name')}'). Conditions found: {len(department_conditions)}")

    template_path = 'Website/Departments/department_landing.html'
    return render_template(
        template_path,
        department=department,
        conditions=department_conditions
    )

# --- End of Routes ---