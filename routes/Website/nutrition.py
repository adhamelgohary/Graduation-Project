from flask import Blueprint, render_template, request, jsonify, abort, current_app, url_for
from db import get_db_connection
import random
import logging

logger = logging.getLogger(__name__)

nutrition_bp = Blueprint(
    'nutrition_bp',
    __name__,
    template_folder='../../templates/Website/Nuitrition',
    static_folder='../../static/Website/',
    static_url_path='/static/Website/'
)

# --- Helper: URL Safe Name (can be shared or defined in a utils.py) ---
def make_url_safe_name_nutrition(name):
    if not name: return ""
    s = name.lower().replace('&', 'and').replace(' ', '-')
    s = ''.join(c for c in s if c.isalnum() or c == '-')
    return '-'.join(filter(None, s.split('-')))

# --- Nutrition Landing Page ---
@nutrition_bp.route('/')
def nutrition_landing_page():
    return render_template('nutrition_landing.html')

# --- Diet Plan Routes (largely the same, ensure data is passed correctly) ---
@nutrition_bp.route('/diet-plans')
def list_diet_plans():
    conn = None
    cursor = None
    plans = []
    try:
        conn = get_db_connection()
        if not conn:
            raise Exception("Database connection failed")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT plan_id, plan_name, description, plan_type, calories, target_conditions
            FROM diet_plans 
            WHERE is_public = 1 
            ORDER BY plan_name
        """
        cursor.execute(query)
        plans = cursor.fetchall()
        for p in plans:
             # Create a direct link to the details page
            p['details_url'] = url_for('nutrition_bp.plan_details', plan_id=p['plan_id'])
    except Exception as e:
        logger.error(f"Error fetching diet plans: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return render_template('list_diet_plans.html', plans=plans)

@nutrition_bp.route('/diet-plan/<int:plan_id>')
def plan_details(plan_id):
    conn = None
    cursor = None
    plan = None
    meal_data = []
    try:
        conn = get_db_connection()
        if not conn:
            raise Exception("Database connection failed")
        cursor = conn.cursor(dictionary=True)
        
        query_plan = """
            SELECT dp.plan_id, dp.plan_name, dp.description, dp.plan_type, dp.calories, 
                   dp.protein_grams, dp.carbs_grams, dp.fat_grams, dp.fiber_grams, dp.sodium_mg,
                   dp.target_conditions, u.username as creator_username
            FROM diet_plans dp
            LEFT JOIN users u ON dp.creator_id = u.user_id
            WHERE dp.plan_id = %s AND dp.is_public = 1 
            LIMIT 1
        """
        cursor.execute(query_plan, (plan_id,))
        plan = cursor.fetchone()

        if not plan:
            abort(404, description="Diet plan not found or not public.")

        query_meals = """
            SELECT meal_id, meal_name, meal_type, description, calories, 
                   protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, time_of_day
            FROM diet_plan_meals 
            WHERE plan_id = %s 
            ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack', 'other'), time_of_day
        """
        cursor.execute(query_meals, (plan_id,))
        meals = cursor.fetchall()

        for meal in meals:
            query_items = """
                SELECT item_id, food_name, serving_size, calories, protein_grams, carbs_grams, 
                       fat_grams, notes, alternatives
                FROM diet_plan_food_items 
                WHERE meal_id = %s
            """
            cursor.execute(query_items, (meal['meal_id'],))
            items = cursor.fetchall()
            meal_data.append({'meal_info': meal, 'items': items})
            
    except Exception as e:
        logger.error(f"Error fetching diet plan details for ID {plan_id}: {e}", exc_info=True)
        abort(500, description="Error retrieving diet plan details.")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    if not plan:
        abort(404, description="Diet plan not found.")
        
    return render_template('plan_details.html', plan=plan, meal_data=meal_data)

# --- Food Library Search Routes (same as before) ---
@nutrition_bp.route('/food-search')
def food_search_page():
    return render_template('food_search.html')

@nutrition_bp.route('/api/food-library/search')
def api_search_food_library():
    query_param = request.args.get('q', '').strip()
    if not query_param or len(query_param) < 2:
        return jsonify({'error': 'Query must be at least 2 characters long'}), 400
    conn = None
    cursor = None
    food_list = []
    try:
        conn = get_db_connection()
        if not conn: raise Exception("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        sql_query = """
            SELECT food_item_id as id, item_name as name, serving_size as serving, 
                   calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg
            FROM food_item_library 
            WHERE item_name LIKE %s AND is_active = 1 
            ORDER BY item_name LIMIT 20
        """
        cursor.execute(sql_query, (f'%{query_param}%',))
        food_list = cursor.fetchall()
    except Exception as e:
        logger.error(f"API Food Search Error for query '{query_param}': {e}", exc_info=True)
        return jsonify({'error': 'Error searching food items.'}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return jsonify(food_list)

# --- Bot API Endpoints ---
@nutrition_bp.route('/api/bot/chat', methods=['POST'])
def api_bot_chat():
    # (Keep the chat logic from the previous response, it doesn't need to change based on plan recommendation)
    data = request.get_json()
    user_message = data.get('message', '').strip().lower()
    reply = ""

    if not user_message:
        return jsonify({'reply': "I didn't quite catch that. Could you please repeat?"})

    if "bmr" in user_message:
        reply = ("BMR is your Basal Metabolic Rate - calories burned at rest. "
                 "The Mifflin-St Jeor equation is often used:\n"
                 "Men: (10 × weight in kg) + (6.25 × height in cm) - (5 × age in years) + 5\n"
                 "Women: (10 × weight in kg) + (6.25 × height in cm) - (5 × age in years) - 161\n"
                 "Your TDEE (Total Daily Energy Expenditure) is BMR multiplied by an activity factor.")
    elif "hello" in user_message or "hi" in user_message:
        reply = "Hello! I'm your Nutrition Bot. How can I assist you today? You can ask about BMR, search for food, or get diet plan suggestions."
    elif "diet plan" in user_message or "meal plan" in user_message:
        reply = "Great! Please go to the 'Diet Plan' tab in this chat window. You can specify allergies, health conditions, and an approximate weight range, and I'll recommend some existing plans."
    elif "food" in user_message and "search" not in user_message:
        reply = "To find nutrition information for specific foods, please use the 'Food Search' tab."
    elif "thank" in user_message: 
        reply = "You're welcome! Let me know if there's anything else."
    elif "bye" in user_message or "goodbye" in user_message:
        reply = "Goodbye! Have a healthy day."
    else:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor(dictionary=True)
                sql_food_check = """
                    SELECT item_name, serving_size, calories, protein_grams, carbs_grams, fat_grams 
                    FROM food_item_library 
                    WHERE item_name LIKE %s AND is_active = 1 
                    LIMIT 1
                """
                cursor.execute(sql_food_check, (f'%{user_message}%',))
                food_item = cursor.fetchone()
                if food_item:
                    reply = (f"For {food_item['item_name']} ({food_item['serving_size']}):\n"
                             f"Calories: ~{food_item['calories'] or 'N/A'}\n"
                             f"Protein: ~{food_item['protein_grams'] or 'N/A'}g\n"
                             f"Carbs: ~{food_item['carbs_grams'] or 'N/A'}g\n"
                             f"Fat: ~{food_item['fat_grams'] or 'N/A'}g\n"
                             "For more details or other foods, please use the 'Food Search' tab.")
                else:
                    responses = [
                        "I'm sorry, I don't have specific information on that. Try the 'Food Search' tab or ask a general nutrition question.",
                        "My knowledge is expanding! For now, I can help with BMR, general food lookups, or diet plan suggestions via the tabs.",
                        "Could you please rephrase? Or, try searching for food items in the 'Food Search' tab."
                    ]
                    reply = random.choice(responses)
        except Exception as e:
            logger.error(f"Bot chat food lookup error: {e}", exc_info=True)
            reply = "I had a little trouble looking that up. Please try again or rephrase."
        finally:
            if cursor: cursor.close()
            if conn and conn.is_connected(): conn.close()
            
    return jsonify({'reply': reply})


@nutrition_bp.route('/api/bot/recommend_diet_plans', methods=['POST']) # Renamed endpoint
def api_recommend_diet_plans():
    data = request.get_json()
    logger.info(f"Diet plan recommendation request data: {data}")

    allergies_input = data.get('allergies', []) # e.g., ['dairy', 'nuts'] - these are names from your `allergies` table
    health_condition_input = data.get('health_condition', 'none') # e.g., 'diabetes' - from your `conditions` table or a simplified list
    weight_range_input = data.get('weight_range', 'none') # e.g., '56-76'

    # --- LOGIC TO RECOMMEND EXISTING DIET PLANS ---
    # 1. Build a dynamic SQL query for `diet_plans` table.
    # 2. Filter based on `health_condition_input` (matching `target_conditions` in `diet_plans`).
    # 3. Filter based on `allergies_input`: This is harder with the current schema for `diet_plans`.
    #    - `diet_plans` doesn't directly link to disallowed allergens.
    #    - Option A: Store common "tags" or disallowed allergens in `diet_plans.description` or a new field.
    #    - Option B (Complex): Check if ANY `diet_plan_food_items` within a plan contain allergens. This requires many joins and is slow for a recommendation query.
    #    - For now, we'll primarily filter on `target_conditions` and maybe `plan_type`.
    # 4. Consider `weight_range_input` to filter `diet_plans.calories` if applicable.

    recommendations_html = "<h4>Recommended Diet Plans For You:</h4>"
    recommended_plans = []
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise Exception("DB connection failed")
        cursor = conn.cursor(dictionary=True)

        sql_clauses = ["dp.is_public = 1"]
        sql_params = []

        if health_condition_input and health_condition_input != 'none':
            sql_clauses.append("LOWER(dp.target_conditions) LIKE %s")
            sql_params.append(f"%{health_condition_input.lower()}%")
        
        # Weight range to calorie mapping (very approximate, customize this)
        min_calories, max_calories = None, None
        if weight_range_input == '40-55': min_calories, max_calories = 1200, 1800
        elif weight_range_input == '56-76': min_calories, max_calories = 1600, 2200
        elif weight_range_input == '77-90': min_calories, max_calories = 2000, 2800
        elif weight_range_input == '90+': min_calories = 2500 # No max, or set a high one

        if min_calories is not None:
            sql_clauses.append("dp.calories >= %s")
            sql_params.append(min_calories)
        if max_calories is not None:
            sql_clauses.append("dp.calories <= %s")
            sql_params.append(max_calories)

        # Allergy filtering is tricky here. We might need to rely on `plan_name` or `description`
        # if allergens are mentioned there, or assume general plans and let user verify details.
        # A more robust solution would require better schema for allergen tagging of plans.
        if allergies_input:
            for allergy in allergies_input:
                # This tries to exclude plans if the allergy is mentioned in name/desc - very basic
                sql_clauses.append("NOT (LOWER(dp.plan_name) LIKE %s OR LOWER(dp.description) LIKE %s)")
                sql_params.append(f"%{allergy.lower()}%")
                sql_params.append(f"%{allergy.lower()}%")


        where_clause = " AND ".join(sql_clauses)
        query = f"""
            SELECT dp.plan_id, dp.plan_name, dp.description, dp.calories
            FROM diet_plans dp
            WHERE {where_clause}
            ORDER BY FIELD(dp.plan_type, 'medical', 'custom', 'weight_loss', 'standard'), dp.plan_name 
            LIMIT 5 
        """ 
        # logger.debug(f"Recommend query: {query} with params {sql_params}")
        cursor.execute(query, tuple(sql_params))
        recommended_plans_db = cursor.fetchall()

        if recommended_plans_db:
            recommendations_html += "<ul class='meal-list'>" # Re-use some bot styling
            for plan in recommended_plans_db:
                plan_url = url_for('nutrition_bp.plan_details', plan_id=plan['plan_id'], _external=True)
                recommendations_html += (
                    f"<li><strong><a href='{plan_url}' target='_blank'>{plan['plan_name']}</a></strong>"
                    f" (Approx. {plan['calories'] or 'N/A'} cals)<br>"
                    f"<small>{plan['description'][:100] if plan['description'] else ''}...</small></li>"
                )
            recommendations_html += "</ul>"
            recommendations_html += "<p><em>Click on a plan name to see full details. Please check the details carefully for any specific dietary needs or allergies.</em></p>"
        else:
            recommendations_html += "<p>Sorry, I couldn't find specific existing diet plans matching all your criteria. You might want to explore our <a href='" + url_for('nutrition_bp.list_diet_plans', _external=True) + "' target='_blank'>full list of diet plans</a> or consult with a nutritionist for a custom plan.</p>"
            recommendations_html += "<p>Consider broadening your criteria if you'd like me to try again.</p>"

    except Exception as e:
        logger.error(f"Error recommending diet plans: {e}", exc_info=True)
        recommendations_html = "<p class='bot-message error'>An error occurred while trying to find diet plan recommendations. Please try again.</p>"
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
        
    return jsonify({'plan_html': recommendations_html})

@nutrition_bp.route('/bmr-calculator')
def bmr_calculator_page():
    return render_template('bmr_calculator.html')