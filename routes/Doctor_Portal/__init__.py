from fastapi import APIRouter
from .Dashboard import doctor_main_router
from .availability_management import availability_router
from .settings_management import settings_router
from .patients_management import patients_router
from .disease_management import disease_management_router
from .diet_plan_management import diet_plans_router
from .appointment_management import appointments_router
from .messaging import messaging_router
from .location_management import locations_router
from .food_item_management import food_items_router
from .vaccine_management import vaccine_management_router

doctor_router = APIRouter(prefix="/doctor")

doctor_router.include_router(doctor_main_router)
doctor_router.include_router(availability_router, prefix="/availability")
doctor_router.include_router(settings_router, prefix="/settings")
doctor_router.include_router(patients_router, prefix="/patients")
doctor_router.include_router(disease_management_router, prefix="/disease")
doctor_router.include_router(diet_plans_router, prefix="/diet-plans")
doctor_router.include_router(appointments_router, prefix="/appointments")
doctor_router.include_router(messaging_router, prefix="/messaging")
doctor_router.include_router(locations_router, prefix="/locations")
doctor_router.include_router(food_items_router, prefix="/food-items")
doctor_router.include_router(vaccine_management_router, prefix="/vaccines")
