from fastapi import APIRouter
from .login import router as login_router
from .register import router as register_router

# from .password_reset import password_reset_router

auth_router = APIRouter(prefix="/auth")

auth_router.include_router(login_router)
auth_router.include_router(register_router)
# auth_router.include_router(password_reset_router)
