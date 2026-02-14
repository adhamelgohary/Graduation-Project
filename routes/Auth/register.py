import logging
import re
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash

from db import get_db
from fastapi_limiter.depends import RateLimiter
from models import (
    Users,
    Patients,
    Departments,
    Specializations,
    PendingRegistrations,
    InsuranceProviders,
)
from utils.template_helpers import templates, flash

from pyrate_limiter import Duration, Limiter, Rate
from fastapi_limiter.depends import RateLimiter

router = APIRouter()
logger = logging.getLogger(__name__)

EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email):
    return re.match(EMAIL_REGEX, email) is not None


# --- Helper Functions (Async) ---


async def get_departments(db: AsyncSession):
    try:
        result = await db.execute(select(Departments).order_by(Departments.name.asc()))
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching departments: {e}")
        return []


async def get_specializations(db: AsyncSession, department_id: int = None):
    try:
        stmt = select(Specializations).order_by(Specializations.name.asc())
        if department_id:
            stmt = stmt.where(Specializations.department_id == department_id)
        result = await db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching specializations: {e}")
        return []


# --- Routes ---


@router.get("/get_specializations_for_department/{department_id}")
async def get_specializations_for_department_route(
    department_id: int, db: AsyncSession = Depends(get_db)
):
    specs = await get_specializations(db, department_id)
    return [{"specialization_id": s.specialization_id, "name": s.name} for s in specs]


@router.get("/register", dependencies=[Depends(RateLimiter(limiter=Limiter))])
@router.post("/register", dependencies=[Depends(RateLimiter(limiter=Limiter))])
async def register_route(request: Request, db: AsyncSession = Depends(get_db)):
    # Fetch common data for template rendering
    all_departments = await get_departments(db)
    specializations_for_selected_dept = []

    if request.method == "GET":
        if not all_departments:
            flash(
                request,
                "Could not load departments list. Please try again later.",
                "warning",
            )
        return templates.TemplateResponse(
            "Auth/Register.html",
            {
                "request": request,
                "departments": all_departments,
                "specializations_for_selected_dept": [],
                "form_data": {},
            },
        )

    # --- POST Handling ---
    form_data = await request.form()

    # Pre-fetch specializations if department_id is in form_data for re-rendering on error
    form_dept_id_str = form_data.get("department_id")
    if form_dept_id_str:
        try:
            dept_id = int(form_dept_id_str)
            specializations_for_selected_dept = await get_specializations(db, dept_id)
            # Convert to dicts for template consistency if needed, but objects usually work in Jinja
            # Jinja can handle objects.
        except ValueError:
            pass

    # Extract Data
    username = form_data.get("username", "").strip()
    email = form_data.get("email", "").strip().lower()
    password = form_data.get("password", "")
    confirm_password = form_data.get("confirm_password", "")
    first_name = form_data.get("first_name", "").strip()
    last_name = form_data.get("last_name", "").strip()
    user_type = form_data.get("user_type")
    phone = form_data.get("phone", "").strip() or None
    country = form_data.get("country", "United States").strip()

    # Patient Data
    date_of_birth = form_data.get("date_of_birth")
    gender = form_data.get("gender") or "unknown"
    insurance_provider_name = form_data.get("insurance_provider", "").strip() or None
    insurance_policy_number = (
        form_data.get("insurance_policy_number", "").strip() or None
    )
    insurance_group_number = form_data.get("insurance_group_number", "").strip() or None

    # Doctor Data
    specialization_id_str = form_data.get("specialization_id")
    license_number = form_data.get("license_number", "").strip() or None
    license_state = form_data.get("license_state", "").strip() or None
    license_expiration = form_data.get("license_expiration")

    errors = []

    # Validation
    if not all([username, email, first_name, last_name, user_type]):
        errors.append("Please fill in all required common fields (*).")
    if not is_valid_email(email):
        errors.append("Please enter a valid email address.")

    if user_type:
        if not password or not confirm_password:
            errors.append(f"Password and confirmation are required for {user_type}s.")
        elif password != confirm_password:
            errors.append("Passwords do not match.")
        elif len(password) < 8:
            errors.append("Password must be at least 8 characters.")

    department_id_int = None
    specialization_id_int = None
    dob_obj = None
    license_exp_obj = None

    if user_type == "patient":
        if not date_of_birth:
            errors.append("Date of Birth is required for patients.")
        else:
            try:
                dob_obj = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
                if dob_obj >= date.today():
                    errors.append("Date of Birth must be in the past.")
            except ValueError:
                errors.append("Invalid Date of Birth format (YYYY-MM-DD).")
        if not gender or gender == "unknown":
            errors.append("Gender is required for patients.")

    elif user_type == "doctor":
        if not form_dept_id_str:
            errors.append("Department is required for professionals.")
        else:
            try:
                department_id_int = int(form_dept_id_str)
                # Validate existence
                if not any(
                    d.department_id == department_id_int for d in all_departments
                ):
                    errors.append("Invalid department selected.")
            except ValueError:
                errors.append("Invalid department ID format.")

        if not specialization_id_str:
            errors.append("Specialization is required for professionals.")
        elif department_id_int:
            try:
                specialization_id_int = int(specialization_id_str)
                # Validate logic
                if not any(
                    s.specialization_id == specialization_id_int
                    for s in specializations_for_selected_dept
                ):
                    errors.append(
                        "Invalid specialization selected for the chosen department."
                    )
            except ValueError:
                errors.append("Invalid specialization ID format.")

        if not license_number:
            errors.append("License Number is required.")
        if not license_state:
            errors.append("License State is required.")
        if not license_expiration:
            errors.append("License Expiration Date is required.")
        else:
            try:
                license_exp_obj = datetime.strptime(
                    license_expiration, "%Y-%m-%d"
                ).date()
                if license_exp_obj < date.today():
                    errors.append("License Expiration Date cannot be in the past.")
            except ValueError:
                errors.append("Invalid License Expiration Date format.")

    elif not user_type:
        errors.append("Please select an account type.")
    else:
        errors.append("Invalid user type selected.")

    if errors:
        for error in errors:
            flash(request, error, "danger")
        return templates.TemplateResponse(
            "Register.html",
            {
                "request": request,
                "form_data": form_data,
                "departments": all_departments,
                "specializations_for_selected_dept": specializations_for_selected_dept,
            },
        )

    # DB Operations
    try:
        # Check Existing Users
        stmt = select(Users).where(
            (Users.email == email) | (Users.username == username)
        )
        result = await db.execute(stmt)
        existing_user = result.scalars().first()

        # Check Pending
        stmt_pending = select(PendingRegistrations).where(
            (
                (PendingRegistrations.email == email)
                | (PendingRegistrations.username == username)
            )
            & (PendingRegistrations.status != "rejected")
        )
        result_pending = await db.execute(stmt_pending)
        pending_user = result_pending.scalars().first()

        if existing_user or pending_user:
            msg = "An account with this Email or Username already exists."
            if pending_user:
                msg += " Your previous registration is pending approval."
            flash(request, msg, "warning")
            return templates.TemplateResponse(
                "Register.html",
                {
                    "request": request,
                    "form_data": form_data,
                    "departments": all_departments,
                    "specializations_for_selected_dept": specializations_for_selected_dept,
                },
            )

        if user_type == "doctor":
            hashed_pw = generate_password_hash(password)
            new_pending = PendingRegistrations(
                email=email,
                first_name=first_name,
                last_name=last_name,
                username=username,
                password=hashed_pw,
                phone=phone,
                country=country,
                user_type_requested="doctor",
                department_id=department_id_int,
                specialization_id=specialization_id_int,
                license_number=license_number,
                license_state=license_state,
                license_expiration=license_exp_obj,
                date_submitted=datetime.now(),
                status="pending",
            )
            db.add(new_pending)
            await db.commit()
            flash(
                request,
                "Doctor registration submitted for approval. You will be notified once reviewed.",
                "info",
            )
            return RedirectResponse(request.url_for("login_route"), status_code=303)

        elif user_type == "patient":
            hashed_pw = generate_password_hash(password)
            new_user = Users(
                username=username,
                email=email,
                password=hashed_pw,
                first_name=first_name,
                last_name=last_name,
                user_type="patient",
                phone=phone,
                country=country,
                account_status="active",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.add(new_user)
            await db.flush()  # Get user_id

            # Handle Patient Profile
            # Lookup Insurance Provider ID if name provided
            ins_prov_id = None
            if insurance_provider_name:
                stmt_ins = select(InsuranceProviders).where(
                    InsuranceProviders.provider_name == insurance_provider_name
                )
                res = await db.execute(stmt_ins)
                prov = res.scalars().first()
                if prov:
                    ins_prov_id = prov.id

            # Create or Update Patient Record
            # We try to fetch existing first (in case trigger created it)
            stmt_pat = select(Patients).where(Patients.user_id == new_user.user_id)
            res_pat = await db.execute(stmt_pat)
            patient = res_pat.scalars().first()

            if not patient:
                patient = Patients(user_id=new_user.user_id)
                db.add(patient)

            patient.date_of_birth = dob_obj
            patient.gender = gender
            patient.insurance_provider_id = ins_prov_id
            patient.insurance_policy_number = insurance_policy_number
            patient.insurance_group_number = insurance_group_number
            # Assuming occupation and marital_status not in form? Or maybe I missed them.
            # Original code had them in UPDATE query but I didn't see fields in form extraction above?
            # Ah, extracting them now just in case they are there.
            patient.marital_status = form_data.get("marital_status")
            patient.occupation = form_data.get("occupation")

            await db.commit()
            flash(request, "Registration successful! You can now log in.", "success")
            return RedirectResponse(request.url_for("login_route"), status_code=303)

    except Exception as e:
        await db.rollback()
        logger.error(f"Registration error: {e}", exc_info=True)
        flash(request, f"An error occurred: {str(e)}", "danger")
        return templates.TemplateResponse(
            "Auth/Register.html",
            {
                "request": request,
                "form_data": form_data,
                "departments": all_departments,
                "specializations_for_selected_dept": specializations_for_selected_dept,
            },
        )
