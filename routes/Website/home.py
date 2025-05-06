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
def get_all_departments_from_db():
    """
    Fetches ALL departments from the database, including image filename.
    Uses the 'image_filename' value directly as the image path.
    """
    departments_data = []
    conn = None
    cursor = None
    # Define the path for your placeholder image. Ensure this path is
    # resolvable by the browser in the same way your database paths are.
    placeholder_image_path = "images/placeholder.jpg" # Example: Adjust if needed

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
                image_filename  -- Fetch the image path/filename stored in the DB
            FROM departments
            ORDER BY name ASC
        """

        cursor.execute(query)
        results = cursor.fetchall()

        # Process results to create the image URL path
        for dept in results:
            # Get the path/filename from DB
            db_image_path = dept.get('image_filename')

            # --- UPDATED LOGIC ---
            # Use the database path directly if it exists, otherwise use the placeholder path
            if db_image_path:
                dept['image_url'] = db_image_path # Use the exact value from the DB
            else:
                dept['image_url'] = placeholder_image_path # Use the defined placeholder path
            # --- END UPDATED LOGIC ---

            # Optional cleanup: remove raw filename if not needed in template
            # (You might keep it if the template logic differs based on whether it's a placeholder)
            # if 'image_filename' in dept:
            #    del dept['image_filename']

            departments_data.append(dept)

    except mysql.connector.Error as db_err:
        # Specific check for missing column 'image_filename'
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


# --- Main Homepage Route (No changes needed here) ---
@home_bp.route('/')
def index():
    """
    Renders the public homepage.
    Fetches ALL departments from the database for the categories section.
    """
    all_departments = get_all_departments_from_db()

    featured_names = [
       "Cardiology", "Neurology", "Dermatology",
       "Orthopedics", "Nutrition Services", "General Medicine"
    ]
    name_to_dept = {dept['name']: dept for dept in all_departments}
    featured_departments = [name_to_dept.get(name) for name in featured_names if name_to_dept.get(name)]

    if len(featured_departments) < len(featured_names):
        current_app.logger.warning(f"Requested featured departments {featured_names}, but only found {len(featured_departments)}. Check names or database.")

    current_app.logger.info(f"Displaying {len(featured_departments)} featured departments on homepage.")
    return render_template('Website/home.html', featured_departments=featured_departments)