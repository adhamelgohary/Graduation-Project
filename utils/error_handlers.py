from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

templates = Jinja2Templates(directory="templates")


async def not_found_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": "Not Found"}, status_code=status.HTTP_404_NOT_FOUND
        )
    return templates.TemplateResponse(
        "errors/error_popup.html",
        {
            "request": request,
            "error_code": 404,
            "error_message": "Page not found. The resource you are looking for might have been removed or is temporarily unavailable.",
        },
        status_code=404,
    )


async def internal_server_error(request: Request, exc: Exception):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": "Internal Server Error"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return templates.TemplateResponse(
        "errors/error_popup.html",
        {
            "request": request,
            "error_code": 500,
            "error_message": "Internal Server Error. Something went wrong on our end. Please try again later.",
        },
        status_code=500,
    )
