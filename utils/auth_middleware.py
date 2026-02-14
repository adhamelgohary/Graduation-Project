import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from db import async_session_factory
from models import Users
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)


class AnonymousUser:
    is_authenticated = False
    is_active = False
    user_type = None
    username = "Guest"
    email = None
    user_id = None

    def is_doctor(self):
        return False

    def is_admin(self):
        return False

    def is_patient(self):
        return False

    def is_fully_verified_doctor(self):
        return False

    @property
    def doctor_profile(self):
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Default to AnonymousUser
        request.state.user = AnonymousUser()

        # SessionMiddleware must be installed and run before this
        if not hasattr(request, "session"):
            logger.warning(
                "AuthMiddleware: No session attribute found on request. Ensure SessionMiddleware is added after AuthMiddleware (outer)."
            )
            return await call_next(request)

        user_id = request.session.get("user_id")

        if user_id:
            try:
                async with async_session_factory() as session:
                    # Eager load profiles to avoid lazy load errors in templates/sync checking
                    query = (
                        select(Users)
                        .options(
                            joinedload(Users.doctor_profile),
                            joinedload(Users.patient_profile),
                            joinedload(Users.admin_profile),
                        )
                        .where(Users.user_id == user_id)
                    )

                    result = await session.execute(query)
                    user = result.unique().scalar_one_or_none()

                    if user:
                        # You might want to check account_status here
                        if user.account_status == "active":
                            request.state.user = user
            except Exception as e:
                logger.error(f"AuthMiddleware error loading user {user_id}: {e}")

        response = await call_next(request)
        return response
