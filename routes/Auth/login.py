import logging
import os
from urllib.parse import urlparse, urljoin
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash

from db import get_db
from models import Users, Doctors, Patients, Admins
from utils.template_helpers import templates, flash
from pyrate_limiter import Duration, Limiter, Rate
from fastapi_limiter.depends import RateLimiter

router = APIRouter()

logger = logging.getLogger(__name__)

limiter = Limiter(Rate(5, Duration.MINUTE))

@router.get("/login", dependencies=[Depends(RateLimiter(limiter=limiter))])
@router.post("/login", dependencies=[Depends(RateLimiter(limiter=limiter))])
async def login_route(
    request: Request,
    identifier: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    remember: Optional[bool] = Form(False),  # We use session cookies, usually implicit
    db: AsyncSession = Depends(get_db),
):
    # Check if already authenticated
    current_user = getattr(request.state, "user", None)
    if current_user and current_user.is_authenticated:
        if current_user.is_admin:
            return RedirectResponse("/admin/dashboard", status_code=303)
        elif current_user.is_doctor:
            return RedirectResponse("/doctor/dashboard", status_code=303)
        elif current_user.is_patient:
            return RedirectResponse("/patient/profile/", status_code=303)
        else:
            return RedirectResponse(request.url_for("home"), status_code=303)

    if request.method == "GET":
        return templates.TemplateResponse("Auth/Login.html", {"request": request})

    # --- POST Logic ---
    if not identifier or not password:
        flash(
            request,
            "Please enter both identifier (email/username) and password.",
            "warning",
        )
        return templates.TemplateResponse("Login.html", {"request": request})

    try:
        # Query User
        # Using select with options if needed, but for password check basic info is enough
        # We might need profiles for redirection logic if we want to check verification status immediately
        stmt = (
            select(Users)
            .options(
                joinedload(Users.doctor_profile),
                joinedload(Users.patient_profile),
                joinedload(Users.admin_profile),
            )
            .where((Users.email == identifier) | (Users.username == identifier))
        )

        result = await db.execute(stmt)
        user = result.unique().scalar_one_or_none()

        if user and check_password_hash(user.password, password):
            if user.account_status == "active":
                # Success!
                request.session["user_id"] = user.user_id
                logger.info(
                    f"User {user.user_id} ({user.username}) logged in successfully."
                )

                # Redirect Logic
                if user.is_admin:
                    flash(request, "Admin login successful!", "success")
                    return RedirectResponse("/admin/dashboard", status_code=303)

                elif user.is_doctor:
                    # Check verification status
                    doc_profile = user.doctor_profile
                    status = (
                        doc_profile.verification_status if doc_profile else "pending"
                    )

                    if status == "approved":
                        flash(request, "Doctor login successful!", "success")
                    elif status == "pending_info":
                        flash(
                            request,
                            "Login successful. Please complete verification.",
                            "info",
                        )
                    else:
                        flash(
                            request,
                            f"Login successful. Account status: {status}.",
                            "info",
                        )

                    return RedirectResponse("/doctor/dashboard", status_code=303)

                elif user.is_patient:
                    flash(request, "Login successful!", "success")
                    return RedirectResponse("/patient/profile/", status_code=303)

                else:
                    flash(request, "Login successful!", "success")
                    return RedirectResponse(request.url_for("home"), status_code=303)

            # Handle non-active statuses
            elif user.account_status == "pending":
                flash(request, "Your account is pending approval.", "warning")
            elif user.account_status == "suspended":
                flash(request, "Your account has been suspended.", "danger")
            elif user.account_status == "inactive":
                flash(request, "Your account is inactive.", "warning")
            else:
                flash(
                    request, f"Login denied. Status: {user.account_status}", "warning"
                )

        else:
            flash(request, "Invalid credentials.", "danger")
            logger.warning(f"Failed login attempt for {identifier}")

    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        flash(request, "An unexpected error occurred. Please try again.", "danger")

    # If failed
    return templates.TemplateResponse("Auth/Login.html", {"request": request})


@router.get("/logout")
async def logout_route(request: Request):
    if "user_id" in request.session:
        request.session.pop("user_id")
        flash(request, "You have been successfully logged out.", "info")
    return RedirectResponse(request.url_for("home"), status_code=303)
