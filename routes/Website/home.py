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
    """Fetches ALL departments from the database, including image filename."""
    departments_data = []
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        if not conn or not conn.is_connected():
            raise ConnectionError("Database connection failed")

        cursor = conn.cursor(dictionary=True)

        # Query ALL departments, including the image_filename column
        # Ensure the 'image_filename' column exists in your 'departments' table!
        query = """
            SELECT
                department_id,
                name,
                description,
                image_filename  -- Fetch the image filename
            FROM departments
            ORDER BY name ASC
        """
        # Removed ORDER BY FIELD as we are fetching all

        cursor.execute(query)
        results = cursor.fetchall()

        # Process results to create the final image URL path
        for dept in results:
            # Get filename from DB, default to placeholder if NULL or empty
            db_filename = dept.get('image_filename')
            if db_filename:
                 # Construct path relative to static folder root
                dept['image_url'] = f"images/{db_filename}"
            else:
                # Use a generic placeholder if DB field is empty/NULL
                dept['image_url'] = "images/placeholder.jpg" # Default department image
                current_app.logger.debug(f"No image filename found in DB for department: {dept.get('name')}. Using placeholder.")

            # Optional cleanup: remove raw filename if not needed in template
            # if 'image_filename' in dept:
            #    del dept['image_filename']

            departments_data.append(dept)

    except mysql.connector.Error as db_err:
        # Check if the error is due to the missing column 'image_filename'
        if db_err.errno == 1054 and 'image_filename' in str(db_err):
             current_app.logger.error(f"Database error fetching departments: Column 'image_filename' likely missing in 'departments' table. Please run ALTER TABLE departments ADD COLUMN image_filename VARCHAR(255) NULL; Error: {db_err}")
        else:
             current_app.logger.error(f"Database error fetching all departments: {db_err}")
    except ConnectionError as conn_err:
         current_app.logger.error(f"{conn_err} fetching all departments.")
    except Exception as e:
        current_app.logger.error(f"Unexpected error fetching all departments: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

    current_app.logger.info(f"Fetched and processed {len(departments_data)} departments from database.")
    return departments_data


# --- Main Homepage Route ---
@home_bp.route('/')
def index():
    """
    Renders the public homepage.
    Fetches ALL departments from the database for the categories section.
    """
    # Fetch dynamic data for the homepage categories using the updated DB function
    all_departments = get_all_departments_from_db()

    # Select *which* departments to feature on the homepage
    # Option 1: Define names to feature
    featured_names = [
        "Cardiology", "Neurology", "Dermatology",
        "Orthopedics", "Nutrition Services", "General Medicine" # Example 6
    ]
    featured_departments = [dept for dept in all_departments if dept['name'] in featured_names]

    # Option 2: Just take the first N departments (less specific)
    # featured_departments = all_departments[:6] # Example: take first 6 alphabetically

    # Ensure the order matches the desired display if using featured_names
    # This preserves the order from featured_names list
    if featured_names:
        name_to_dept = {dept['name']: dept for dept in featured_departments}
        featured_departments = [name_to_dept.get(name) for name in featured_names if name_to_dept.get(name)]


    current_app.logger.info(f"Displaying {len(featured_departments)} featured departments on homepage.")

    # Render the template, passing the *featured* list
    return render_template('Website/home.html', featured_departments=featured_departments)