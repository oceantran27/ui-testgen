from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # App config
    PROJECT_NAME: str = "UI TestGen API"
    ENVIRONMENT: str = "local" # local, dev, staging, prod
    API_V1_STR: str = "/api/v1"
    
    # Storage config (MinIO / S3)
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "minioadmin"
    STORAGE_SECRET_KEY: str = "minioadmin"
    STORAGE_BUCKET_NAME: str = "ui-testgen-local"
    STORAGE_SECURE: bool = False
    
    # Database config
    DATABASE_URL: str = "postgresql+asyncpg://testgen_user:testgen_password@localhost:5432/testgen_db"
    
    # Queue / Redis config
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Business logic config
    REQUIRED_VIEWPORT_WIDTH: int = 1440
    REQUIRED_VIEWPORT_HEIGHT: int = 900
    ALLOWED_IMAGE_FORMATS: List[str] = ["png", "jpg", "jpeg", "webp"]
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_IMAGES_PER_RUN: int = 50
    DUPLICATE_ALLOWED: bool = True
    UNORDERED_IMAGES_ALLOWED: bool = True
    INPUT_LEVEL_DETECTION: str = "auto"
    JOB_EXECUTION_MODE: str = "async"
    WORKER_CONCURRENCY: int = 2
    
    # Phase 3 — Duplicate detection
    PHASH_EXACT_THRESHOLD: int = 0         # distance = 0 → exact visual
    PHASH_NEAR_THRESHOLD: int = 5          # distance ≤ 5 → near-visual
    PHASH_UNCERTAIN_THRESHOLD: int = 10    # 6–10 → uncertain, needs VLM
    DHASH_NEAR_THRESHOLD: int = 5
    DUPLICATE_MIN_CONFIDENCE: float = 0.75 # min confidence to auto-merge semantic
    USE_VLM_FOR_DUPLICATE_CHECK: bool = False
    
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()
