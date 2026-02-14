from utils.db_context import db_connection
from utils.media_utils import get_verfied_image_path


class DoctorService:

    @staticmethod
    def get_all_departments():
        with db_connection() as cursor:
            cursor.execute(
                """
                SELECT department_id, name 
                FROM departments 
                WHERE name NOT IN ('Other/Unspecified', 'PENDING_VERIFICATION_DEPT') 
                ORDER BY name ASC
            """
            )
            return cursor.fetchall()

    @staticmethod
    def get_specializations(department_id=None):
        query = """
            SELECT specialization_id, name 
            FROM specializations 
            WHERE name NOT IN ('Unknown', 'Other', 'PENDING_VERIFICATION') 
        """
        params = []
        if department_id:
            query += " AND department_id = %s"
            params.append(department_id)

        query += " ORDER BY name ASC"

        with db_connection() as cursor:
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

    @staticmethod
    def get_filtered_doctors(
        search_name=None, department_id=None, specialization_id=None, accepting_new=None
    ):
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name,
                d.profile_photo_url, d.accepting_new_patients,
                s.name AS specialization_name,
                dept.name AS department_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            WHERE u.user_type = 'doctor'
              AND u.account_status = 'active'
              AND d.verification_status = 'approved' 
        """
        params = []

        if search_name:
            query += " AND (LOWER(u.first_name) LIKE %s OR LOWER(u.last_name) LIKE %s)"
            like_term = f"%{search_name.lower()}%"
            params.extend([like_term, like_term])

        if department_id:
            query += " AND d.department_id = %s"
            params.append(department_id)

        if specialization_id:
            query += " AND d.specialization_id = %s"
            params.append(specialization_id)

        if accepting_new is not None:
            query += " AND d.accepting_new_patients = %s"
            params.append(1 if accepting_new else 0)

        query += " ORDER BY u.last_name ASC"

        with db_connection() as cursor:
            cursor.execute(query, tuple(params))
            doctors = cursor.fetchall()

        # Format Data for the View
        for doc in doctors:
            doc["profile_image_path"] = get_verfied_image_path(
                doc["profile_photo_url"], "images/profile_pics/default_avatar.png"
            )

        return doctors

    @staticmethod
    def get_doctor_details(doctor_id: int):
        query = """
            SELECT
                u.user_id, u.first_name, u.last_name, u.email, u.phone,
                d.profile_photo_url, d.biography, d.accepting_new_patients,
                d.medical_school, d.graduation_year, d.certifications,
                dl.address, dl.city, dl.state, dl.zip_code, dl.phone_number as clinic_phone,
                s.name AS specialization_name, s.description as specialization_description,
                dept.name AS department_name, dept.description as department_description
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            LEFT JOIN departments dept ON d.department_id = dept.department_id
            LEFT JOIN doctor_locations dl ON d.user_id = dl.doctor_id AND dl.is_primary = 1
            WHERE u.user_id = %s AND u.user_type = 'doctor'
        """

        with db_connection() as cursor:
            cursor.execute(query, (doctor_id,))
            doctor = cursor.fetchone()

            if doctor:
                doctor["profile_image_path"] = get_verfied_image_path(
                    doctor["profile_photo_url"],
                    "images/profile_pics/default_avatar.png",
                )

                # Fetch Documents
                cursor.execute(
                    """
                    SELECT document_type, file_name, file_path 
                    FROM doctor_documents WHERE doctor_id = %s
                """,
                    (doctor_id,),
                )
                doctor["documents"] = cursor.fetchall()

        return doctor
