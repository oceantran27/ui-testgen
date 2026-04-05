from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.api import api_router
import os
import logging
import time
from datetime import datetime, timedelta

# --- Logging Setup ---
LOG_FILE = "log.txt"
LOG_EXPIRATION_DAYS = 3

def setup_logging():
    """Configures logging with expiration policy."""
    if os.path.exists(LOG_FILE):
        creation_time = os.path.getctime(LOG_FILE)
        creation_date = datetime.fromtimestamp(creation_time)
        if datetime.now() - creation_date > timedelta(days=LOG_EXPIRATION_DAYS):
            try:
                os.remove(LOG_FILE)
                print(f"Old log file {LOG_FILE} removed (expired).")
            except Exception as e:
                print(f"Error removing old log file: {e}")

    logging.basicConfig(
        level=logging.INFO,
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

# Ensure the uploads directory exists
os.makedirs("uploads", exist_ok=True)

# Mount the 'uploads' directory to serve static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# Set all CORS enabled origins
if True: # Always enable CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], # Allow all origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
