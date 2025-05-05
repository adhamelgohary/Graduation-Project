# routes/Admin_Portal/structure_management.py

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app
)
from flask_login import login_required # Assuming you have user roles check elsewhere or use specific admin decorator
import mysql.connector
from db import get_db_connection

# Assuming you have an admin_required decorator
# from ..decorators import admin_required
# If not, ensure proper checks within routes

structure_bp = Blueprint(
    'admin_structure',
    __name__,
    url_prefix='/admin/structure', # Define a base URL prefix for these routes
    template_folder='../../templates' # Point to base templates folder
)

# --- Helper Functions ---

def get_all_departments():
    """Fetches all departments ordered by name."""
    conn = None
    cursor = None
    departments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM departments ORDER BY name ASC")
        departments = cursor.fetchall()
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching all departments: {err}")
        flash("Error retrieving departments from database.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return departments

def get_all_specializations_with_dept_name():
    """Fetches all specializations with their associated department name."""
    conn = None
    cursor = None
    specializations = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.specialization_id, s.name, s.description, s.department_id, d.name as department_name
            FROM specializations s
            LEFT JOIN departments d ON s.department_id = d.department_id
            ORDER BY s.name ASC
        """
        cursor.execute(query)
        specializations = cursor.fetchall()
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching all specializations: {err}")
        flash("Error retrieving specializations from database.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specializations

def get_department(dept_id):
    """Fetches a single department by ID."""
    conn = None; cursor = None; department = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM departments WHERE department_id = %s", (dept_id,))
        department = cursor.fetchone()
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching department {dept_id}: {err}")
        flash(f"Error retrieving department {dept_id}.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

def get_specialization(spec_id):
    """Fetches a single specialization by ID."""
    conn = None; cursor = None; specialization = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM specializations WHERE specialization_id = %s", (spec_id,))
        specialization = cursor.fetchone()
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching specialization {spec_id}: {err}")
        flash(f"Error retrieving specialization {spec_id}.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specialization

# --- Routes ---

@structure_bp.route('/')
@login_required
# @admin_required # Add your admin check decorator here
def manage_structure():
    """Displays the main page for managing departments and specializations."""
    # Check if user is admin if not using decorator
    # if not current_user.is_admin(): abort(403)

    departments = get_all_departments()
    specializations = get_all_specializations_with_dept_name()
    return render_template(
        'Admin_Portal/structure/manage_structure.html',
        departments=departments,
        specializations=specializations
    )

# --- Department Routes ---

@structure_bp.route('/departments/add', methods=['POST'])
@login_required
# @admin_required
def add_department():
    # if not current_user.is_admin(): abort(403)
    name = request.form.get('department_name', '').strip()
    description = request.form.get('department_description', '').strip() or None
    # Handle image filename later if needed

    if not name:
        flash("Department name is required.", "danger")
        return redirect(url_for('.manage_structure'))

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO departments (name, description) VALUES (%s, %s)", (name, description))
        conn.commit()
        flash(f"Department '{name}' added successfully.", "success")
    except mysql.connector.Error as err:
        conn.rollback()
        current_app.logger.error(f"Error adding department: {err}")
        if err.errno == 1062: # Duplicate entry
            flash(f"Error: Department name '{name}' already exists.", "danger")
        else:
            flash(f"Database error adding department: {err.msg}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure'))

@structure_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_department(dept_id):
    # if not current_user.is_admin(): abort(403)
    conn = None; cursor = None

    if request.method == 'POST':
        name = request.form.get('department_name', '').strip()
        description = request.form.get('department_description', '').strip() or None
        # Handle image filename update later if needed

        if not name:
            flash("Department name cannot be empty.", "danger")
            # Fetch department again to re-render form with error
            department = get_department(dept_id)
            if not department: return redirect(url_for('.manage_structure')) # Redirect if GET somehow fails
            return render_template('Admin_Portal/structure/edit_department.html', department=department)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE departments SET name = %s, description = %s, updated_at = NOW() WHERE department_id = %s",
                (name, description, dept_id)
            )
            conn.commit()
            flash(f"Department '{name}' updated successfully.", "success")
            return redirect(url_for('.manage_structure'))
        except mysql.connector.Error as err:
            conn.rollback()
            current_app.logger.error(f"Error updating department {dept_id}: {err}")
            if err.errno == 1062:
                flash(f"Error: Department name '{name}' already exists.", "danger")
            else:
                flash(f"Database error updating department: {err.msg}", "danger")
            # Fetch department again to re-render form with error
            department = get_department(dept_id)
            if not department: return redirect(url_for('.manage_structure'))
            return render_template('Admin_Portal/structure/edit_department.html', department=department)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

    # GET Request
    department = get_department(dept_id)
    if not department:
        flash("Department not found.", "warning")
        return redirect(url_for('.manage_structure'))
    return render_template('Admin_Portal/structure/edit_department.html', department=department)


@structure_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
# @admin_required
def delete_department(dept_id):
    # if not current_user.is_admin(): abort(403)
    conn = None; cursor = None
    try:
        # Optional: Check if department is used by any specializations before deleting
        # query = "SELECT COUNT(*) as count FROM specializations WHERE department_id = %s"
        # cursor.execute(query, (dept_id,))
        # spec_count = cursor.fetchone()['count']
        # if spec_count > 0:
        #    flash(f"Cannot delete department: It is linked to {spec_count} specialization(s). Unlink them first.", "warning")
        #    return redirect(url_for('.manage_structure'))

        conn = get_db_connection()
        cursor = conn.cursor()
        # Schema sets FK to NULL on delete, so this should be safe
        cursor.execute("DELETE FROM departments WHERE department_id = %s", (dept_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Department deleted successfully. Associated specializations are now unlinked.", "success")
        else:
            flash("Department not found or already deleted.", "warning")
    except mysql.connector.Error as err:
        conn.rollback()
        current_app.logger.error(f"Error deleting department {dept_id}: {err}")
        flash(f"Database error deleting department: {err.msg}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure'))


# --- Specialization Routes ---

@structure_bp.route('/specializations/add', methods=['POST'])
@login_required
# @admin_required
def add_specialization():
    # if not current_user.is_admin(): abort(403)
    name = request.form.get('specialization_name', '').strip()
    description = request.form.get('specialization_description', '').strip() or None
    department_id_str = request.form.get('department_id', '').strip()

    if not name:
        flash("Specialization name is required.", "danger")
        return redirect(url_for('.manage_structure') + '#specializations-section') # Jump to section

    department_id = None
    if department_id_str:
        try:
            department_id = int(department_id_str)
        except ValueError:
            flash("Invalid Department selected.", "danger")
            return redirect(url_for('.manage_structure') + '#specializations-section')

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO specializations (name, description, department_id) VALUES (%s, %s, %s)",
            (name, description, department_id) # department_id can be None
        )
        conn.commit()
        flash(f"Specialization '{name}' added successfully.", "success")
    except mysql.connector.Error as err:
        conn.rollback()
        current_app.logger.error(f"Error adding specialization: {err}")
        if err.errno == 1062: # Duplicate entry
            flash(f"Error: Specialization name '{name}' already exists.", "danger")
        elif err.errno == 1452: # FK constraint violation
             flash(f"Error: Invalid Department selected.", "danger")
        else:
            flash(f"Database error adding specialization: {err.msg}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure') + '#specializations-section')

@structure_bp.route('/specializations/<int:spec_id>/edit', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_specialization(spec_id):
    # if not current_user.is_admin(): abort(403)
    conn = None; cursor = None

    if request.method == 'POST':
        name = request.form.get('specialization_name', '').strip()
        description = request.form.get('specialization_description', '').strip() or None
        department_id_str = request.form.get('department_id', '').strip()

        if not name:
            flash("Specialization name cannot be empty.", "danger")
            # Fetch data again for re-render
            specialization = get_specialization(spec_id)
            departments = get_all_departments()
            if not specialization: return redirect(url_for('.manage_structure'))
            return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)

        department_id = None
        if department_id_str:
            try:
                department_id = int(department_id_str)
            except ValueError:
                flash("Invalid Department selected.", "danger")
                specialization = get_specialization(spec_id)
                departments = get_all_departments()
                if not specialization: return redirect(url_for('.manage_structure'))
                return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE specializations SET
                   name = %s, description = %s, department_id = %s, updated_at = NOW()
                   WHERE specialization_id = %s""",
                (name, description, department_id, spec_id)
            )
            conn.commit()
            flash(f"Specialization '{name}' updated successfully.", "success")
            return redirect(url_for('.manage_structure') + '#specializations-section')
        except mysql.connector.Error as err:
            conn.rollback()
            current_app.logger.error(f"Error updating specialization {spec_id}: {err}")
            if err.errno == 1062:
                flash(f"Error: Specialization name '{name}' already exists.", "danger")
            elif err.errno == 1452:
                 flash(f"Error: Invalid Department selected.", "danger")
            else:
                flash(f"Database error updating specialization: {err.msg}", "danger")
            # Fetch data again for re-render
            specialization = get_specialization(spec_id)
            departments = get_all_departments()
            if not specialization: return redirect(url_for('.manage_structure'))
            return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

    # GET Request
    specialization = get_specialization(spec_id)
    if not specialization:
        flash("Specialization not found.", "warning")
        return redirect(url_for('.manage_structure'))

    departments = get_all_departments() # Need list for dropdown
    return render_template(
        'Admin_Portal/structure/edit_specialization.html',
        specialization=specialization,
        departments=departments
    )

@structure_bp.route('/specializations/<int:spec_id>/delete', methods=['POST'])
@login_required
# @admin_required
def delete_specialization(spec_id):
    # if not current_user.is_admin(): abort(403)
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # IMPORTANT: Doctors FK uses ON DELETE RESTRICT. Deletion will fail if doctors use this spec.
        cursor.execute("DELETE FROM specializations WHERE specialization_id = %s", (spec_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Specialization deleted successfully.", "success")
        else:
            flash("Specialization not found or already deleted.", "warning")
    except mysql.connector.Error as err:
        conn.rollback()
        current_app.logger.error(f"Error deleting specialization {spec_id}: {err}")
        if err.errno == 1451: # FK constraint fail (likely doctors linked)
             flash(f"Cannot delete specialization: It is currently assigned to one or more doctors. Reassign doctors first.", "danger")
        else:
            flash(f"Database error deleting specialization: {err.msg}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure') + '#specializations-section')