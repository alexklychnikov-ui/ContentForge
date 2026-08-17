import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.brands import router as brands_router
from app.api.catalogs import router as catalogs_router
from app.api.channels import router as channels_router
from app.api.content import router as content_router
from app.api.experiments import router as experiments_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.media import router as media_router
from app.api.plans import router as plans_router
from app.api.publish import router as publish_router
from app.api.recipients import router as recipients_router
from app.config import get_settings
from app.errors import (
    AppError,
    app_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.logutil import RequestContextMiddleware, configure_app_logging
from app.services.token_crypto import TokenEncryptionError, get_fernet


def create_app() -> FastAPI:
    settings = get_settings()
    if os.environ.get("TESTING") != "1":
        try:
            get_fernet()
        except TokenEncryptionError as exc:
            raise RuntimeError(str(exc)) from exc
    application = FastAPI(title="ContentForge", version="0.7.0")
    configure_app_logging()
    application.add_middleware(RequestContextMiddleware)
    web_origin = settings.public_web_url.rstrip("/")
    allow_origins = list(
        dict.fromkeys([web_origin, "http://localhost:5173", "http://127.0.0.1:5173"])
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.include_router(health_router)
    application.include_router(auth_router, prefix="/api/v1")
    application.include_router(brands_router, prefix="/api/v1")
    application.include_router(catalogs_router, prefix="/api/v1")
    application.include_router(plans_router, prefix="/api/v1")
    application.include_router(content_router, prefix="/api/v1")
    application.include_router(jobs_router, prefix="/api/v1")
    application.include_router(publish_router, prefix="/api/v1")
    application.include_router(analytics_router, prefix="/api/v1")
    application.include_router(experiments_router, prefix="/api/v1")
    application.include_router(channels_router, prefix="/api/v1")
    application.include_router(recipients_router, prefix="/api/v1")
    application.include_router(media_router, prefix="/api/v1")
    return application


app = create_app()
