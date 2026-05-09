from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.errors import BaseAPIException, global_exception_handler, generic_exception_handler
from app.api.routes import health, runs
from app.core.logging import logger
from app.services.queue_service import queue_service

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # For dev only, configure properly in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    app.add_exception_handler(BaseAPIException, global_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Routers
    app.include_router(health.router, prefix="", tags=["System"])
    app.include_router(runs.router, prefix=settings.API_V1_STR, tags=["Runs"])

    @app.on_event("startup")
    async def startup_event():
        logger.info("Application starting up...")
        await queue_service.connect()

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("Application shutting down...")
        await queue_service.disconnect()

    return app

app = create_app()
