# routes/Admin_Portal/structure_management.py

import os
import uuid
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app
)
from flask_login import login_required
import mysql.connector
from werkzeug.utils import secure_filename
from db import get_db_connection

# --- Use config keys set by directory_configs.py ---
UPLOAD_FOLDER_CONFIG_KEY = 'UPLOAD_FOLDER_DEPARTMENTS'
ALLOWED_EXTENSIONS_CONFIG_KEY = 'ALLOWED_IMAGE_EXTENSIONS'
STATIC_FOLDER_CONFIG_KEY = 'STATIC_FOLDER' # Key for the static folder path

# ... (keep admin_required check comment or implementation) ...

structure_bp = Blueprint(
    'admin_structure',
    __name__,
    url_prefix='/admin/structure',
    template_folder='../../templates'
)

# --- File Handling Helper Functions (No changes needed here) ---

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def generate_secure_filename(original_filename):
    extension = original_filename.rsplit('.', 1)[1].lower()
    unique_id = uuid.uuid4().hex
    safe_original_name = secure_filename(original_filename.rsplit('.', 1)[0])
    safe_original_name = safe_original_name[:50] if len(safe_original_name) > 50 else safe_original_name
    return f"{safe_original_name}_{unique_id}.{extension}"

def delete_existing_image(filename_db_path): # Removed config_key argument
    """Safely deletes an existing image file using app config."""
    if not filename_db_path:
        return False

    # Get folder paths from app config
    upload_folder = current_app.config.get(UPLOAD_FOLDER_CONFIG_KEY) # Use department key specifically
    static_folder = current_app.config.get(STATIC_FOLDER_CONFIG_KEY)

    if not upload_folder or not static_folder:
        current_app.logger.error(f"Upload/Static folder key not configured ('{UPLOAD_FOLDER_CONFIG_KEY}' or '{STATIC_FOLDER_CONFIG_KEY}'). Cannot delete file.")
        return False

    try:
        # Construct full path using static folder and the relative DB path
        full_path = os.path.join(static_folder, filename_db_path)

        if os.path.exists(full_path) and os.path.isfile(full_path):
            os.remove(full_path)
            current_app.logger.info(f"Deleted existing file: {full_path}")
            return True
        else:
            # It's okay if file doesn't exist (might have been manually deleted)
            current_app.logger.warning(f"File to delete not found at: {full_path} (DB path: {filename_db_path})")
            return False # Indicate file wasn't found to delete
    except OSError as e:
        current_app.logger.error(f"Error deleting file {full_path}: {e}")
        return False
    except Exception as e:
         current_app.logger.error(f"Unexpected error constructing path or deleting file {filename_db_path}: {e}")
         return False


# --- Database Helper Functions (No changes needed here) ---
# ... (get_all_departments, get_all_specializations_with_dept_name, get_department, get_specialization remain the same) ...
def get_all_departments():
    """Fetches all departments ordered by name."""
    conn = None; cursor = None; departments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT department_id, name, description, image_filename FROM departments ORDER BY name ASC")
        departments = cursor.fetchall()
        # Construct full URL for images
        for dept in departments:
            if dept.get('image_filename'):
                dept['image_url'] = url_for('static', filename=dept['image_filename'])
            else:
                dept['image_url'] = url_for('static', filename='Admin_Portal/images/dept_placeholder.png') # Default image
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching all departments: {err}")
        flash("Error retrieving departments from database.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return departments

def get_all_specializations_with_dept_name():
    """Fetches all specializations with their associated department name."""
    conn = None; cursor = None; specializations = []
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
    """Fetches a single department by ID, adding image URL."""
    conn = None; cursor = None; department = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM departments WHERE department_id = %s", (dept_id,))
        department = cursor.fetchone()
        if department:
             if department.get('image_filename'):
                 department['image_url'] = url_for('static', filename=department['image_filename'])
             else:
                 department['image_url'] = url_for('static', filename='Admin_Portal/images/dept_placeholder.png') # Default
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
# @admin_required
def manage_structure():
    # ... (no changes needed) ...
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
    # ... (variable retrieval) ...
    name = request.form.get('department_name', '').strip()
    description = request.form.get('department_description', '').strip() or None
    image_file = request.files.get('department_image')

    if not name:
        flash("Department name is required.", "danger")
        return redirect(url_for('.manage_structure'))

    conn = None; cursor = None
    saved_filename_db_path = None
    saved_filepath_full = None
    upload_error = False

    # --- Handle File Upload ---
    if image_file and image_file.filename != '':
        # Get config values using the defined keys
        allowed_extensions = current_app.config.get(ALLOWED_EXTENSIONS_CONFIG_KEY)
        upload_folder = current_app.config.get(UPLOAD_FOLDER_CONFIG_KEY)
        static_folder = current_app.config.get(STATIC_FOLDER_CONFIG_KEY)

        if not upload_folder or not static_folder:
            flash("Server configuration error: Upload/Static folder not set.", "danger")
            upload_error = True
        elif allowed_extensions and allowed_file(image_file.filename, allowed_extensions):
            try:
                secure_name = generate_secure_filename(image_file.filename)
                saved_filepath_full = os.path.join(upload_folder, secure_name)
                # Calculate DB path relative to static folder
                relative_folder = os.path.relpath(upload_folder, static_folder)
                saved_filename_db_path = os.path.join(relative_folder, secure_name).replace(os.path.sep, '/')

                # os.makedirs already handled by configure_directories
                image_file.save(saved_filepath_full)
                current_app.logger.info(f"Department image saved to: {saved_filepath_full}")
            except Exception as e:
                current_app.logger.error(f"Error saving department image: {e}", exc_info=True)
                flash("Error saving uploaded image.", "danger")
                upload_error = True
        else:
            flash("Invalid image file type. Allowed types: {}".format(', '.join(allowed_extensions or [])), "danger")
            upload_error = True

    if upload_error:
        return redirect(url_for('.manage_structure'))
    # --- End File Upload Handling ---

    # --- Database Insert ---
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO departments (name, description, image_filename) VALUES (%s, %s, %s)",
            (name, description, saved_filename_db_path)
        )
        conn.commit()
        flash(f"Department '{name}' added successfully.", "success")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error adding department to DB: {err}")
        if err.errno == 1062: flash(f"Error: Department name '{name}' already exists.", "danger")
        else: flash(f"Database error adding department: {err.msg}", "danger")
        # Cleanup orphaned file
        if saved_filepath_full and os.path.exists(saved_filepath_full):
             if delete_existing_image(saved_filename_db_path): # Call helper
                 current_app.logger.warning(f"Orphaned file deleted after DB error: {saved_filepath_full}")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error adding department: {e}", exc_info=True)
        flash("An unexpected error occurred while adding the department.", "danger")
        if saved_filepath_full and os.path.exists(saved_filepath_full):
             if delete_existing_image(saved_filename_db_path):
                 current_app.logger.warning(f"Orphaned file deleted after unexpected error: {saved_filepath_full}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure'))


@structure_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_department(dept_id):
    # ... (variable retrieval) ...
    conn = None; cursor = None
    if request.method == 'POST':
        name = request.form.get('department_name', '').strip()
        description = request.form.get('department_description', '').strip() or None
        image_file = request.files.get('department_image')
        delete_image_flag = request.form.get('delete_image') == '1'

        if not name:
            flash("Department name cannot be empty.", "danger")
            department = get_department(dept_id)
            return render_template('Admin_Portal/structure/edit_department.html', department=department)

        new_image_db_path = None
        upload_error = False
        saved_filepath_full = None

        current_department_data = get_department(dept_id)
        if not current_department_data:
            flash("Department not found.", "warning")
            return redirect(url_for('.manage_structure'))
        current_image_db_path = current_department_data.get('image_filename')

        # --- Handle Image Update/Deletion ---
        if delete_image_flag:
            if current_image_db_path:
                if delete_existing_image(current_image_db_path):
                    new_image_db_path = None
                    flash("Current image marked for deletion.", "info")
                else:
                    flash("Failed to delete current image file, update aborted.", "warning")
                    # Re-render form without proceeding to DB update
                    department = get_department(dept_id)
                    return render_template('Admin_Portal/structure/edit_department.html', department=department)
            else:
                new_image_db_path = None # Was already null
        elif image_file and image_file.filename != '':
            allowed_extensions = current_app.config.get(ALLOWED_EXTENSIONS_CONFIG_KEY)
            upload_folder = current_app.config.get(UPLOAD_FOLDER_CONFIG_KEY)
            static_folder = current_app.config.get(STATIC_FOLDER_CONFIG_KEY)

            if not upload_folder or not static_folder:
                flash("Server configuration error: Upload/Static folder not set.", "danger")
                upload_error = True
            elif allowed_extensions and allowed_file(image_file.filename, allowed_extensions):
                try:
                    secure_name = generate_secure_filename(image_file.filename)
                    saved_filepath_full = os.path.join(upload_folder, secure_name)
                    relative_folder = os.path.relpath(upload_folder, static_folder)
                    new_image_db_path = os.path.join(relative_folder, secure_name).replace(os.path.sep, '/')

                    # os.makedirs already handled by configure_directories
                    image_file.save(saved_filepath_full)
                    current_app.logger.info(f"New department image saved: {saved_filepath_full}")
                    # Delete OLD image only if new one saved successfully
                    if current_image_db_path:
                         delete_existing_image(current_image_db_path)
                except Exception as e:
                    current_app.logger.error(f"Error saving updated department image: {e}", exc_info=True)
                    flash("Error saving uploaded image.", "danger")
                    upload_error = True
                    new_image_db_path = current_image_db_path # Revert to old path
            else:
                flash("Invalid new image file type. Allowed types: {}".format(', '.join(allowed_extensions or [])), "danger")
                upload_error = True
                new_image_db_path = current_image_db_path
        else:
            new_image_db_path = current_image_db_path # Keep current

        if upload_error:
             department = get_department(dept_id)
             return render_template('Admin_Portal/structure/edit_department.html', department=department)
        # --- End Image Update/Deletion ---

        # --- Database Update ---
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE departments SET
                   name = %s, description = %s, image_filename = %s, updated_at = NOW()
                   WHERE department_id = %s""",
                (name, description, new_image_db_path, dept_id)
            )
            conn.commit()
            flash(f"Department '{name}' updated successfully.", "success")
            return redirect(url_for('.manage_structure'))
        except mysql.connector.Error as err:
            # ... (keep DB error handling, log potential file inconsistencies) ...
            if conn: conn.rollback()
            current_app.logger.error(f"Error updating department {dept_id} in DB: {err}")
            if err.errno == 1062: flash(f"Error: Department name '{name}' already exists.", "danger")
            else: flash(f"Database error updating department: {err.msg}", "danger")
            # Log potential inconsistencies
            if saved_filepath_full and os.path.exists(saved_filepath_full) and new_image_db_path != current_image_db_path:
                 current_app.logger.warning(f"DB error after file operations for dept {dept_id}. New file '{saved_filepath_full}' might be orphaned.")
            elif delete_image_flag and new_image_db_path is None and current_image_db_path is not None: # Check if delete seemed successful file-wise but DB failed
                 current_app.logger.warning(f"DB error after deleting image for dept {dept_id}. File deleted but DB not updated.")

            department = get_department(dept_id) # Refetch for template
            return render_template('Admin_Portal/structure/edit_department.html', department=department)
        except Exception as e:
             # ... (keep general exception handling) ...
            if conn: conn.rollback()
            current_app.logger.error(f"Unexpected error updating department {dept_id}: {e}", exc_info=True)
            flash("An unexpected error occurred while updating.", "danger")
            department = get_department(dept_id) # Refetch for template
            return render_template('Admin_Portal/structure/edit_department.html', department=department)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()

    # --- GET Request ---
    department = get_department(dept_id)
    if not department:
        flash("Department not found.", "warning")
        return redirect(url_for('.manage_structure'))
    return render_template('Admin_Portal/structure/edit_department.html', department=department)


@structure_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
# @admin_required
def delete_department(dept_id):
    # ... (Get image filename before deleting DB record) ...
    conn = None; cursor = None
    department_data = get_department(dept_id)
    image_to_delete_db_path = department_data.get('image_filename') if department_data else None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM departments WHERE department_id = %s", (dept_id,))
        conn.commit()

        if cursor.rowcount > 0:
            flash("Department deleted successfully. Associated specializations are now unlinked.", "success")
            # Delete image file AFTER DB success
            if image_to_delete_db_path:
                delete_existing_image(image_to_delete_db_path) # Call helper
        else:
            flash("Department not found or already deleted.", "warning")
    # ... (keep error handling) ...
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting department {dept_id}: {err}")
        flash(f"Database error deleting department: {err.msg}", "danger")
    except Exception as e:
         if conn: conn.rollback()
         current_app.logger.error(f"Unexpected error deleting department {dept_id}: {e}", exc_info=True)
         flash("An unexpected error occurred during deletion.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    return redirect(url_for('.manage_structure'))


# --- Specialization Routes (No changes needed) ---
# ... (keep add_specialization, edit_specialization, delete_specialization as they were) ...
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