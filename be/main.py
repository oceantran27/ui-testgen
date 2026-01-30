from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.api import api_router
import os

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json")

# Ensure the uploads directory exists
os.makedirs("uploads", exist_ok=True)

# Mount the 'uploads' directory to serve static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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
