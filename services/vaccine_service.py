from utils.db_context import db_connection
from utils.media_utils import get_verfied_image_path


class VaccineService:
    @staticmethod
    def get_categories():
        with db_connection() as cursor:
            cursor.execute("SELECT * FROM vaccine_categories WHERE is_active = 1")
            cats = cursor.fetchall()

        for cat in cats:
            cat["image_path"] = get_verfied_image_path(
                cat.get("image_filename"),
                "images/vaccines/default.png",  # Adjust default
            )
        return cats

    @staticmethod
    def get_vaccine_details(vaccine_id: int):
        with db_connection() as cursor:
            cursor.execute(
                """
                SELECT v.*, vc.category_name
                FROM vaccines v
                LEFT JOIN vaccine_categories vc ON v.category_id = vc.category_id
                WHERE v.vaccine_id = %s AND v.is_active = 1
            """,
                (vaccine_id,),
            )
            return cursor.fetchone()
