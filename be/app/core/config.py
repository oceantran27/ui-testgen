from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API for UI TestGen, providing endpoints to analyze UI screenshots and generate test cases."

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    
    # Gemini
    GEMINI_API_KEY: Optional[str] = None

    # Backblaze B2
    B2_KEY_ID: Optional[str] = None
    B2_KEY_NAME: Optional[str] = None
    B2_APPLICATION_KEY: Optional[str] = None
    B2_BUCKET_NAME: Optional[str] = None
    B2_ENDPOINT: Optional[str] = None
    B2_REGION: Optional[str] = None
    STORAGE_TYPE: str = "local"  # 'local' | 'b2' | 'auto' (legacy: 'db' -> 'local')

    # B2 S3-compatible presigned upload settings
    B2_PRESIGNED_EXPIRES_SECONDS: int = 3600

    # Supabase
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None

    # Redis / Upstash
    REDIS_URL: Optional[str] = None
    DEFAULT_INPUTS_CACHE_KEY: str = "default_inputs:all"
    DEFAULT_INPUTS_CACHE_TTL_SECONDS: int = 3600
    USER_SESSION_TTL_SECONDS: int = 3600

    # Admin auth
    ADMIN_API_KEY: Optional[str] = None

    @model_validator(mode='after')
    def normalize_storage_and_b2_credentials(self) -> "Settings":

        storage_type = (self.STORAGE_TYPE or "local").strip().lower()
        if storage_type == "db":
            storage_type = "local"
        if storage_type not in {"local", "b2", "auto"}:
            storage_type = "local"
        self.STORAGE_TYPE = storage_type

        return self
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
