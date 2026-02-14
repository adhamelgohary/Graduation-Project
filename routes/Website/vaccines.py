from fastapi import APIRouter, Request, HTTPException

# removed local Jinja2Templates import
from services.vaccine_service import VaccineService

vaccines_router = APIRouter()
from utils.template_helpers import templates


@vaccines_router.get("/")
async def vaccine_landing(request: Request):
    return templates.TemplateResponse(
        "Website/Vaccines/vaccine_landing.html",
        {
            "request": request,
            "categories": VaccineService.get_categories(),
            # You can add common_vaccines here if you add the method to the service
        },
    )


@vaccines_router.get("/vaccine/{vaccine_id}")
async def vaccine_detail(request: Request, vaccine_id: int):
    vaccine = VaccineService.get_vaccine_details(vaccine_id)
    if not vaccine:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "Website/Vaccines/vaccine_condition_details.html",
        {
            "request": request,
            "data": vaccine,
            "data_type": "vaccine",
            "page_title": vaccine.get("vaccine_name"),
        },
    )
