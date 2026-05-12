from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.api_error_log import api_error_logging_middleware
from app.core.errors import BaseAPIException, global_exception_handler, generic_exception_handler
from app.api.routes import health, runs
from app.core.logging import logger
from app.services.queue_service import queue_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    await queue_service.connect()
    if settings.JOB_EXECUTION_MODE == "async":
        logger.info(
            "Job queue is async: submitted runs are processed by the ARQ worker, not this API "
            "process. If runs stay `queued`, start: arq app.workers.main_worker.WorkerSettings"
        )
    try:
        yield
    finally:
        logger.info("Application shutting down...")
        await queue_service.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # For dev only, configure properly in prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(api_error_logging_middleware)

    # Exception Handlers
    app.add_exception_handler(BaseAPIException, global_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # Routers
    app.include_router(health.router, prefix="", tags=["System"])
    app.include_router(runs.router, prefix=settings.API_V1_STR, tags=["Runs"])

    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
