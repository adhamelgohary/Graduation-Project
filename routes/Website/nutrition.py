# Health_Guide/routes/Website/nutrition.py
from fastapi import APIRouter, Request, Body, Query, HTTPException

# removed local Jinja2Templates import
from fastapi.responses import JSONResponse
from services.nutrition_service import NutritionService

nutrition_router = APIRouter()
from utils.template_helpers import templates


# nuitrition lanfing page
@nutrition_router.get("/")
async def nutrition_landing(request: Request):
    specialists = NutritionService.get_specialists()
    return templates.TemplateResponse(
        "Website/Nutrition/nutrition_landing.html",
        {
            "request": request,
            "specialists": specialists,
        },
    )


# list diet plans
@nutrition_router.get("/list-diet-plans")
async def list_diet_plans(request: Request):
    plans = NutritionService.get_diet_plans()
    specialists = NutritionService.get_specialists()
    return templates.TemplateResponse(
        "Website/Nutrition/list_diet_plans.html",
        {
            "request": request,
            "plans": plans,
            "specialists": specialists,
        },
    )


# plan details
@nutrition_router.get("/plan-details/{plan_id}")
async def plan_details(request: Request, plan_id: int):
    plan = NutritionService.get_plan_details(plan_id)
    if not data:
        raise HTTPException(status_code=404, detail="Plan not found")

    specialists = NutritionService.get_specialists()
    return templates.TemplateResponse(
        "Website/Nutrition/plan_details.html",
        {
            "request": request,
            "plan": plan,
            "meals": plan["meals"],
            "specialists": specialists,
        },
    )


@nutrition_router.get("/food-search")
async def food_search_page(request: Request):
    return templates.TemplateResponse(
        "Website/Nutrition/food_search.html", {"request": request}
    )


@nutrition_router.get("/bmr-calculator")
async def bmr_calculator_page(request: Request):
    return templates.TemplateResponse(
        "Website/Nutrition/bmr_calculator.html", {"request": request}
    )


# --- API Routes (AJAX / React) ---


@nutrition_router.get("/api/food-library/search")
async def search_food_library():
    results = NutritionService.search_food_library(q)
    return JSONResponse(content=results)


@nutrition_router.post("/api/bot/chat")
async def api_bot_chat(data: dict = Body(...)):
    """
    The ChatBot State Machine.
    Kept in Router because it's mostly presentation/interaction logic, not business logic.
    """
    payload = data.get("payload", {})
    state = data.get("state", {})
    action_type = payload.get("type")
    action_value = payload.get("value")

    reply_text = ""
    reply_options = []
    next_state = state.copy()

    # --- Interaction Logic ---
    if action_type == "text_input" and action_value.lower() in [
        "hi",
        "hello",
        "menu",
        "start over",
    ]:
        next_state = {}
        reply_text = "Hello! I'm your Nutrition Bot. How can I assist you today?"
        reply_options = [
            {
                "label": "Suggest a Diet Plan",
                "payload": {"type": "action", "value": "suggest_plan_start"},
            },
            {
                "label": "Explain BMR",
                "payload": {"type": "action", "value": "explain_bmr"},
            },
            {
                "label": "Ask a General Question",
                "payload": {"type": "action", "value": "ask_general_question_prompt"},
            },
        ]

    elif action_type == "action" and action_value == "explain_bmr":
        reply_text = (
            "BMR is your Basal Metabolic Rate - calories burned at rest.\n"
            "Men: (10 × weight kg) + (6.25 × height cm) - (5 × age) + 5\n"
            "Women: (10 × weight kg) + (6.25 × height cm) - (5 × age) - 161"
        )
        reply_options = [
            {
                "label": "Suggest a Diet Plan",
                "payload": {"type": "action", "value": "suggest_plan_start"},
            },
            {
                "label": "Back to Main Menu",
                "payload": {"type": "action", "value": "start_over"},
            },
        ]

    elif action_type == "action" and action_value == "suggest_plan_start":
        next_state = {"current_flow": "diet_plan", "step": "allergies", "allergies": []}
        reply_text = "Do you have any common allergies? (Select all that apply)"
        allergies = [
            "Dairy",
            "Nuts",
            "Peanuts",
            "Shellfish",
            "Fish",
            "Eggs",
            "Wheat/Gluten",
            "Soy",
        ]
        reply_options = [
            {"label": a, "payload": {"type": "select_allergy", "value": a.lower()}}
            for a in allergies
        ]
        reply_options.append(
            {
                "label": "Done with Allergies",
                "payload": {"type": "action", "value": "collect_allergies_done"},
            }
        )

    elif payload.get("type") == "select_allergy":
        selected = payload.get("value")
        current_list = next_state.get("allergies", [])

        if selected in current_list:
            current_list.remove(selected)
        else:
            current_list.append(selected)

        next_state["allergies"] = current_list
        reply_text = f"Allergies selected: {', '.join(current_list) if current_list else 'None'}."

        # Re-render options
        allergies = [
            "Dairy",
            "Nuts",
            "Peanuts",
            "Shellfish",
            "Fish",
            "Eggs",
            "Wheat/Gluten",
            "Soy",
        ]
        reply_options = []
        for a in allergies:
            prefix = "✅ " if a.lower() in current_list else ""
            reply_options.append(
                {
                    "label": prefix + a,
                    "payload": {"type": "select_allergy", "value": a.lower()},
                }
            )
        reply_options.append(
            {
                "label": "Done with Allergies",
                "payload": {"type": "action", "value": "collect_allergies_done"},
            }
        )

    elif action_type == "action" and action_value == "collect_allergies_done":
        next_state["step"] = "weight_range"
        reply_text = "What is your approximate weight range?"
        reply_options = [
            {
                "label": "40-55 kg",
                "payload": {"type": "select_weight", "value": "40-55"},
            },
            {
                "label": "56-76 kg",
                "payload": {"type": "select_weight", "value": "56-76"},
            },
            {
                "label": "77-90 kg",
                "payload": {"type": "select_weight", "value": "77-90"},
            },
            {"label": "90+ kg", "payload": {"type": "select_weight", "value": "90+"}},
        ]

    elif payload.get("type") == "select_weight":
        next_state["weight_range"] = payload.get("value")
        next_state["step"] = "health_condition"
        reply_text = "Any specific health conditions?"
        reply_options = [
            {
                "label": "None / General",
                "payload": {"type": "select_health", "value": "none"},
            },
            {
                "label": "Diabetes",
                "payload": {"type": "select_health", "value": "diabetes"},
            },
            {
                "label": "Hypertension",
                "payload": {"type": "select_health", "value": "hypertension"},
            },
        ]

    elif payload.get("type") == "select_health":
        # FINAL STEP: GET RECOMMENDATIONS
        next_state["health_condition"] = payload.get("value")

        # Call Service to get plans
        plans = NutritionService.get_recommendations(
            {
                "allergies": next_state.get("allergies"),
                "weight_range": next_state.get("weight_range"),
                "health_condition": next_state.get("health_condition"),
            }
        )

        # Build HTML snippet for the bot (similar to legacy)
        if plans:
            html = "<ul class='bot-recommendation-list'>"
            for p in plans:
                # Note: We return a relative URL here, assumes frontend handles base or it's same domain
                html += f"<li><strong>{p['plan_name']}</strong> ({p['calories']} cal)<br>{p['description'][:80]}...</li>"
            html += "</ul>"
        else:
            html = "<p>No specific plans found. Please consult a specialist.</p>"

        return JSONResponse(
            {
                "reply": "Here are some suggestions based on your profile:",
                "recommendation_html": html,
                "options": [
                    {
                        "label": "Start Over",
                        "payload": {"type": "action", "value": "start_over"},
                    }
                ],
                "state": {},  # Reset state
            }
        )

    elif action_type == "action" and action_value == "start_over":
        # Recursively call start logic or just return manually
        reply_text = "Let's start over. How can I help?"
        next_state = {}
        reply_options = [
            {
                "label": "Suggest a Diet Plan",
                "payload": {"type": "action", "value": "suggest_plan_start"},
            },
        ]

    # Default fallback
    if not reply_text:
        reply_text = "I didn't understand that. Type 'menu' to restart."

    return JSONResponse(
        {"reply": reply_text, "options": reply_options, "state": next_state}
    )
