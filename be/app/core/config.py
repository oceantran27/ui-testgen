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

    # Multi-Agent Committee
    COMMITTEE_MAX_FAILSAFE_ROUNDS: int = 5
    COMMITTEE_SCORE_DELTA_THRESHOLD: float = 1.0
    COMMITTEE_LLM_TIMEOUT_SECONDS: int = 45
    COMMITTEE_MAX_CONCURRENCY: int = 5
    COMMITTEE_WEIGHT_BA: float = 0.4
    COMMITTEE_WEIGHT_QA: float = 0.3
    COMMITTEE_WEIGHT_UX: float = 0.3
    COMMITTEE_RANKER_VERSION: str = "v1"
    COMMITTEE_AGENT_BA_PROMPT_PATH: str = "app/prompts/committee_agent1_business_analyst_system_prompt.txt"
    COMMITTEE_AGENT_QA_PROMPT_PATH: str = "app/prompts/committee_agent2_security_qa_system_prompt.txt"
    COMMITTEE_AGENT_UX_PROMPT_PATH: str = "app/prompts/committee_agent3_ux_expert_system_prompt.txt"
    COMMITTEE_AGENT_JUDGE_PROMPT_PATH: str = "app/prompts/committee_agent4_judge_moderator_system_prompt.txt"
    COMMITTEE_LOG_STRUCTURED_ENABLED: bool = True
    COMMITTEE_LOG_LEGACY_ENABLED: bool = True
    COMMITTEE_LOG_MAX_TEXT_CHARS: int = 320
    COMMITTEE_EVENT_STREAM_ENABLED: bool = True
    COMMITTEE_EVENT_STREAM_TTL_SECONDS: int = 3600
    COMMITTEE_EVENT_STREAM_MAX_REQUESTS: int = 300
    COMMITTEE_EVENT_STREAM_MAX_EVENTS_PER_REQUEST: int = 2500
    COMMITTEE_EVENT_STREAM_POLL_MAX_LIMIT: int = 250


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

        if self.COMMITTEE_MAX_FAILSAFE_ROUNDS <= 0:
            self.COMMITTEE_MAX_FAILSAFE_ROUNDS = 5

        if self.COMMITTEE_SCORE_DELTA_THRESHOLD < 0:
            self.COMMITTEE_SCORE_DELTA_THRESHOLD = 1.0

        if self.COMMITTEE_LLM_TIMEOUT_SECONDS <= 0:
            self.COMMITTEE_LLM_TIMEOUT_SECONDS = 45

        if self.COMMITTEE_MAX_CONCURRENCY <= 0:
            self.COMMITTEE_MAX_CONCURRENCY = 5

        self.COMMITTEE_WEIGHT_BA = max(0.0, self.COMMITTEE_WEIGHT_BA)
        self.COMMITTEE_WEIGHT_QA = max(0.0, self.COMMITTEE_WEIGHT_QA)
        self.COMMITTEE_WEIGHT_UX = max(0.0, self.COMMITTEE_WEIGHT_UX)

        if not self.COMMITTEE_RANKER_VERSION:
            self.COMMITTEE_RANKER_VERSION = "v1"

        if not self.COMMITTEE_AGENT_BA_PROMPT_PATH:
            self.COMMITTEE_AGENT_BA_PROMPT_PATH = "app/prompts/committee_agent1_business_analyst_system_prompt.txt"

        if not self.COMMITTEE_AGENT_QA_PROMPT_PATH:
            self.COMMITTEE_AGENT_QA_PROMPT_PATH = "app/prompts/committee_agent2_security_qa_system_prompt.txt"

        if not self.COMMITTEE_AGENT_UX_PROMPT_PATH:
            self.COMMITTEE_AGENT_UX_PROMPT_PATH = "app/prompts/committee_agent3_ux_expert_system_prompt.txt"

        if not self.COMMITTEE_AGENT_JUDGE_PROMPT_PATH:
            self.COMMITTEE_AGENT_JUDGE_PROMPT_PATH = "app/prompts/committee_agent4_judge_moderator_system_prompt.txt"

        if self.COMMITTEE_LOG_MAX_TEXT_CHARS < 80:
            self.COMMITTEE_LOG_MAX_TEXT_CHARS = 80

        if self.COMMITTEE_EVENT_STREAM_TTL_SECONDS < 60:
            self.COMMITTEE_EVENT_STREAM_TTL_SECONDS = 60

        if self.COMMITTEE_EVENT_STREAM_MAX_REQUESTS < 10:
            self.COMMITTEE_EVENT_STREAM_MAX_REQUESTS = 10

        if self.COMMITTEE_EVENT_STREAM_MAX_EVENTS_PER_REQUEST < 50:
            self.COMMITTEE_EVENT_STREAM_MAX_EVENTS_PER_REQUEST = 50

        if self.COMMITTEE_EVENT_STREAM_POLL_MAX_LIMIT < 10:
            self.COMMITTEE_EVENT_STREAM_POLL_MAX_LIMIT = 10

        return self
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
