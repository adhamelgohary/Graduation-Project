from fastapi import APIRouter, Request, Query, HTTPException

# removed local Jinja2Templates import
from services.department_service import DepartmentService
from fastapi.responses import JSONResponse

department_router = APIRouter()
from utils.template_helpers import templates


@department_router.get("/")
async def list_departments(request: Request):
    departments = DepartmentService.get_all_departments()
    return templates.TemplateResponse(
        "Website/Department/department_list.html",
        {"request": request, "departments": departments},
    )


@department_router.get("/{dept_id}/")
async def department_landing(request: Request, dept_id: int, search: str = Query("")):
    dept = DepartmentService.get_department_details(dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    conditions = DepartmentService.get_conditions_by_department(
        dept_id, search_term=search
    )

    return templates.TemplateResponse(
        "Website/Department/department_landing.html",
        {
            "request": request,
            "department": dept,
            "conditions": conditions,
            "search_term": search,
        },
    )


# This handles the condition detail view (merged logic)
@department_router.get("/condition/{condition_id}/")
async def condition_detail_page(request: Request, condition_id: int):
    condition, doctors = DepartmentService.get_condition_details(condition_id)
    if not condition:
        raise HTTPException(status_code=404, detail="Condition not found")

    return templates.TemplateResponse(
        "Website/DiseaseInfo/disease_detail.html",
        {
            "request": request,
            "condition": condition,
            "doctors": doctors,
            "page_title": condition.get("name"),
        },
    )
