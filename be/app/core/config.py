from typing import Optional

from pydantic import Field, field_validator
from pydantic import model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API for UI TestGen, providing endpoints to analyze UI screenshots and generate test cases."

    # Gemini
    GEMINI_API_KEY: Optional[str] = None

    # Provider selection
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-2.5-flash"

    # Runtime controls
    LOG_LEVEL: str = "INFO"
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    LOG_RETENTION_DAYS: int = 3

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return ["*"]
            if normalized.startswith("["):
                return value
            return [part.strip() for part in normalized.split(",") if part.strip()]
        return value

    @model_validator(mode='after')
    def normalize_settings(self) -> "Settings":
        self.LLM_PROVIDER = (self.LLM_PROVIDER or "gemini").strip().lower()
        self.LLM_MODEL = (self.LLM_MODEL or "gemini-2.5-flash").strip()
        self.LOG_LEVEL = (self.LOG_LEVEL or "INFO").strip().upper()

        if self.LOG_RETENTION_DAYS <= 0:
            self.LOG_RETENTION_DAYS = 3

        return self
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
