from fastapi import APIRouter, Request, Query

# removed local Jinja2Templates import
from services.doctor_service import DoctorService

doctor_router = APIRouter()
from utils.template_helpers import templates


@doctor_router.get("/")
@doctor_router.get("/list")
async def list_doctors(
    request: Request,
    search_name: str = Query("", alias="search_name"),
    department_id: int = Query(None, alias="department_id"),
    specialization_id: int = Query(None, alias="specialization_id"),
):
    doctors = DoctorService.get_filtered_doctors(
        search_name=search_name,
        department_id=department_id,
        specialization_id=specialization_id,
    )

    # Fetch filter options
    departments = DoctorService.get_all_departments()
    specs = DoctorService.get_specializations(department_id) if department_id else []

    return templates.TemplateResponse(
        "Website/Doctor/doctor_list.html",
        {
            "request": request,
            "doctors": doctors,
            "departments": departments,
            "specializations_dropdown_data": specs,
            "selected_name": search_name,
            "selected_dept_id": department_id,
            "selected_spec_id": specialization_id,
        },
    )


@doctor_router.get("/profile/{doctor_id}")
async def view_doctor_profile(request: Request, doctor_id: int):
    doctor = DoctorService.get_doctor_details(doctor_id)
    if not doctor:
        return templates.TemplateResponse("404.html", {"request": request})

    return templates.TemplateResponse(
        "Website/Doctor/doctor_profile.html", {"request": request, "doctor": doctor}
    )
