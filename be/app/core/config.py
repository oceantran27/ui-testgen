from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    
    # Database
    DATABASE_URL: str = "mysql+mysqlconnector://user:password@localhost/db_name"
    
    # OpenAI
    OPENAI_API_KEY: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
