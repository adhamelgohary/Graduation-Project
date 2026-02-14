from fastapi import APIRouter

# Import all sub-routers
from .Website import website_router

# from .Admin_Portal import admin_router
# from .Doctor_Portal import doctor_router
# from .Patient_Portal import patient_router
# from .api import api_router
from .Auth import auth_router

# The master router
master_router = APIRouter()

master_router.include_router(website_router)
# master_router.include_router(admin_router)
# master_router.include_router(doctor_router)
# master_router.include_router(patient_router)
# master_router.include_router(api_router)
master_router.include_router(auth_router)
