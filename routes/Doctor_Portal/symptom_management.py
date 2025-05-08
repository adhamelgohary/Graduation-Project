# your_project/routes/Doctor_Portal/symptom_management.py

import mysql.connector
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    jsonify, current_app, abort
)
from flask_login import login_required, current_user
import os
from db import get_db_connection
from datetime import datetime
import math

# Adjust import based on your project structure for utils
from .utils import (
    check_doctor_authorization,
    get_enum_values,
    get_all_simple
)

# --- Blueprint Definition ---
symptom_management_bp = Blueprint(
    'symptom_management',
    __name__,
    url_prefix='/doctor/symptoms',
    template_folder='../../templates'
)

# --- Configuration / Constants ---
ITEMS_PER_PAGE_SYMPTOMS = 15
# Updated VALID_SORT_COLUMNS to reference alias 's' from the query
VALID_SORT_COLUMNS_SYMPTOMS = {
    'name': 's.symptom_name',
    'id': 's.symptom_id',
    'category': 's.symptom_category',
    'body_area': 's.body_area',
    'icd_code': 's.icd_code'
}
DEFAULT_SORT_COLUMN_SYMPTOMS = 'name'
DEFAULT_SORT_DIRECTION_SYMPTOMS = 'ASC'


# --- Data Fetching Helpers ---

def get_all_body_locations_with_sublocations():
    """Fetches all body locations and their sublocations for forms."""
    conn = None
    cursor = None
    locations_data = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT location_id, location_name FROM body_locations ORDER BY display_order, location_name")
        main_locations = cursor.fetchall()
        for loc in main_locations:
            cursor.execute(
                "SELECT sublocation_id, sublocation_name FROM body_sublocations WHERE location_id = %s ORDER BY display_order, sublocation_name",
                (loc['location_id'],)
            )
            loc['sublocations'] = cursor.fetchall()
            locations_data.append(loc)
    except mysql.connector.Error as err:
        current_app.logger.error(f"Error fetching body locations with sublocations: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return locations_data

def get_paginated_symptoms(page=1, per_page=ITEMS_PER_PAGE_SYMPTOMS, search_term=None,
                           sort_by=DEFAULT_SORT_COLUMN_SYMPTOMS, sort_dir=DEFAULT_SORT_DIRECTION_SYMPTOMS,
                           filters=None):
    """Fetches a paginated list of symptoms."""
    conn = None; cursor = None
    result = {'items': [], 'total': 0}
    offset = (page - 1) * per_page
    valid_filters = filters or {}

    sort_column_sql = VALID_SORT_COLUMNS_SYMPTOMS.get(sort_by, VALID_SORT_COLUMNS_SYMPTOMS[DEFAULT_SORT_COLUMN_SYMPTOMS])
    sort_dir_sql = 'DESC' if sort_dir.upper() == 'DESC' else 'ASC'

    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        sql_select = "SELECT SQL_CALC_FOUND_ROWS s.symptom_id, s.symptom_name, s.description, s.body_area, s.icd_code, s.symptom_category"
        sql_from = " FROM symptoms s"
        # Add `WHERE s.is_active = TRUE` if you implement soft deletes
        sql_where = " WHERE 1=1 "
        params = []

        if search_term:
            search_like = f"%{search_term}%"
            sql_where += " AND (s.symptom_name LIKE %s OR s.description LIKE %s OR s.icd_code LIKE %s)"
            params.extend([search_like, search_like, search_like])

        if valid_filters.get('category'):
            sql_where += " AND s.symptom_category = %s"
            params.append(valid_filters['category'])
        if valid_filters.get('body_area'):
            sql_where += " AND s.body_area LIKE %s"
            params.append(f"%{valid_filters['body_area']}%")

        query = f"{sql_select}{sql_from}{sql_where} ORDER BY {sort_column_sql} {sort_dir_sql} LIMIT %s OFFSET %s"
        params.extend([per_page, offset])
        cursor.execute(query, tuple(params))
        result['items'] = cursor.fetchall()
        cursor.execute("SELECT FOUND_ROWS() as total")
        result['total'] = cursor.fetchone()['total']

    except Exception as err:
        current_app.logger.error(f"Error in get_paginated_symptoms: {err}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return result

def get_symptom_details_simple(symptom_id):
    """Fetches symptom details and associated body sublocations (simplified)."""
    conn = None; cursor = None
    details = {'symptom': None, 'body_sublocations': []}
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True, buffered=True)
        # Add `AND is_active = TRUE` if implementing soft delete
        cursor.execute("SELECT * FROM symptoms WHERE symptom_id = %s", (symptom_id,))
        details['symptom'] = cursor.fetchone()

        if details['symptom']:
            cursor.execute("""
                SELECT bsl.sublocation_id, bsl.sublocation_name, bl.location_name
                FROM body_sublocations bsl
                JOIN symptom_body_locations sbl ON bsl.sublocation_id = sbl.sublocation_id
                JOIN body_locations bl ON bsl.location_id = bl.location_id
                WHERE sbl.symptom_id = %s
                ORDER BY bl.location_name, bsl.sublocation_name
            """, (symptom_id,))
            details['body_sublocations'] = cursor.fetchall()

    except Exception as err:
        current_app.logger.error(f"Error get_symptom_details_simple ID {symptom_id}: {err}", exc_info=True)
        return None # Return None on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    # Return None if symptom itself wasn't found, otherwise return details dict
    return details if details['symptom'] else None


def get_symptom_details_for_form(symptom_id):
    """Fetches core symptom data and just the IDs of associated sublocations."""
    conn = None; cursor = None;
    result = {'symptom': None, 'associated_sublocation_ids': []}
    try:
        conn = get_db_connection();
        cursor = conn.cursor(dictionary=True) # Core data needs dict
        # Add `AND is_active = TRUE` if implementing soft delete
        cursor.execute("SELECT * FROM symptoms WHERE symptom_id = %s", (symptom_id,))
        result['symptom'] = cursor.fetchone()
        cursor.close() # Close dict cursor

        if result['symptom']:
            # Use a separate non-dict cursor for fetching just IDs
            cursor = conn.cursor(buffered=True)
            cursor.execute("SELECT sublocation_id FROM symptom_body_locations WHERE symptom_id = %s", (symptom_id,))
            result['associated_sublocation_ids'] = [row[0] for row in cursor.fetchall()]

    except Exception as err:
        current_app.logger.error(f"Error get_symptom_details_for_form ID {symptom_id}: {err}", exc_info=True)
        return None # Return None on error
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    # Return None if symptom itself wasn't found, otherwise return result dict
    return result if result['symptom'] else None

def update_symptom_sublocation_associations(cursor, symptom_id, selected_sublocation_ids):
    """Updates ONLY the symptom-body sublocation associations."""
    try:
        # Delete existing sublocation links for this symptom
        cursor.execute("DELETE FROM symptom_body_locations WHERE symptom_id = %s", (symptom_id,))
        # Insert new links if any were selected
        if selected_sublocation_ids:
            # Assuming default relevance_score = 1.0
            subloc_insert_data = [(symptom_id, sub_id, 1.0) for sub_id in selected_sublocation_ids]
            subloc_sql = "INSERT INTO symptom_body_locations (symptom_id, sublocation_id, relevance_score) VALUES (%s, %s, %s)"
            cursor.executemany(subloc_sql, subloc_insert_data)
            current_app.logger.info(f"Updated {len(subloc_insert_data)} sublocation associations for symptom {symptom_id}.")
    except mysql.connector.Error as err:
        current_app.logger.error(f"DB Error updating sublocation associations for symptom {symptom_id}: {err}", exc_info=True)
        raise # Re-raise to ensure transaction rollback


# --- Routes (Simplified) ---

@symptom_management_bp.route('/', methods=['GET'])
@login_required
def list_symptoms():
    """Displays a paginated list of symptoms."""
    if not check_doctor_authorization(current_user): abort(403)

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', DEFAULT_SORT_COLUMN_SYMPTOMS).lower()
    sort_dir = request.args.get('sort_dir', DEFAULT_SORT_DIRECTION_SYMPTOMS).upper()
    filters = {k: request.args.get(f'filter_{k}') for k in ['category', 'body_area'] if request.args.get(f'filter_{k}')}

    if sort_by not in VALID_SORT_COLUMNS_SYMPTOMS: sort_by = DEFAULT_SORT_COLUMN_SYMPTOMS
    if sort_dir not in ['ASC', 'DESC']: sort_dir = DEFAULT_SORT_DIRECTION_SYMPTOMS

    result = get_paginated_symptoms(page, ITEMS_PER_PAGE_SYMPTOMS, search, sort_by, sort_dir, filters)
    total_pages = math.ceil(result['total'] / ITEMS_PER_PAGE_SYMPTOMS) if ITEMS_PER_PAGE_SYMPTOMS > 0 else 0

    filter_options = {'symptom_categories': get_enum_values('symptoms', 'symptom_category')}

    return render_template(
        'Doctor_Portal/Symptoms/symptom_list.html',
        symptoms=result['items'],
        total_symptoms=result['total'],
        search_term=search, current_page=page, total_pages=total_pages,
        sort_by=sort_by, sort_dir=sort_dir, filters=filters,
        valid_sort_columns=VALID_SORT_COLUMNS_SYMPTOMS, **filter_options
    )

@symptom_management_bp.route('/<int:symptom_id>', methods=['GET'])
@login_required
def view_symptom(symptom_id):
    """Displays details for a single symptom (simplified)."""
    if not check_doctor_authorization(current_user): abort(403)

    details = get_symptom_details_simple(symptom_id) # Using the simplified detail fetcher
    if not details:
        flash("Symptom not found.", "warning")
        return redirect(url_for('.list_symptoms'))

    # Pass the details dict directly; template needs adjustment if structure changed significantly
    return render_template('Doctor_Portal/Symptoms/symptom_detail.html', details=details)

@symptom_management_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_symptom():
    """Adds a new symptom."""
    if not check_doctor_authorization(current_user): abort(403)

    dropdown_options = {
        'symptom_categories': get_enum_values('symptoms', 'symptom_category'),
        'gender_relevance_opts': get_enum_values('symptoms', 'gender_relevance'),
        'all_body_locations_with_sub': get_all_body_locations_with_sublocations(),
        # 'all_conditions': get_all_conditions_for_linking(), # REMOVED
    }

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        selected_sublocation_ids = request.form.getlist('sublocation_ids', type=int)
        # selected_condition_ids = request.form.getlist('condition_ids', type=int) # REMOVED

        try:
            form = request.form
            symptom_name = form.get('symptom_name', '').strip()
            description = form.get('description', '').strip() or None
            body_area = form.get('body_area', '').strip() or None
            icd_code = form.get('icd_code', '').strip() or None
            common_causes = form.get('common_causes', '').strip() or None
            severity_scale = form.get('severity_scale', '').strip() or None
            symptom_category = form.get('symptom_category') or None
            age_relevance = form.get('age_relevance', '').strip() or None
            gender_relevance = form.get('gender_relevance') if form.get('gender_relevance') else 'all'
            question_text = form.get('question_text', '').strip() or None
            follow_up_questions = form.get('follow_up_questions', '').strip() or None

            # --- Validation ---
            if not symptom_name: errors.append("Symptom Name is required.")
            if symptom_category and symptom_category not in dropdown_options.get('symptom_categories',[]): errors.append("Invalid Symptom Category.")
            if gender_relevance and gender_relevance not in dropdown_options.get('gender_relevance_opts',[]): errors.append("Invalid Gender Relevance.")

            if errors: raise ValueError("Validation failed.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_symptom = """INSERT INTO symptoms (symptom_name, description, body_area, icd_code, common_causes, severity_scale, symptom_category, age_relevance, gender_relevance, question_text, follow_up_questions, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())"""
            params_symptom = (symptom_name, description, body_area, icd_code, common_causes, severity_scale, symptom_category, age_relevance, gender_relevance, question_text, follow_up_questions)
            cursor.execute(sql_symptom, params_symptom)
            new_symptom_id = cursor.lastrowid
            if not new_symptom_id: raise mysql.connector.Error("Failed to insert symptom.")

            # Update only sublocation associations
            update_symptom_sublocation_associations(cursor, new_symptom_id, selected_sublocation_ids)

            conn.commit()
            flash(f"Symptom '{symptom_name}' added successfully.", "success")
            # Consider redirecting to list view for simplicity, or keep detail view
            # return redirect(url_for('.list_symptoms'))
            return redirect(url_for('.view_symptom', symptom_id=new_symptom_id))

        except ValueError:
            for e in errors: flash(e, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error adding symptom: {err}", exc_info=True); flash("Database error occurred.", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Error adding symptom: {e}", exc_info=True); flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

        # Re-render on error
        return render_template(
            'Doctor_Portal/Symptoms/symptom_form.html', form_action=url_for('.add_symptom'), form_title="Add New Symptom",
            symptom=request.form, errors=errors, **dropdown_options,
            associated_sublocation_ids=selected_sublocation_ids
            # associated_condition_ids=selected_condition_ids # REMOVED
        )

    # GET request
    return render_template(
        'Doctor_Portal/Symptoms/symptom_form.html', form_action=url_for('.add_symptom'), form_title="Add New Symptom",
        symptom=None, **dropdown_options, associated_sublocation_ids=[]
        # associated_condition_ids=[] # REMOVED
    )

@symptom_management_bp.route('/<int:symptom_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_symptom(symptom_id):
    """Edits an existing symptom."""
    if not check_doctor_authorization(current_user): abort(403)

    dropdown_options = {
        'symptom_categories': get_enum_values('symptoms', 'symptom_category'),
        'gender_relevance_opts': get_enum_values('symptoms', 'gender_relevance'),
        'all_body_locations_with_sub': get_all_body_locations_with_sublocations(),
        # 'all_conditions': get_all_conditions_for_linking(), # REMOVED
    }

    if request.method == 'POST':
        conn = None; cursor = None; errors = []
        selected_sublocation_ids = request.form.getlist('sublocation_ids', type=int)
        # selected_condition_ids = request.form.getlist('condition_ids', type=int) # REMOVED

        try:
            form = request.form
            symptom_name = form.get('symptom_name', '').strip()
            description = form.get('description', '').strip() or None
            body_area = form.get('body_area', '').strip() or None
            icd_code = form.get('icd_code', '').strip() or None
            common_causes = form.get('common_causes', '').strip() or None
            severity_scale = form.get('severity_scale', '').strip() or None
            symptom_category = form.get('symptom_category') or None
            age_relevance = form.get('age_relevance', '').strip() or None
            gender_relevance = form.get('gender_relevance') if form.get('gender_relevance') else 'all'
            question_text = form.get('question_text', '').strip() or None
            follow_up_questions = form.get('follow_up_questions', '').strip() or None

            if not symptom_name: errors.append("Symptom Name is required.")
            if symptom_category and symptom_category not in dropdown_options.get('symptom_categories',[]): errors.append("Invalid Symptom Category.")
            if gender_relevance and gender_relevance not in dropdown_options.get('gender_relevance_opts', []): errors.append("Invalid Gender Relevance.")

            if errors: raise ValueError("Validation failed.")

            conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()
            sql_update = """UPDATE symptoms SET symptom_name=%s, description=%s, body_area=%s, icd_code=%s, common_causes=%s, severity_scale=%s, symptom_category=%s, age_relevance=%s, gender_relevance=%s, question_text=%s, follow_up_questions=%s, updated_at=NOW() WHERE symptom_id=%s"""
            # Add `AND is_active = TRUE` if needed
            params_update = (symptom_name, description, body_area, icd_code, common_causes, severity_scale, symptom_category, age_relevance, gender_relevance, question_text, follow_up_questions, symptom_id)
            cursor.execute(sql_update, params_update)

            if cursor.rowcount == 0:
                conn.rollback(); flash("Symptom not found or no changes made.", "warning")
                return redirect(url_for('.list_symptoms'))

            # Update only sublocation associations
            update_symptom_sublocation_associations(cursor, symptom_id, selected_sublocation_ids)

            conn.commit()
            flash(f"Symptom '{symptom_name}' updated successfully.", "success")
            return redirect(url_for('.view_symptom', symptom_id=symptom_id)) # Go back to detail view

        except ValueError:
             for e_msg in errors: flash(e_msg, 'danger')
        except mysql.connector.Error as err:
            if conn: conn.rollback()
            current_app.logger.error(f"DB error editing symptom {symptom_id}: {err}", exc_info=True); flash("Database error occurred.", "danger")
        except Exception as e:
            if conn: conn.rollback()
            current_app.logger.error(f"Error editing symptom {symptom_id}: {e}", exc_info=True); flash("An unexpected error occurred.", "danger")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

        # Re-render on error
        form_data_on_err = request.form.to_dict()
        form_data_on_err['symptom_id'] = symptom_id
        return render_template(
            'Doctor_Portal/Symptoms/symptom_form.html',
            form_action=url_for('.edit_symptom', symptom_id=symptom_id), form_title=f"Edit Symptom (ID: {symptom_id})",
            symptom=form_data_on_err, errors=errors, **dropdown_options,
            associated_sublocation_ids=selected_sublocation_ids
            # associated_condition_ids=selected_condition_ids # REMOVED
        )

    # GET request
    form_data = get_symptom_details_for_form(symptom_id) # Use the combined fetcher
    if not form_data:
        flash("Symptom not found.", "warning")
        return redirect(url_for('.list_symptoms'))

    return render_template(
        'Doctor_Portal/Symptoms/symptom_form.html',
        form_action=url_for('.edit_symptom', symptom_id=symptom_id),
        form_title=f"Edit Symptom: {form_data['symptom'].get('symptom_name', 'N/A')}",
        symptom=form_data['symptom'],
        **dropdown_options,
        associated_sublocation_ids=form_data['associated_sublocation_ids']
        # associated_condition_ids=form_data['associated_condition_ids'] # REMOVED
    )

@symptom_management_bp.route('/<int:symptom_id>/delete', methods=['POST'])
@login_required
def delete_symptom(symptom_id):
    """Deletes a symptom and its sublocation associations (Hard Delete)."""
    # Optional: Implement stricter authorization
    if not check_doctor_authorization(current_user): abort(403)

    conn = None; cursor = None
    try:
        conn = get_db_connection(); conn.start_transaction(); cursor = conn.cursor()

        # Delete associations first
        cursor.execute("DELETE FROM symptom_body_locations WHERE symptom_id = %s", (symptom_id,))
        # No longer need to delete from symptom_condition_map

        # Delete the symptom itself
        cursor.execute("DELETE FROM symptoms WHERE symptom_id = %s", (symptom_id,))

        if cursor.rowcount == 0:
            flash("Symptom not found or already deleted.", "warning"); conn.rollback()
        else:
            conn.commit(); flash("Symptom deleted successfully.", "success")

    except mysql.connector.Error as err:
        if conn: conn.rollback()
        current_app.logger.error(f"DB Error deleting symptom {symptom_id}: {err}", exc_info=True); flash("Error deleting symptom.", "danger")
    except Exception as e:
        if conn: conn.rollback()
        current_app.logger.error(f"Error deleting symptom {symptom_id}: {e}", exc_info=True); flash("An unexpected error occurred.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for('.list_symptoms')) # Redirect to list view after deletion