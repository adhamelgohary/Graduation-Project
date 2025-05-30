# routes/Website/home.py

from flask import Blueprint, render_template, current_app
import mysql.connector
from db import get_db_connection # Assuming db.py has this function

# Define the blueprint
home_bp = Blueprint(
    'home',
    __name__,
    template_folder='../../templates/Website' # Adjusted relative path
)

# --- Helper to fetch ALL departments including image filename from DB ---
# This function remains as it might be used by other parts of the application
# or future features. It is NOT directly used by the modified homepage /index route
# for the "Our Departments" section anymore.
def get_all_departments_from_db():
    """
    Fetches ALL departments from the database, including image filename.
    Uses the 'image_filename' value directly as the image path.
    """
    departments_data = []
    conn = None
    cursor = None
    placeholder_image_path = "images/placeholder.jpg"

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            raise ConnectionError("Database connection failed")

        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT
                department_id,
                name,
                description,
                image_filename
            FROM departments
            ORDER BY name ASC
        """

        cursor.execute(query)
        results = cursor.fetchall()

        for dept in results:
            db_image_path = dept.get('image_filename')
            if db_image_path:
                dept['image_url'] = db_image_path
            else:
                dept['image_url'] = placeholder_image_path
            departments_data.append(dept)

    except mysql.connector.Error as db_err:
        if db_err.errno == 1054 and 'image_filename' in str(db_err):
             current_app.logger.error(f"Database error fetching departments: Column 'image_filename' might be missing in the 'departments' table. Please verify schema. Error: {db_err}")
        else:
             current_app.logger.error(f"Database error fetching all departments: {db_err}")
    except ConnectionError as conn_err:
         current_app.logger.error(f"{conn_err} fetching all departments.")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching all departments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    current_app.logger.info(f"Fetched and processed {len(departments_data)} departments from database (using direct image paths).")
    return departments_data


# --- Main Homepage Route ---
@home_bp.route('/')
def index():
    """
    Renders the public homepage.
    The "Our Departments" section is now statically defined in the home.html template.
    """
    # The previous logic for fetching 'featured_departments' is no longer needed
    # for the "Our Departments" section as it's now static in the template.
    # If other parts of home.html needed all_departments, that logic would remain here.
    # Based on the provided home.html, it's not currently used.

    current_app.logger.info("Rendering homepage with static 'Our Departments' section.")
    return render_template('Website/home.html')