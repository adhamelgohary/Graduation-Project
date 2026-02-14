from utils.db_context import db_connection
from utils.media_utils import get_verfied_image_path
from utils.text_helpers import create_snippet


class NutritionService:
    @staticmethod
    def get_specialists(limit=4):
        # Hardcoded ID from your original code (21 = Nutrition)
        query = """
            SELECT u.user_id, u.first_name, u.last_name, 
                   d.profile_photo_url, d.biography,
                   s.name AS specialization_name
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            WHERE u.user_type = 'doctor' 
              AND u.account_status = 'active'
              AND d.department_id = 21 
              AND d.verification_status = 'approved'
            ORDER BY u.last_name ASC
            LIMIT %s
        """
        with db_connection() as cursor:
            cursor.execute(query, (limit,))
            specialists = cursor.fetchall()

        for doc in specialists:
            doc["profile_picture_url"] = get_verfied_image_path(
                doc["profile_photo_url"], "images/profile_pics/default_avatar.png"
            )
            doc["short_bio"] = create_snippet(doc["biography"], 100)

        return specialists

    @staticmethod
    def get_diet_plans(public_only=True):
        query = "SELECT * FROM diet_plans WHERE is_public = 1 ORDER BY plan_name"
        with db_connection() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    @staticmethod
    def get_plan_details(plan_id: int):
        with db_connection() as cursor:
            # 1. Get Plan Info
            cursor.execute("SELECT * FROM diet_plans WHERE plan_id = %s", (plan_id,))
            plan = cursor.fetchone()

            if not plan:
                return None

            # 2. Get Meals
            cursor.execute(
                """
                SELECT * FROM diet_plan_meals 
                WHERE plan_id = %s 
                ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack'), time_of_day
            """,
                (plan_id,),
            )
            meals = cursor.fetchall()

            # 3. Get Foods per Meal
            meal_data = []
            for meal in meals:
                cursor.execute(
                    "SELECT * FROM diet_plan_food_items WHERE meal_id = %s",
                    (meal["meal_id"],),
                )
                foods = cursor.fetchall()
                meal_data.append({"meal_info": meal, "food_items_list": foods})

        return {"plan": plan, "meals": meal_data}
