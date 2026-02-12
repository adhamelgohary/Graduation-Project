from fastapi import APIRouter
from .Dashboard import admin_main_router
from .Admins_Management import admin_management_router
from .Doctors_Management import doctors_management_router
from .Patient_Management import patient_management_router
from .Registiration_Approval_System import registration_approval_router
from .search_users import search_users_router
from .Appointments import admin_appointments_router
from .structure_management import structure_router

admin_router = APIRouter(prefix="/admin")

admin_router.include_router(admin_main_router)
admin_router.include_router(admin_management_router, prefix="/management")
admin_router.include_router(doctors_management_router, prefix="/doctors")
admin_router.include_router(patient_management_router, prefix="/patients")
admin_router.include_router(registration_approval_router, prefix="/approvals")
admin_router.include_router(search_users_router, prefix="/search")
admin_router.include_router(admin_appointments_router, prefix="/appointments")
admin_router.include_router(structure_router, prefix="/structure")
