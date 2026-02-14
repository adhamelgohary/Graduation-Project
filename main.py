import os
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException

from utils.auth_middleware import AuthMiddleware
from utils.error_handlers import not_found_error, internal_server_error
from routes import master_router
from utils.template_helpers import templates
from utils.admin_setup import setup_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Redis connection
    app.state.redis = redis.from_url(
        f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:6379",
        encoding="utf-8",
        decode_responses=True,
    )
    yield
    await app.state.redis.close()


app = FastAPI(title="Health Guide API", lifespan=lifespan)

# Error Handlers
app.add_exception_handler(HTTPException, not_found_error)
app.add_exception_handler(Exception, internal_server_error)

# Middleware
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "your-secret-key")
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Modular SQLAdmin setup
setup_admin(app)

# Include routes
app.include_router(master_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
