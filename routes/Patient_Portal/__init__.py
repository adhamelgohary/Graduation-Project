from fastapi import APIRouter
from .profile import patient_profile_router
from .medical_info import patient_medical_info_router
from .patient_messaging import patient_messaging_router

patient_router = APIRouter(prefix="/patient")

patient_router.include_router(patient_profile_router, prefix="/profile")
patient_router.include_router(patient_medical_info_router, prefix="/medical-info")
patient_router.include_router(patient_messaging_router, prefix="/messaging")
