from flask import Blueprint, render_template, abort, current_app
from db import get_db_connection
import math

vaccines_bp = Blueprint(
    'vaccines_bp',
    __name__,
    template_folder='../../templates/Website/Vaccines',
)

# Helper function to fetch vaccine categories
def get_vaccine_categories_from_db():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT category_id, category_name, description, target_group, image_filename
                FROM vaccine_categories
                WHERE is_active = 1
                ORDER BY category_name
            """
            cursor.execute(query)
            categories = cursor.fetchall()
            return categories if categories else []
    except Exception as e:
        current_app.logger.error(f"Error fetching vaccine categories: {e}", exc_info=True)
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Helper function to fetch common vaccines
def get_common_vaccines_from_db(limit=4):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT vaccine_id, vaccine_name, abbreviation, diseases_prevented
                FROM vaccines
                WHERE is_active = 1
                ORDER BY vaccine_name
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            vaccines = cursor.fetchall()
            return vaccines if vaccines else []
    except Exception as e:
        current_app.logger.error(f"Error fetching common vaccines: {e}", exc_info=True)
        return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Helper function to fetch a single vaccine's details by its ID
def get_vaccine_details_by_id_from_db(vaccine_id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT v.*, vc.category_name
                FROM vaccines v
                LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id
                WHERE v.vaccine_id = %s AND v.is_active = 1
                LIMIT 1
            """
            cursor.execute(query, (vaccine_id,))
            vaccine = cursor.fetchone()
            return vaccine
    except Exception as e:
        current_app.logger.error(f"Error fetching vaccine details for ID '{vaccine_id}': {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

# Helper function to fetch a single category's details by its ID
# AND fetch its associated vaccines
def get_category_details_and_vaccines_by_id_from_db(category_id):
    conn = None
    cursor = None
    category_data = None
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            # Fetch category details
            query_category = """
                SELECT * FROM vaccine_categories
                WHERE category_id = %s AND is_active = 1
                LIMIT 1
            """
            cursor.execute(query_category, (category_id,))
            category_data = cursor.fetchone()

            if category_data:
                # Fetch vaccines in this category
                query_vaccines = """
                    SELECT vaccine_id, vaccine_name, abbreviation, diseases_prevented
                    FROM vaccines
                    WHERE category_id = %s AND is_active = 1
                    ORDER BY vaccine_name
                """
                cursor.execute(query_vaccines, (category_data['category_id'],))
                vaccines_in_category = cursor.fetchall()
                category_data['vaccines_in_category_list'] = vaccines_in_category if vaccines_in_category else []
            return category_data
    except Exception as e:
        current_app.logger.error(f"Error fetching category details and vaccines for ID '{category_id}': {e}", exc_info=True)
        return None
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


@vaccines_bp.route('/')
def vaccine_landing():
    categories = get_vaccine_categories_from_db()
    common_vaccines = get_common_vaccines_from_db()
    # Virus spikes data logic for decorative SVG (remains the same)
    num_spikes = 12; center_x, center_y = 50, 50; spike_line_length = 40
    spike_circle_radius_offset = 42; spike_circle_radius = 4; virus_spikes_data = []
    for i in range(num_spikes):
        angle_rad = (i * 360 / num_spikes) * (math.pi / 180)
        line_x2 = center_x + spike_line_length * math.cos(angle_rad)
        line_y2 = center_y + spike_line_length * math.sin(angle_rad)
        circle_x = center_x + spike_circle_radius_offset * math.cos(angle_rad)
        circle_y = center_y + spike_circle_radius_offset * math.sin(angle_rad)
        virus_spikes_data.append({
            'line_x1': center_x, 'line_y1': center_y, 'line_x2': line_x2, 'line_y2': line_y2,
            'circle_x': circle_x, 'circle_y': circle_y, 'circle_r': spike_circle_radius
        })
    return render_template(
        'vaccine_landing.html',
        categories=categories,
        common_vaccines=common_vaccines,
        virus_spikes=virus_spikes_data
    )

# Route for individual vaccine details using vaccine_id
@vaccines_bp.route('/vaccine/<int:vaccine_id>')
def vaccine_detail_page(vaccine_id):
    vaccine_data = get_vaccine_details_by_id_from_db(vaccine_id)
    if not vaccine_data:
        current_app.logger.warning(f"No vaccine found for ID: {vaccine_id}. Aborting with 404.")
        abort(404)

    page_title = vaccine_data.get('vaccine_name', "Vaccine Information")
    return render_template('vaccine_condition_details.html',
                           page_title=page_title,
                           data=vaccine_data,
                           data_type='vaccine')

# Route for individual category details using category_id
@vaccines_bp.route('/category/<int:category_id>')
def category_detail_page(category_id):
    category_data_with_vaccines = get_category_details_and_vaccines_by_id_from_db(category_id)
    if not category_data_with_vaccines:
        current_app.logger.warning(f"No category found for ID: {category_id}. Aborting with 404.")
        abort(404)

    page_title = category_data_with_vaccines.get('category_name', "Category Information")
    return render_template('vaccine_condition_details.html',
                           page_title=page_title,
                           data=category_data_with_vaccines, # This includes 'vaccines_in_category_list'
                           data_type='category')