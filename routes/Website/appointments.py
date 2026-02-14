from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import RedirectResponse

# removed local Jinja2Templates import
from services.appointment_service import AppointmentService
from services.doctor_service import DoctorService
from utils.dependencies import get_current_user
from datetime import date

appointments_router = APIRouter()
from utils.template_helpers import templates


@appointments_router.get("/schedule/with/<int:doctor_id>")
async def schedule_with_doc(
    request: Request,
    doctor_id: int,
    current_user=Depends(get_current_user),
    # Capture query params for pre-filling on error
    location_id: int = None,
    error: str = None,
):
    doctor = AppointmentService.get_doctor_scheduling_details(doctor_id)
    if not doctor:
        return RedirectResponse("/doctors?error=DoctorNotFound")

    setup = AppointmentService.get_scheduling_setup(doctor_id)
    types = AppointmentService.get_appointment_types()

    return templates.TemplateResponse(
        "Website/Appointments/appointment_form.html",
        {
            "request": request,
            "doctor": doctor,
            "scheduling_info": setup,
            "appointment_types": types,
            "today_date_iso": date.today().isoformat(),
            "error_message": error,  # Display this in your template
            "prefill": {"location_id": location_id},
        },
    )


@appointments_router.get("/availability/{doctor_id}/{date_str}")
async def get_availability_ajax(doctor_id: int, date_str: str, location_id: int):
    # This is called by JavaScript
    return AppointmentService.get_available_slots(doctor_id, date_str, location_id)


@appointments_router.post("/schedule/confirm/{doctor_id}")
async def confirm_appointment(
    request: Request,
    doctor_id: int,
    location_id: int = Form(...),
    appointment_date: str = Form(...),
    appointment_time: str = Form(...),
    appointment_type_id: int = Form(...),
    reason: str = Form(...),
    current_user=Depends(get_current_user),
):
    # 1. Re-check availability (Security best practice)
    check = AppointmentService.get_available_slots(
        doctor_id, appointment_date, location_id
    )
    if appointment_time not in check.get("slots", []):
        url = request.url_for("schedule_with_doc", doctor_id=doctor_id)
        return RedirectResponse(
            f"{url}?error=Slot+taken+or+invalid&location_id={location_id}",
            status_code=303,
        )

    # 2. Get Duration
    types = AppointmentService.get_appointment_types()
    duration = next(
        (
            t["default_duration_minutes"]
            for t in types
            if t["type_id"] == appointment_type_id
        ),
        30,
    )

    # 3. Create
    data = {
        "doctor_id": doctor_id,
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "appointment_type_id": appointment_type_id,
        "reason": reason,
        "location_id": location_id,
        "duration_minutes": duration,
    }

    new_id = AppointmentService.create_appointment(data, current_user.id)

    # 4. Redirect to details
    return RedirectResponse(
        request.url_for("view_appointment_detail", appointment_id=new_id),
        status_code=303,
    )


@appointments_router.get("/{appointment_id}")
async def view_appointment_detail(
    request: Request, appointment_id: int, current_user=Depends(get_current_user)
):
    appt = AppointmentService.get_appointment_details(
        appointment_id, current_user.id, "patient"
    )  # Assuming patient
    if not appt:
        return RedirectResponse("/appointments/my-appointments?error=NotFound")

    return templates.TemplateResponse(
        "Website/Appointments/appointment_detail.html",
        {"request": request, "appointment": appt},
    )


@appointments_router.get("/my-appointments")
async def view_my_appointments(
    request: Request, current_user=Depends(get_current_user)
):
    appts = AppointmentService.get_user_appointments(current_user.id, "patient")

    # Filter python-side (or move to SQL)
    upcoming = [a for a in appts if a["category"] == "upcoming"]
    past = [a for a in appts if a["category"] == "past"]

    return templates.TemplateResponse(
        "Website/Appointments/my_appointments.html",
        {
            "request": request,
            "upcoming_appointments": upcoming,
            "past_appointments": past,
        },
    )
