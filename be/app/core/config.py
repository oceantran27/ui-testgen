from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API for UI TestGen, providing endpoints to analyze UI screenshots and generate test cases."
    
    # Database
    DB_HOST: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_NAME: Optional[str] = None
    DATABASE_URL: Optional[str] = None

    @model_validator(mode='after')
    def assemble_db_connection(self) -> "Settings":
        if self.DATABASE_URL:
            return self

        if self.DB_HOST and self.DB_USER and self.DB_PASSWORD is not None and self.DB_NAME:
            self.DATABASE_URL = f"mysql+mysqlconnector://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}/{self.DB_NAME}"
            return self
        
        raise ValueError("Database configuration is missing. "
                         "Please set either DATABASE_URL or all of DB_HOST, DB_USER, DB_PASSWORD, and DB_NAME.")

    # OpenAI
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
