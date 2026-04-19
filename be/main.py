import logging
import os
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings

# --- Logging Setup ---
LOG_FILE = "log.txt"

def setup_logging():
    """Configures logging with expiration policy."""
    if os.path.exists(LOG_FILE):
        creation_time = os.path.getctime(LOG_FILE)
        creation_date = datetime.fromtimestamp(creation_time)
        if datetime.now() - creation_date > timedelta(days=settings.LOG_RETENTION_DAYS):
            try:
                os.remove(LOG_FILE)
                print(f"Old log file {LOG_FILE} removed (expired).")
            except Exception as e:
                print(f"Error removing old log file: {e}")

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.info("Logging initialized.")

setup_logging()
# ---------------------

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
