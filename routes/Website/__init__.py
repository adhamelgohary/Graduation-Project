from fastapi import APIRouter
from .home import home_router
from .department import department_router
from .doctor import doctor_router
from .appointments import appointments_router
from .disease_info import disease_info_router
from .vaccines import vaccines_router
from .nutrition import nutrition_router

website_router = APIRouter()

website_router.include_router(home_router)
website_router.include_router(department_router, prefix="/department")
website_router.include_router(doctor_router, prefix="/doctor")
website_router.include_router(appointments_router, prefix="/appointments")
website_router.include_router(disease_info_router, prefix="/disease-info")
website_router.include_router(vaccines_router, prefix="/vaccines")
website_router.include_router(nutrition_router, prefix="/nutrition")
