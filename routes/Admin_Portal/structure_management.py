# routes/Admin_Portal/structure_management.py

import os
import uuid
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for, current_app
)
from flask_login import login_required # Assuming you have an admin_required decorator or similar
import mysql.connector
from werkzeug.utils import secure_filename as werkzeug_secure_filename # Renamed for clarity
from db import get_db_connection

# Import the helper from directory_configs
# Adjust the import path based on your project structure if utils is not directly accessible
try:
    from utils.directory_configs import get_relative_path_for_db
except ImportError:
    current_app.logger.critical("CRITICAL: Failed to import get_relative_path_for_db from utils.directory_configs in structure_management.")
    # Define a dummy fallback if needed, or let it raise an error if this is essential
    def get_relative_path_for_db(absolute_filepath): return None


# --- Use config keys set by directory_configs.py ---
UPLOAD_FOLDER_CONFIG_KEY_DEPT = 'UPLOAD_FOLDER_DEPARTMENTS' # Specific for department images
ALLOWED_EXTENSIONS_CONFIG_KEY_IMG = 'ALLOWED_IMAGE_EXTENSIONS' # Specific for images

structure_bp = Blueprint(
    'admin_structure',
    __name__,
    url_prefix='/admin/structure',
    template_folder='../../templates' # Adjust if your templates are elsewhere (e.g., ../templates/Admin_Portal/structure)
)

# --- Admin Check (Placeholder - implement your actual admin check) ---
# from functools import wraps
# def admin_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if not getattr(current_user, 'user_type', None) == 'admin':
#             flash("You do not have permission to access this page.", "danger")
#             return redirect(url_for('login.login_route')) # Or your main dashboard
#         return f(*args, **kwargs)
#     return decorated_function

# --- File Handling Helper Functions ---

def allowed_file(filename, allowed_extensions_set): # Takes a set now
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions_set

def generate_unique_filesystem_name(original_filename): # Renamed for clarity
    """Generates a secure and unique filename for storing on the filesystem."""
    cleaned_filename = werkzeug_secure_filename(original_filename)
    base, ext = os.path.splitext(cleaned_filename)
    base = base[:100] if base else "image" # Ensure base is not empty and limit length
    return f"{uuid.uuid4().hex}_{base}{ext}"

def delete_existing_image_file(db_relative_path):
    """
    Safely deletes an existing image file.
    Assumes db_relative_path is the path stored in DB, relative to the static folder.
    e.g., "uploads/department_images/image.jpg"
    """
    if not db_relative_path:
        return False

    if not current_app.static_folder:
        current_app.logger.error("Flask app's static_folder is not configured. Cannot delete file.")
        return False

    try:
        # Construct full absolute path using static folder and the relative DB path
        full_absolute_path = os.path.join(current_app.static_folder, db_relative_path)
        full_absolute_path = os.path.normpath(full_absolute_path) # Normalize

        if os.path.exists(full_absolute_path) and os.path.isfile(full_absolute_path):
            os.remove(full_absolute_path)
            current_app.logger.info(f"Deleted existing file: {full_absolute_path}")
            return True
        else:
            current_app.logger.warning(f"File to delete not found at: {full_absolute_path} (DB path: {db_relative_path})")
            return False 
    except OSError as e:
        current_app.logger.error(f"OSError deleting file {db_relative_path} (abs: {full_absolute_path}): {e}")
    except Exception as e:
         current_app.logger.error(f"Unexpected error deleting file {db_relative_path}: {e}", exc_info=True)
    return False


# --- Database Helper Functions ---
def get_all_departments():
    conn = None; cursor = None; departments = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT department_id, name, description, image_filename FROM departments ORDER BY name ASC")
        departments = cursor.fetchall()
        for dept in departments:
            if dept.get('image_filename'): # image_filename is path relative to static (e.g. uploads/department_images/file.jpg)
                dept['image_url'] = url_for('static', filename=dept['image_filename'])
            else:
                dept['image_url'] = url_for('static', filename='Admin_Portal/images/dept_placeholder.png')
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching all departments: {err}")
        flash("Error retrieving departments from database.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return departments

def get_all_specializations_with_dept_name():
    conn = None; cursor = None; specializations = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.specialization_id, s.name, s.description, s.department_id, d.name as department_name
            FROM specializations s
            LEFT JOIN departments d ON s.department_id = d.department_id
            ORDER BY d.name ASC, s.name ASC
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
                 department['image_url'] = url_for('static', filename='Admin_Portal/images/dept_placeholder.png')
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching department {dept_id}: {err}")
        flash(f"Error retrieving department {dept_id}.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return department

# (get_specialization can remain the same)
def get_specialization(spec_id):
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
# @admin_required # Apply your admin check
def manage_structure():
    departments = get_all_departments()
    specializations = get_all_specializations_with_dept_name()
    return render_template(
        'Admin_Portal/structure/manage_structure.html', # Ensure this template path is correct
        departments=departments,
        specializations=specializations
    )

# --- Department Routes ---

@structure_bp.route('/departments/add', methods=['POST'])
@login_required
# @admin_required
def add_department():
    name = request.form.get('department_name', '').strip()
    description = request.form.get('department_description', '').strip() or None
    image_file = request.files.get('department_image')

    if not name:
        flash("Department name is required.", "danger")
        return redirect(url_for('.manage_structure'))

    conn = None; cursor = None
    saved_filename_db_path = None # This will be relative to static folder
    saved_file_absolute_path = None # For actual saving and cleanup on error
    upload_error = False

    if image_file and image_file.filename != '':
        allowed_extensions = current_app.config.get(ALLOWED_EXTENSIONS_CONFIG_KEY_IMG)
        # UPLOAD_FOLDER_DEPARTMENTS stores the absolute path
        upload_folder_absolute = current_app.config.get(UPLOAD_FOLDER_CONFIG_KEY_DEPT) 

        if not upload_folder_absolute:
            flash("Server configuration error: Department upload folder not set.", "danger")
            upload_error = True
        elif allowed_extensions and allowed_file(image_file.filename, allowed_extensions):
            try:
                filesystem_secure_name = generate_unique_filesystem_name(image_file.filename)
                saved_file_absolute_path = os.path.join(upload_folder_absolute, filesystem_secure_name)
                
                os.makedirs(upload_folder_absolute, exist_ok=True) # Ensure dir exists
                image_file.save(saved_file_absolute_path)
                current_app.logger.info(f"Department image saved to: {saved_file_absolute_path}")

                # Generate path for DB relative to static folder
                saved_filename_db_path = get_relative_path_for_db(saved_file_absolute_path)
                if not saved_filename_db_path:
                    raise ValueError("Could not determine relative path for database storage.")

            except Exception as e:
                current_app.logger.error(f"Error saving department image: {e}", exc_info=True)
                flash(f"Error saving uploaded image: {str(e)}", "danger")
                upload_error = True
        else:
            flash("Invalid image file type. Allowed types: {}".format(', '.join(allowed_extensions or [])), "danger")
            upload_error = True

    if upload_error: # If any file upload error, don't proceed to DB
        return redirect(url_for('.manage_structure'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.autocommit = False
        cursor.execute(
            "INSERT INTO departments (name, description, image_filename, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
            (name, description, saved_filename_db_path)
        )
        conn.commit()
        flash(f"Department '{name}' added successfully.", "success")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error adding department to DB: {err}")
        if err.errno == 1062: flash(f"Error: Department name '{name}' already exists.", "danger")
        else: flash(f"Database error adding department: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
        if saved_file_absolute_path and os.path.exists(saved_file_absolute_path):
             if delete_existing_image_file(saved_filename_db_path): 
                 current_app.logger.warning(f"Cleaned up orphaned file after DB error: {saved_file_absolute_path}")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Unexpected error adding department: {e}", exc_info=True)
        flash("An unexpected error occurred while adding the department.", "danger")
        if saved_file_absolute_path and os.path.exists(saved_file_absolute_path):
             if delete_existing_image_file(saved_filename_db_path):
                 current_app.logger.warning(f"Cleaned up orphaned file after unexpected error: {saved_file_absolute_path}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): 
            if not conn.autocommit: conn.autocommit = True
            conn.close()

    return redirect(url_for('.manage_structure'))


@structure_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_department(dept_id):
    conn = None; cursor = None
    
    current_department_data = get_department(dept_id) # Fetch initial data for GET and pre-POST
    if not current_department_data:
        flash("Department not found.", "warning")
        return redirect(url_for('.manage_structure'))

    if request.method == 'POST':
        name = request.form.get('department_name', '').strip()
        description = request.form.get('department_description', '').strip() or None
        image_file = request.files.get('department_image')
        delete_image_flag = request.form.get('delete_image') == '1'

        if not name:
            flash("Department name cannot be empty.", "danger")
            # Pass current_department_data back to avoid re-fetching if validation fails early
            return render_template('Admin_Portal/structure/edit_department.html', department=current_department_data)

        new_image_db_path = current_department_data.get('image_filename') # Start with existing
        saved_file_absolute_path_for_cleanup_on_error = None
        old_image_to_delete_if_replaced = None
        
        if delete_image_flag:
            if new_image_db_path: # If there was an image
                old_image_to_delete_if_replaced = new_image_db_path # Mark for deletion
                new_image_db_path = None # Set to None for DB update
            # File deletion will happen after successful DB update or on error cleanup
        elif image_file and image_file.filename != '':
            allowed_extensions = current_app.config.get(ALLOWED_EXTENSIONS_CONFIG_KEY_IMG)
            upload_folder_absolute = current_app.config.get(UPLOAD_FOLDER_CONFIG_KEY_DEPT)

            if not upload_folder_absolute:
                flash("Server configuration error: Department upload folder not set.", "danger")
                return render_template('Admin_Portal/structure/edit_department.html', department=current_department_data)
            
            if allowed_extensions and allowed_file(image_file.filename, allowed_extensions):
                try:
                    filesystem_secure_name = generate_unique_filesystem_name(image_file.filename)
                    saved_file_absolute_path = os.path.join(upload_folder_absolute, filesystem_secure_name)
                    
                    os.makedirs(upload_folder_absolute, exist_ok=True)
                    image_file.save(saved_file_absolute_path)
                    current_app.logger.info(f"New department image for {dept_id} saved: {saved_file_absolute_path}")
                    
                    temp_db_path = get_relative_path_for_db(saved_file_absolute_path)
                    if not temp_db_path:
                        raise ValueError("Could not determine relative path for new image.")
                    
                    old_image_to_delete_if_replaced = new_image_db_path # Mark current image for deletion
                    new_image_db_path = temp_db_path # This is the new path for the DB
                    saved_file_absolute_path_for_cleanup_on_error = saved_file_absolute_path

                except Exception as e:
                    current_app.logger.error(f"Error saving updated department image for {dept_id}: {e}", exc_info=True)
                    flash(f"Error saving uploaded image: {str(e)}", "danger")
                    # Don't change new_image_db_path, keep the old one
                    return render_template('Admin_Portal/structure/edit_department.html', department=current_department_data)
            else:
                flash("Invalid new image file type. Allowed types: {}".format(', '.join(allowed_extensions or [])), "danger")
                return render_template('Admin_Portal/structure/edit_department.html', department=current_department_data)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            conn.autocommit = False
            cursor.execute(
                """UPDATE departments SET
                   name = %s, description = %s, image_filename = %s, updated_at = NOW()
                   WHERE department_id = %s""",
                (name, description, new_image_db_path, dept_id)
            )
            conn.commit()

            # If DB update was successful, now delete the old physical file if it was replaced or marked for deletion
            if old_image_to_delete_if_replaced and old_image_to_delete_if_replaced != new_image_db_path:
                delete_existing_image_file(old_image_to_delete_if_replaced)
            
            flash(f"Department '{name}' updated successfully.", "success")
            return redirect(url_for('.manage_structure'))

        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"Error updating department {dept_id} in DB: {err}")
            if err.errno == 1062: flash(f"Error: Department name '{name}' already exists.", "danger")
            else: flash(f"Database error updating department: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
            
            # If a new file was saved but DB update failed, try to clean up the new file
            if saved_file_absolute_path_for_cleanup_on_error and os.path.exists(saved_file_absolute_path_for_cleanup_on_error):
                if get_relative_path_for_db(saved_file_absolute_path_for_cleanup_on_error) == new_image_db_path: # ensure it's the one we tried to set
                    delete_existing_image_file(new_image_db_path)
                    current_app.logger.warning(f"Cleaned up newly uploaded file {new_image_db_path} for dept {dept_id} due to DB error.")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Unexpected error updating department {dept_id}: {e}", exc_info=True)
            flash("An unexpected error occurred while updating.", "danger")
            if saved_file_absolute_path_for_cleanup_on_error and os.path.exists(saved_file_absolute_path_for_cleanup_on_error):
                 if get_relative_path_for_db(saved_file_absolute_path_for_cleanup_on_error) == new_image_db_path:
                    delete_existing_image_file(new_image_db_path)
                    current_app.logger.warning(f"Cleaned up newly uploaded file {new_image_db_path} for dept {dept_id} due to unexpected error.")
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): 
                if not conn.autocommit: conn.autocommit = True
                conn.close()
        # Re-render form with potentially unchanged department data on error
        return render_template('Admin_Portal/structure/edit_department.html', department=get_department(dept_id))


    # GET Request
    return render_template('Admin_Portal/structure/edit_department.html', department=current_department_data)


@structure_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
# @admin_required
def delete_department(dept_id):
    conn = None; cursor = None
    department_data = get_department(dept_id) # Fetch before delete to get image filename
    image_to_delete_db_path = department_data.get('image_filename') if department_data else None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.autocommit = False
        
        # Consider what happens to specializations linked to this department.
        # If FK is SET NULL: specializations.department_id will become NULL.
        # If FK is RESTRICT/NO ACTION: this delete will fail if specializations are linked.
        # Current specializations table has ON DELETE SET NULL for department_id in its FK.
        
        cursor.execute("DELETE FROM departments WHERE department_id = %s", (dept_id,))
        
        if cursor.rowcount > 0:
            conn.commit() # Commit DB changes first
            flash("Department deleted successfully. Associated specializations' department links are set to NULL.", "success")
            if image_to_delete_db_path:
                delete_existing_image_file(image_to_delete_db_path)
        else:
            if conn.in_transaction: conn.rollback()
            flash("Department not found or already deleted.", "warning")

    except mysql.connector.Error as err:
        if conn and conn.is_connected() and not conn.autocommit : conn.rollback()
        current_app.logger.error(f"Error deleting department {dept_id}: {err}")
        if err.errno == 1451: # Foreign key constraint fails (e.g. if specializations FK was RESTRICT)
            flash("Cannot delete department. It might be referenced by other records (e.g., specializations if FK was restrictive, or doctors if directly linked).", "danger")
        else:
            flash(f"Database error deleting department: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
    except Exception as e:
         if conn and conn.is_connected() and not conn.autocommit : conn.rollback()
         current_app.logger.error(f"Unexpected error deleting department {dept_id}: {e}", exc_info=True)
         flash("An unexpected error occurred during deletion.", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): 
            if not conn.autocommit : conn.autocommit = True
            conn.close()

    return redirect(url_for('.manage_structure'))


# --- Specialization Routes (No file handling, largely unchanged) ---
@structure_bp.route('/specializations/add', methods=['POST'])
@login_required
# @admin_required
def add_specialization():
    name = request.form.get('specialization_name', '').strip()
    description = request.form.get('specialization_description', '').strip() or None
    department_id_str = request.form.get('department_id', '').strip()

    if not name:
        flash("Specialization name is required.", "danger")
        return redirect(url_for('.manage_structure') + '#specializations-section')

    department_id = None
    if department_id_str: # Department is optional for a specialization
        try: department_id = int(department_id_str)
        except ValueError:
            flash("Invalid Department selected for specialization.", "danger")
            return redirect(url_for('.manage_structure') + '#specializations-section')

    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.autocommit = False
        cursor.execute(
            "INSERT INTO specializations (name, description, department_id, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())",
            (name, description, department_id) 
        )
        conn.commit()
        flash(f"Specialization '{name}' added successfully.", "success")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error adding specialization: {err}")
        if err.errno == 1062: 
            flash(f"Error: Specialization name '{name}' already exists.", "danger")
        elif err.errno == 1452 and department_id is not None: # FK constraint violation only if department_id was provided
             flash(f"Error: Invalid Department selected for specialization.", "danger")
        else:
            flash(f"Database error adding specialization: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): 
            if not conn.autocommit: conn.autocommit = True
            conn.close()
    return redirect(url_for('.manage_structure') + '#specializations-section')

@structure_bp.route('/specializations/<int:spec_id>/edit', methods=['GET', 'POST'])
@login_required
# @admin_required
def edit_specialization(spec_id):
    conn = None; cursor = None
    
    if request.method == 'POST':
        name = request.form.get('specialization_name', '').strip()
        description = request.form.get('specialization_description', '').strip() or None
        department_id_str = request.form.get('department_id', '').strip()

        if not name:
            flash("Specialization name cannot be empty.", "danger")
            # Re-fetch for re-render
            specialization = get_specialization(spec_id)
            departments = get_all_departments()
            if not specialization: return redirect(url_for('.manage_structure'))
            return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)

        department_id = None
        if department_id_str:
            try: department_id = int(department_id_str)
            except ValueError:
                flash("Invalid Department selected.", "danger")
                specialization = get_specialization(spec_id)
                departments = get_all_departments()
                if not specialization: return redirect(url_for('.manage_structure'))
                return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            conn.autocommit = False
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
            if conn: conn.rollback()
            current_app.logger.error(f"Error updating specialization {spec_id}: {err}")
            if err.errno == 1062:
                flash(f"Error: Specialization name '{name}' already exists.", "danger")
            elif err.errno == 1452 and department_id is not None:
                 flash(f"Error: Invalid Department selected.", "danger")
            else:
                flash(f"Database error updating specialization: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
            specialization = get_specialization(spec_id) # Re-fetch for form
            departments = get_all_departments()
            return render_template('Admin_Portal/structure/edit_specialization.html', specialization=specialization, departments=departments)
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): 
                if not conn.autocommit: conn.autocommit = True
                conn.close()

    # GET Request
    specialization = get_specialization(spec_id)
    if not specialization:
        flash("Specialization not found.", "warning")
        return redirect(url_for('.manage_structure'))
    departments = get_all_departments()
    return render_template(
        'Admin_Portal/structure/edit_specialization.html', # Ensure this template path is correct
        specialization=specialization,
        departments=departments
    )

@structure_bp.route('/specializations/<int:spec_id>/delete', methods=['POST'])
@login_required
# @admin_required
def delete_specialization(spec_id):
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.autocommit = False
        cursor.execute("DELETE FROM specializations WHERE specialization_id = %s", (spec_id,))
        conn.commit()
        if cursor.rowcount > 0:
            flash("Specialization deleted successfully.", "success")
        else:
            flash("Specialization not found or already deleted.", "warning")
    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting specialization {spec_id}: {err}")
        if err.errno == 1451: 
             flash(f"Cannot delete specialization: It is currently assigned to one or more doctors. Reassign doctors first or update their specialization to 'Unassigned'.", "danger")
        else:
            flash(f"Database error deleting specialization: {err.msg if hasattr(err, 'msg') else str(err)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): 
            if not conn.autocommit: conn.autocommit = True
            conn.close()
    return redirect(url_for('.manage_structure') + '#specializations-section')