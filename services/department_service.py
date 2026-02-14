from utils.db_context import db_connection
from utils.media_utils import get_verfied_image_path
from utils.template_helpers import get_current_year  # Example of reusing logic


class DepartmentService:

    @staticmethod
    def get_all_departments():
        # Reusing the simple image check logic
        with db_connection() as cursor:
            cursor.execute(
                """
                SELECT department_id, name, description, image_filename
                FROM departments 
                ORDER BY name ASC
            """
            )
            departments = cursor.fetchall()

        for dept in departments:
            dept["image_path"] = get_verfied_image_path(
                dept["image_filename"], "images/departments/placeholder.jpg"
            )
        return departments

    @staticmethod
    def get_department_details(dept_id: int):
        with db_connection() as cursor:
            cursor.execute(
                "SELECT * FROM departments WHERE department_id = %s", (dept_id,)
            )
            dept = cursor.fetchone()

            if dept:
                dept["image_path"] = get_verfied_image_path(
                    dept["image_filename"], "images/departments/placeholder.jpg"
                )

                # Assign specific CSS based on name (Migrated from your old code)
                name = dept.get("name", "")
                if name == "Cardiology":
                    dept["meta"] = {
                        "css": "Website/Departments/cardio.css",
                        "icon": "fa-heart-pulse",
                    }
                elif name == "Neurology":
                    dept["meta"] = {
                        "css": "Website/Departments/neuro.css",
                        "icon": "fa-brain",
                    }
                # ... Add other cases here
                else:
                    dept["meta"] = {
                        "css": "Website/generic_department.css",
                        "icon": "fa-stethoscope",
                    }

        return dept

    @staticmethod
    def get_conditions_by_department(dept_id: int, search_term: str = None):
        query = """
            SELECT 
                c.condition_id, c.condition_name, c.description, 
                c.condition_image_filename,
                s.name AS specialization_name
            FROM conditions c
            LEFT JOIN specializations s ON c.specialization_id = s.specialization_id
            WHERE c.department_id = %s AND c.is_active = TRUE 
        """
        params = [dept_id]

        if search_term:
            query += (
                " AND (LOWER(c.condition_name) LIKE %s OR LOWER(c.description) LIKE %s)"
            )
            term = f"%{search_term.lower()}%"
            params.extend([term, term])

        with db_connection() as cursor:
            cursor.execute(query, tuple(params))
            conditions = cursor.fetchall()

        for cond in conditions:
            cond["image_path"] = get_verfied_image_path(
                cond["condition_image_filename"],
                "images/conditions/disease_placeholder.png",
            )
        return conditions

    
    @staticmethod
    def get_condition_details(condition_id: int):
        with db_connection() as cursor:
            # 1. Main Details
            cursor.execute("""
                SELECT c.*, c.condition_name AS name, 
                       dept.name AS department_name, dept.department_id,
                       s.name AS specialization_name
                FROM conditions c
                LEFT JOIN departments dept ON c.department_id = dept.department_id
                LEFT JOIN specializations s ON c.specialization_id = s.specialization_id
                WHERE c.condition_id = %s AND c.is_active = TRUE
            """, (condition_id,))
            condition = cursor.fetchone()
            
            if not condition:
                return None, []

            # 2. Image Processing
            condition["image_url"] = get_verfied_image_path(
                condition["condition_image_filename"], 
                "images/conditions/disease_placeholder.png"
            )

            # 3. Text Splitting (Legacy logic support)
            # Converts comma-separated strings in DB to lists for the frontend
            for field in ["regular_symptoms_text", "causes_text", "risk_factors_text", "complications_text"]:
                list_key = field.replace("_text", "_list")
                condition[list_key] = [x.strip() for x in (condition.get(field) or "").split(",") if x.strip()]

            # 4. Fetch Related Doctors (Logic moved from view)
            doctors = []
            if condition.get("department_id"):
                cursor.execute("""
                    SELECT u.user_id, u.first_name, u.last_name, d.profile_photo_url, s.name AS specialization_name
                    FROM users u JOIN doctors d ON u.user_id = d.user_id
                    LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
                    WHERE d.department_id = %s AND d.verification_status = 'approved'
                    LIMIT 4
                """, (condition["department_id"],))
                doctors = cursor.fetchall()
                for d in doctors:
                    d["profile_picture_url"] = get_verfied_image_path(d["profile_photo_url"], "images/profile_pics/default_avatar.png")

            return condition, doctors