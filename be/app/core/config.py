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

    # Module 1 - Vision Extractor
    VISION_EXTRACTOR_PROMPT_PATH: str = "app/prompts/vision_extractor_system_prompt.txt"

    # Module 2 - Evaluator & Rationalizer
    EVALUATOR_RATIONALIZER_PROMPT_PATH: str = "app/prompts/evaluator_rationalizer_system_prompt.txt"
    EVALUATOR_RATIONALIZER_PROMPT_VERSION: str = "v1"


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
    B2_PRESIGNED_GET_EXPIRES_SECONDS: int = 3600

    # Supabase
    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_ANALYSIS_TABLE: str = "user_goals_history"

    # Data retention
    DATA_RETENTION_DAYS: int = 15

    # B2 object prefixes
    B2_DEFAULT_INPUTS_PREFIX: str = "default-inputs"
    B2_USER_INPUTS_PREFIX: str = "user-inputs"

    @model_validator(mode='after')
    def normalize_storage_and_b2_credentials(self) -> "Settings":

        storage_type = (self.STORAGE_TYPE or "local").strip().lower()
        if storage_type == "db":
            storage_type = "local"
        if storage_type not in {"local", "b2", "auto"}:
            storage_type = "local"
        self.STORAGE_TYPE = storage_type

        self.SUPABASE_ANALYSIS_TABLE = (self.SUPABASE_ANALYSIS_TABLE or "user_goals_history").strip()

        self.B2_DEFAULT_INPUTS_PREFIX = (self.B2_DEFAULT_INPUTS_PREFIX or "default-inputs").strip().strip("/")
        self.B2_USER_INPUTS_PREFIX = (self.B2_USER_INPUTS_PREFIX or "user-inputs").strip().strip("/")

        if self.DATA_RETENTION_DAYS <= 0:
            self.DATA_RETENTION_DAYS = 15

        if not self.VISION_EXTRACTOR_PROMPT_PATH:
            self.VISION_EXTRACTOR_PROMPT_PATH = "app/prompts/vision_extractor_system_prompt.txt"

        if not self.EVALUATOR_RATIONALIZER_PROMPT_PATH:
            self.EVALUATOR_RATIONALIZER_PROMPT_PATH = "app/prompts/evaluator_rationalizer_system_prompt.txt"

        if not self.EVALUATOR_RATIONALIZER_PROMPT_VERSION:
            self.EVALUATOR_RATIONALIZER_PROMPT_VERSION = "v1"

        return self
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
