from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    
    # Database
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DATABASE_URL: Optional[str] = None

    @model_validator(mode='after')
    def assemble_db_connection(self) -> "Settings":
        if self.DATABASE_URL is None:
            self.DATABASE_URL = f"mysql+mysqlconnector://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}/{self.DB_NAME}"
        return self

    # OpenAI
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
