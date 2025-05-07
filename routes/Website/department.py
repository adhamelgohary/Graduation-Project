# routes/Website/department.py

from flask import Blueprint, render_template, current_app, abort, url_for
import mysql.connector
import sys
import os
# from .home import get_all_departments_from_db # Import if needed for listing, or fetch directly

# --- Database Connection ---
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from db import get_db_connection
except ImportError:
    try: from db import get_db_connection
    except ImportError: get_db_connection = None; print("ERROR: Cannot import db.py")

# --- Blueprint Definition ---
department_bp = Blueprint(
    'department',
    __name__,
    template_folder='../../templates',
    url_prefix='/departments'
)

# --- Helper Function (Keep - Unchanged) ---
def get_department_by_id(dept_id):
    # ... (Keep this function as is from previous version) ...
    department = None; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM departments WHERE department_id = %s", (dept_id,))
        department = cursor.fetchone()
        if department:
            db_filename = department.get('image_filename')
            department['image_url'] = url_for('static', filename=f"uploads/department_images/{db_filename}") if db_filename else url_for('static', filename="images/departments/placeholder.jpg")
            # Add theme/CSS mapping logic if needed
            dept_name = department.get('name', '')
            if dept_name == 'Cardiology': department['specific_css'] = 'website/cardio.css'; department['hero_icon'] = 'fa-heart-pulse' # etc.
            else: department['specific_css'] = 'website/generic_department.css'; department['hero_icon'] = 'fa-stethoscope' # Default
    except Exception as e: logger.error(f"Error get_department_by_id({dept_id}): {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

# --- Helper Function (Keep - Unchanged, relative path for image) ---
def get_conditions_by_department(dept_id):
    conditions = []; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        query = "SELECT condition_id, condition_name, description, condition_image_filename FROM conditions WHERE department_id = %s AND is_active = TRUE ORDER BY condition_name ASC"
        cursor.execute(query, (dept_id,))
        results = cursor.fetchall()
        for cond_data in results:
            img_file = cond_data.get('condition_image_filename')
            # Use the serve route or direct static path
            # Option A: Dedicated route
            # cond_data['image_url'] = url_for('disease_info.serve_condition_image', image_filename_in_db=img_file) if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")
            # Option B: Direct static path (simpler if no auth needed on images)
            cond_data['image_url'] = url_for('static', filename=img_file) if img_file else url_for('static', filename="images/conditions/disease_placeholder.png")

            cond_data['name'] = cond_data.get('condition_name')
            # Short description for list display (using simple truncate here)
            desc = cond_data.get('description', '')
            cond_data['short_description'] = (desc[:100] + '...') if desc and len(desc) > 100 else desc
            conditions.append(cond_data)
    except Exception as e: logger.error(f"Error get_conditions_by_department({dept_id}): {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return conditions


# --- Helper Function (Keep - Unchanged, relative path for image) ---
def get_doctors_by_department(dept_id):
    # ... (Keep this function as is - ensure profile picture path is correct) ...
    # Make sure profile_picture_url uses the correct relative path structure (e.g., 'uploads/profile_pics/...')
    doctors = []; conn = None; cursor = None
    logger = current_app.logger if current_app else print
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        query = """SELECT u.user_id, u.first_name, u.last_name, u.profile_picture, s.name AS specialization_name, d.biography
                   FROM users u JOIN doctors d ON u.user_id = d.user_id LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                   WHERE u.user_type = 'doctor' AND u.account_status = 'active' AND d.department_id = %s AND d.verification_status = 'approved'
                   ORDER BY u.last_name ASC, u.first_name ASC"""
        cursor.execute(query, (dept_id,))
        doctors_raw = cursor.fetchall()
        for doc in doctors_raw:
            pic = doc.get('profile_picture') # This should be the relative path like 'uploads/profile_pics/...'
            doc['profile_picture_url'] = url_for('static', filename=pic) if pic else url_for('static', filename='images/profile_pics/default_avatar.png')
            bio = doc.get('biography'); doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
            doctors.append(doc)
    except Exception as e: logger.error(f"Error get_doctors_by_department({dept_id}): {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return doctors


# --- Routes ---

@department_bp.route('/')
def list_departments():
    """Renders the page listing all available departments."""
    # You might fetch departments directly here or use an imported function
    conn = None; cursor = None; all_departments = []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT department_id, name, description, image_filename FROM departments ORDER BY name ASC")
        all_departments_raw = cursor.fetchall()
        for dept in all_departments_raw:
            img = dept.get('image_filename') # Should be like 'uploads/department_images/...'
            dept['image_url'] = url_for('static', filename=img) if img else url_for('static', filename='images/departments/placeholder.jpg')
            all_departments.append(dept)
    except Exception as e: current_app.logger.error(f"Error listing departments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return render_template('Website/Departments/department_list.html', departments=all_departments)

@department_bp.route('/<int:dept_id>/')
def department_landing(dept_id):
    """Renders the landing page for a specific department."""
    department = get_department_by_id(dept_id)
    if not department: abort(404, description=f"Department ID {dept_id} not found.")
    
    department_conditions = get_conditions_by_department(dept_id)
    # Note: The template link to condition details will need updating:
    # Change url_for('department.view_condition', ...) TO url_for('disease_info.view_condition', ...)

    return render_template('Website/Departments/department_landing.html',
                           department=department,
                           conditions=department_conditions)

# REMOVED view_condition route from here