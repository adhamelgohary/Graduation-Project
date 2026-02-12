import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Import master router
from routes import master_router

app = FastAPI(title="Health Guide API")

# Middleware
app.add_middleware(
    SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "your-secret-key")
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Single line to include ALL routes from all portals and auth!
app.include_router(master_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
