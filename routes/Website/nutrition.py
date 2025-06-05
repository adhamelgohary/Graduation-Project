# your_project/routes/Website/nutrition.py

from flask import Blueprint, render_template, request, jsonify, abort, current_app, url_for
from db import get_db_connection
import random
import logging
from datetime import datetime, time, timedelta 
import os # Added for os.path.join if needed for image path checking

logger = logging.getLogger(__name__)

nutrition_bp = Blueprint(
    'nutrition_bp',
    __name__,
    template_folder='../../templates/Website/Nuitrition', 
    static_folder='../../static/Website/',
    static_url_path='/static/Website/'
)

# --- Helper: URL Safe Name ---
def make_url_safe_name_nutrition(name):
    if not name: return ""
    s = name.lower().replace('&', 'and').replace(' ', '-')
    s = ''.join(c for c in s if c.isalnum() or c == '-')
    return '-'.join(filter(None, s.split('-')))

# --- Get Nutrition Specialists ---
def get_nutrition_specialists():
    conn = None
    cursor = None
    specialists = []
    NUTRITION_DEPARTMENT_ID = 21 
    try:
        conn = get_db_connection()
        if not conn:
            logger.error("DB Connection failed for get_nutrition_specialists")
            return [] # Return empty list on DB connection failure
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT u.user_id, u.first_name, u.last_name, 
                   d.profile_photo_url, s.name AS specialization_name, d.biography
            FROM users u
            JOIN doctors d ON u.user_id = d.user_id
            LEFT JOIN specializations s ON d.specialization_id = s.specialization_id
            WHERE u.user_type = 'doctor' 
              AND u.account_status = 'active'
              AND d.department_id = %s
              AND d.verification_status = 'approved'
            ORDER BY u.last_name ASC, u.first_name ASC
            LIMIT 4 
        """
        cursor.execute(query, (NUTRITION_DEPARTMENT_ID,))
        specialists_raw = cursor.fetchall()

        for doc in specialists_raw:
            path_relative_to_static_from_db = doc.get('profile_photo_url')
            doc['profile_picture_url'] = url_for('static', filename='images/profile_pics/default_avatar.png')
            if path_relative_to_static_from_db:
                if current_app and current_app.static_folder:
                    # This assumes path_relative_to_static_from_db is like "uploads/profile_pics/filename.jpg"
                    # No need for os.path.join if the path is already correct relative to static folder root
                    full_abs_path_to_check = os.path.normpath(os.path.join(current_app.static_folder, path_relative_to_static_from_db))
                    if not os.path.exists(full_abs_path_to_check):
                        logger.warning(f"Nutrition specialist profile image not found: {full_abs_path_to_check} (DB path: {path_relative_to_static_from_db})")
                    else:
                        doc['profile_picture_url'] = url_for('static', filename=path_relative_to_static_from_db)
                else: 
                     doc['profile_picture_url'] = url_for('static', filename=path_relative_to_static_from_db)
            
            bio = doc.get('biography')
            doc['short_bio'] = (bio[:100] + '...') if bio and len(bio) > 100 else bio
            specialists.append(doc)

    except Exception as e:
        logger.error(f"Error fetching nutrition specialists: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return specialists

# --- Nutrition Landing Page ---
@nutrition_bp.route('/')
def nutrition_landing_page():
    nutrition_specialists = get_nutrition_specialists()
    return render_template('nutrition_landing.html', specialists=nutrition_specialists)

# --- Diet Plan Routes ---
@nutrition_bp.route('/diet-plans')
def list_diet_plans():
    conn = None
    cursor = None
    plans = []
    nutrition_specialists = [] # Initialize
    try:
        conn = get_db_connection()
        if not conn:
            raise Exception("Database connection failed")
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT plan_id, plan_name, description, plan_type, calories, 
                   protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, 
                   target_conditions
            FROM diet_plans 
            WHERE is_public = 1 
            ORDER BY plan_name
        """
        cursor.execute(query)
        plans = cursor.fetchall()
        for p in plans:
            p['details_url'] = url_for('nutrition_bp.plan_details', plan_id=p['plan_id'])
        
        nutrition_specialists = get_nutrition_specialists() # Fetch specialists

    except Exception as e:
        logger.error(f"Error fetching diet plans: {e}", exc_info=True)
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return render_template('list_diet_plans.html', plans=plans, specialists=nutrition_specialists)

@nutrition_bp.route('/diet-plan/<int:plan_id>')
def plan_details(plan_id):
    conn = None
    cursor = None
    plan = None
    meal_data = []
    nutrition_specialists = [] # Initialize
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
                   protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg, 
                   time_of_day
            FROM diet_plan_meals 
            WHERE plan_id = %s 
            ORDER BY FIELD(meal_type, 'breakfast', 'lunch', 'dinner', 'snack', 'other'), time_of_day
        """
        cursor.execute(query_meals, (plan_id,))
        meals = cursor.fetchall()

        for meal in meals:
            if isinstance(meal.get('time_of_day'), timedelta):
                total_seconds = int(meal['time_of_day'].total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                meal['time_of_day_obj'] = time(hours, minutes, seconds) 
            elif isinstance(meal.get('time_of_day'), time):
                meal['time_of_day_obj'] = meal['time_of_day']
            else:
                meal['time_of_day_obj'] = None
            
            query_food_items = """
                SELECT item_id, food_name, serving_size, calories, 
                       protein_grams, carbs_grams, fat_grams, 
                       notes, alternatives
                FROM diet_plan_food_items 
                WHERE meal_id = %s
            """
            cursor.execute(query_food_items, (meal['meal_id'],))
            food_items_for_meal = cursor.fetchall()
            meal_data.append({'meal_info': meal, 'food_items_list': food_items_for_meal})
        
        nutrition_specialists = get_nutrition_specialists() # Fetch specialists for this page too
            
    except Exception as e:
        logger.error(f"Error fetching diet plan details for ID {plan_id}: {e}", exc_info=True)
        abort(500, description="Error retrieving diet plan details.")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    
    if not plan: # This check should be redundant if the first one aborts
        abort(404, description="Diet plan not found.")
        
    return render_template('plan_details.html', plan=plan, meal_data=meal_data, specialists=nutrition_specialists)

# ... (food_search_page, api_search_food_library, api_bot_chat, _get_diet_plan_recommendations, api_recommend_diet_plans_endpoint, bmr_calculator_page remain the same) ...
@nutrition_bp.route('/food-search')
def food_search_page():
    return render_template('food_search.html')

@nutrition_bp.route('/api/food-library/search')
def api_search_food_library():
    query_param = request.args.get('q', '').strip()
    if not query_param or len(query_param) < 2:
        return jsonify({'error': 'Query must be at least 2 characters long'}), 400
    conn = None; cursor = None; food_list = []
    try:
        conn = get_db_connection()
        if not conn: raise Exception("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        sql_query = "SELECT food_item_id as id, item_name as name, serving_size as serving, calories, protein_grams, carbs_grams, fat_grams, fiber_grams, sodium_mg FROM food_item_library WHERE item_name LIKE %s AND is_active = 1 ORDER BY item_name LIMIT 20"
        cursor.execute(sql_query, (f'%{query_param}%',))
        food_list = cursor.fetchall()
    except Exception as e:
        logger.error(f"API Food Search Error for query '{query_param}': {e}", exc_info=True)
        return jsonify({'error': 'Error searching food items.'}), 500
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return jsonify(food_list)

@nutrition_bp.route('/api/bot/chat', methods=['POST'])
def api_bot_chat():
    data = request.get_json()
    payload = data.get('payload', {})
    state = data.get('state', {}) 
    action_type = payload.get('type')
    action_value = payload.get('value')
    reply_text = ""
    reply_options = []
    next_state = state.copy() 
    if action_type == "text_input" and action_value.lower() in ["hi", "hello", "menu", "start over"]:
        next_state = {} 
        reply_text = "Hello! I'm your Nutrition Bot. How can I assist you today?"
        reply_options = [
            {"label": "Suggest a Diet Plan", "payload": {"type": "action", "value": "suggest_plan_start"}},
            {"label": "Explain BMR", "payload": {"type": "action", "value": "explain_bmr"}},
            {"label": "Ask a General Question", "payload": {"type": "action", "value": "ask_general_question_prompt"}}
        ]
    elif action_type == "action" and action_value == "explain_bmr":
        reply_text = ("BMR is your Basal Metabolic Rate - calories burned at rest. "
                      "The Mifflin-St Jeor equation is often used:\n"
                      "Men: (10 × weight in kg) + (6.25 × height in cm) - (5 × age in years) + 5\n"
                      "Women: (10 × weight in kg) + (6.25 × height in cm) - (5 × age in years) - 161\n"
                      "Your TDEE (Total Daily Energy Expenditure) is BMR multiplied by an activity factor.\n\nAnything else I can help with?")
        reply_options = [
            {"label": "Suggest a Diet Plan", "payload": {"type": "action", "value": "suggest_plan_start"}},
            {"label": "Back to Main Menu", "payload": {"type": "action", "value": "start_over"}}
        ]
    elif action_type == "action" and action_value == "ask_general_question_prompt":
        reply_text = "Sure, what's your nutrition question? (I'll do my best to answer or guide you to resources)"
        next_state['awaiting'] = 'general_question_text'
    elif action_type == "action" and action_value == "suggest_plan_start":
        next_state = {'current_flow': 'diet_plan', 'step': 'allergies', 'allergies': []} 
        reply_text = "Okay, I can help with diet plan suggestions! First, do you have any of these common allergies? (Select all that apply, then click 'Done with Allergies')"
        allergies = ["Dairy", "Nuts", "Peanuts", "Shellfish", "Fish", "Eggs", "Wheat/Gluten", "Soy"]
        reply_options = [{"label": allergy, "payload": {"type": "select_allergy", "value": allergy.lower()}} for allergy in allergies]
        reply_options.append({"label": "Done with Allergies", "payload": {"type": "action", "value": "collect_allergies_done"}})
    elif payload.get("type") == "select_allergy":
        selected_allergy = payload.get("value")
        if 'allergies' not in next_state: next_state['allergies'] = [] 
        
        if selected_allergy in next_state['allergies']:
            next_state['allergies'].remove(selected_allergy)
            reply_text = f"Okay, '{selected_allergy.title()}' deselected. Any other allergies? Or click 'Done with Allergies'."
        else: 
            next_state['allergies'].append(selected_allergy)
            reply_text = f"Okay, noted '{selected_allergy.title()}'. Any other allergies? Or click 'Done with Allergies'."
        
        allergies_master_list = ["Dairy", "Nuts", "Peanuts", "Shellfish", "Fish", "Eggs", "Wheat/Gluten", "Soy"]
        reply_options = []
        for allergy_item in allergies_master_list:
            label_prefix = "✅ " if allergy_item.lower() in next_state.get('allergies', []) else ""
            reply_options.append({"label": label_prefix + allergy_item, "payload": {"type": "select_allergy", "value": allergy_item.lower()}})
        reply_options.append({"label": "Done with Allergies", "payload": {"type": "action", "value": "collect_allergies_done"}})
    elif action_type == "action" and action_value == "collect_allergies_done":
        next_state['step'] = 'weight_range'
        reply_text = f"Selected allergies: {', '.join(next_state.get('allergies', ['None'])) if next_state.get('allergies') else 'None'}.\nNow, what's your approximate weight range?"
        reply_options = [
            {"label": "General / Not Sure", "payload": {"type": "select_weight", "value": "none"}},
            {"label": "40-55 kg", "payload": {"type": "select_weight", "value": "40-55"}},
            {"label": "56-76 kg", "payload": {"type": "select_weight", "value": "56-76"}},
            {"label": "77-90 kg", "payload": {"type": "select_weight", "value": "77-90"}},
            {"label": "90+ kg", "payload": {"type": "select_weight", "value": "90+"}},
        ]
    elif payload.get("type") == "select_weight":
        next_state['weight_range'] = payload.get("value")
        next_state['step'] = 'health_condition'
        reply_text = f"Okay, weight range: {payload.get('value') if payload.get('value') != 'none' else 'General'}.\nDo you have any specific health conditions to consider for your diet?"
        reply_options = [
            {"label": "None / General Wellness", "payload": {"type": "select_health_condition", "value": "none"}},
            {"label": "Diabetes", "payload": {"type": "select_health_condition", "value": "diabetes"}},
            {"label": "Hypertension", "payload": {"type": "select_health_condition", "value": "hypertension"}},
            {"label": "Heart Disease", "payload": {"type": "select_health_condition", "value": "heart"}},
            {"label": "Kidney Disease", "payload": {"type": "select_health_condition", "value": "kidney"}},
            {"label": "IBS", "payload": {"type": "select_health_condition", "value": "ibs"}},
        ]
    elif payload.get("type") == "select_health_condition":
        next_state['health_condition'] = payload.get("value")
        next_state['step'] = 'recommend'
        reply_text = f"Understood. Health condition: {payload.get('value') if payload.get('value') != 'none' else 'General Wellness'}.\nLet me find some plan suggestions for you..."
        recommendation_request_data = {
            'allergies': next_state.get('allergies', []),
            'health_condition': next_state.get('health_condition', 'none'),
            'weight_range': next_state.get('weight_range', 'none')
        }
        recommendation_response = _get_diet_plan_recommendations(recommendation_request_data)
        current_state_summary = (
            f"Finding plans for:\n"
            f"- Allergies: {', '.join(next_state.get('allergies', ['None'])) if next_state.get('allergies') else 'None'}\n"
            f"- Weight Range: {next_state.get('weight_range', 'General')}\n"
            f"- Health Condition: {next_state.get('health_condition', 'General Wellness').replace('_',' ').title()}"
        )
        # The summary is not directly sent back as reply_text to avoid overwriting "Finding plans..."
        # Instead, it's constructed and can be used by the frontend if needed.
        # The main reply will be the recommendation_html.
        next_state = {} 
        return jsonify({
            'reply': "Here are some suggestions based on your input:\n" + current_state_summary, # Added summary to initial reply
            'recommendation_html': recommendation_response.get('plan_html', "<p>Could not fetch recommendations at this time.</p>"),
            'options': [
                 {"label": "Start Over", "payload": {"type": "action", "value": "start_over"}}
            ],
            'state': next_state
        })
    elif action_type == "action" and action_value == "start_over":
        next_state = {} 
        reply_text = "Okay, let's start over. How can I help you today?"
        reply_options = [
            {"label": "Suggest a Diet Plan", "payload": {"type": "action", "value": "suggest_plan_start"}},
            {"label": "Explain BMR", "payload": {"type": "action", "value": "explain_bmr"}},
            {"label": "Ask a General Question", "payload": {"type": "action", "value": "ask_general_question_prompt"}}
        ]
    elif next_state.get('awaiting') == 'general_question_text' and action_type == "text_input":
        user_question = payload.get("text", "")
        if "protein" in user_question: reply_text = "Protein is essential for building and repairing tissues, making enzymes and hormones. Good sources include meat, fish, eggs, dairy, beans, lentils, and tofu."
        elif "fiber" in user_question: reply_text = "Fiber aids digestion, helps regulate blood sugar, and can lower cholesterol. Find it in fruits, vegetables, whole grains, nuts, and seeds."
        elif "carbohydrates" in user_question or "carbs" in user_question: reply_text = "Carbohydrates are your body's main source of energy. Choose complex carbs like whole grains, fruits, and vegetables over simple carbs like sugary drinks and processed snacks."
        else: reply_text = "That's an interesting question! For detailed nutritional advice specific to your needs, it's always best to consult a registered dietitian or your doctor. I can help with BMR, food lookups via the 'Food Search' tab, or suggest existing diet plans."
        next_state = {} 
        reply_options = [
            {"label": "Suggest a Diet Plan", "payload": {"type": "action", "value": "suggest_plan_start"}},
            {"label": "Explain BMR", "payload": {"type": "action", "value": "explain_bmr"}},
            {"label": "Ask Another Question", "payload": {"type": "action", "value": "ask_general_question_prompt"}},
            {"label": "Main Menu", "payload": {"type": "action", "value": "start_over"}}
        ]
    elif not reply_text and not reply_options: 
        reply_text = "I'm not sure how to respond to that. You can ask me to 'Suggest a Diet Plan', 'Explain BMR', or ask a general nutrition question. Or type 'menu' to see options."
        reply_options = [
            {"label": "Suggest a Diet Plan", "payload": {"type": "action", "value": "suggest_plan_start"}},
            {"label": "Explain BMR", "payload": {"type": "action", "value": "explain_bmr"}},
        ]
    return jsonify({'reply': reply_text, 'options': reply_options, 'state': next_state})

def _get_diet_plan_recommendations(data):
    allergies_input = data.get('allergies', []) 
    health_condition_input = data.get('health_condition', 'none') 
    weight_range_input = data.get('weight_range', 'none') 
    recommendations_html = "" 
    conn = None; cursor = None
    try:
        conn = get_db_connection()
        if not conn: raise Exception("DB connection failed")
        cursor = conn.cursor(dictionary=True)
        sql_clauses = ["dp.is_public = 1"]
        sql_params = []
        if health_condition_input and health_condition_input != 'none':
            sql_clauses.append("LOWER(dp.target_conditions) LIKE %s")
            sql_params.append(f"%{health_condition_input.lower()}%")
        min_calories, max_calories = None, None
        if weight_range_input == '40-55': min_calories, max_calories = 1200, 1800
        elif weight_range_input == '56-76': min_calories, max_calories = 1600, 2200
        elif weight_range_input == '77-90': min_calories, max_calories = 2000, 2800
        elif weight_range_input == '90+': min_calories = 2500 
        if min_calories is not None:
            sql_clauses.append("dp.calories >= %s")
            sql_params.append(min_calories)
        if max_calories is not None:
            sql_clauses.append("dp.calories <= %s")
            sql_params.append(max_calories)
        if allergies_input:
            for allergy in allergies_input:
                sql_clauses.append("NOT (LOWER(dp.plan_name) LIKE %s OR LOWER(dp.description) LIKE %s)")
                sql_params.extend([f"%{allergy.lower()}%", f"%{allergy.lower()}%"])
        where_clause = " AND ".join(sql_clauses)
        target_calorie_midpoint = 1800 
        if min_calories and max_calories: target_calorie_midpoint = (min_calories + max_calories) // 2
        elif min_calories: target_calorie_midpoint = min_calories + 300 
        
        query = f"""
            SELECT dp.plan_id, dp.plan_name, dp.description, dp.calories, dp.plan_type
            FROM diet_plans dp
            WHERE {where_clause}
            ORDER BY FIELD(dp.plan_type, 'medical', 'custom', 'weight_loss', 'weight_gain', 'maintenance', 'standard'), 
                     ABS(dp.calories - %s), 
                     dp.plan_name 
            LIMIT 3 
        """ 
        final_params = sql_params + [target_calorie_midpoint]
        cursor.execute(query, tuple(final_params))
        recommended_plans_db = cursor.fetchall()
        if recommended_plans_db:
            recommendations_html += "<ul class='bot-recommendation-list'>" # Changed class for styling
            for plan_item in recommended_plans_db:
                plan_url = url_for('nutrition_bp.plan_details', plan_id=plan_item['plan_id'], _external=True)
                recommendations_html += (
                    f"<li class='bot-recommendation-item'><strong><a href='{plan_url}' target='_blank' class='bot-link'>{plan_item['plan_name']}</a></strong>"
                    f" <span class='bot-recommendation-meta'>(Type: {plan_item['plan_type'].replace('_', ' ').title()}, ~{plan_item['calories'] or 'N/A'} cals)</span><br>"
                    f"<small class='bot-recommendation-desc'>{plan_item['description'][:100] if plan_item['description'] else ''}...</small></li>"
                )
            recommendations_html += "</ul><p class='bot-recommendation-footer'><em>Click plan name for details. Always verify ingredients.</em></p>"
        else:
            recommendations_html += "<p>Sorry, I couldn't find specific diet plans matching all your criteria. You might want to explore our <a href='" + url_for('nutrition_bp.list_diet_plans', _external=True) + "' target='_blank' class='bot-link'>full list of diet plans</a> or consult with a nutritionist.</p>"
    except Exception as e:
        logger.error(f"Error generating diet plan recommendations: {e}", exc_info=True)
        recommendations_html = "<p class='bot-message error-message'>An error occurred while finding recommendations.</p>" 
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
    return {'plan_html': recommendations_html}

@nutrition_bp.route('/api/bot/recommend_diet_plans', methods=['POST'])
def api_recommend_diet_plans_endpoint():
    data = request.get_json()
    result = _get_diet_plan_recommendations(data)
    return jsonify(result)

@nutrition_bp.route('/bmr-calculator')
def bmr_calculator_page():
    return render_template('bmr_calculator.html')