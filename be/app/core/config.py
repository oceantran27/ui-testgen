from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # App config
    PROJECT_NAME: str = "UI TestGen API"
    ENVIRONMENT: str = "local"  # local, dev, staging, prod
    API_V1_STR: str = "/api/v1"

    # Storage config (MinIO / S3)
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "minioadmin"
    STORAGE_SECRET_KEY: str = "minioadmin"
    STORAGE_BUCKET_NAME: str = "ui-testgen-local"
    STORAGE_SECURE: bool = False

    # Database config (Docker compose maps host 5433 → Postgres 5432 in container)
    DATABASE_URL: str = "postgresql+asyncpg://testgen_user:testgen_password@localhost:5433/testgen_db"

    # Queue / Redis config
    REDIS_URL: str = "redis://localhost:6379/0"
    # ARQ worker: max wall time for entire process_run job.
    ARQ_JOB_NO_TIMEOUT: bool = True
    ARQ_JOB_TIMEOUT_SECONDS: int = 14400  # 4 hours
    ARQ_INTERPRET_300S_AS_LONG_JOB: bool = True
    ARQ_JOB_LONG_PIPELINE_FALLBACK_SECONDS: int = 14400

    # Uploads & run input policy
    ALLOWED_IMAGE_FORMATS: List[str] = ["png", "jpg", "jpeg", "webp"]
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_IMAGES_PER_RUN: int = 50
    DUPLICATE_ALLOWED: bool = True
    UNORDERED_IMAGES_ALLOWED: bool = True
    INPUT_LEVEL_DETECTION: str = "auto"
    JOB_EXECUTION_MODE: str = "async"

    # LangGraph
    ENABLE_GRAPH_CHECKPOINT: bool = True

    # Model providers
    DEFAULT_MODEL_PROVIDER: str = "openai"
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"
    OPENAI_TEXT_MODEL: str = "gpt-5-mini"
    OPENAI_VISION_MODEL: str = "gpt-5-mini"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    VISION_MODEL_TIMEOUT_SECONDS: int = 90
    TEXT_MODEL_TIMEOUT_SECONDS: int = 60

    MODEL_MAX_RETRIES: int = 2
    MODEL_RETRY_BACKOFF_SECONDS: float = 2.0
    DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT: bool = True
    DISABLE_MODEL_HTTP_TIMEOUT: bool = True

    ENABLE_MODEL_FALLBACK: bool = False
    FALLBACK_MODEL_PROVIDER: str = "gemini"

    USE_VLM_FOR_UI_STATE_EXTRACTION: bool = True
    USE_LLM_FOR_FLOW_DISCOVERY: bool = True
    USE_LLM_FOR_SCENARIO_GENERATION: bool = True
    USE_LLM_FOR_SCENARIO_VALIDATION: bool = True

    ENABLE_MODEL_RAW_RESPONSE_ARTIFACT: bool = True

    MOCK_MODEL_MODE: str = "success"  # success | schema_mismatch | timeout | provider_error

    # UI state extraction (vision)
    UI_STATE_EXTRACTION_PROVIDER: str = "openai"
    UI_STATE_EXTRACTION_MODEL_NAME: str = "gpt-5.4-mini"
    UI_STATE_EXTRACTION_TIMEOUT_SECONDS: int = 120
    UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS: int = 16384
    UI_STATE_EXTRACTION_MAX_CONCURRENCY: int = Field(default=5, ge=1, le=50)
    SAVE_UI_STATE_EXTRACTION_REPORT: bool = True

    # Screen intent extraction v2 + intent-aware flow discovery (shared provider defaults)
    LLM_FLOW_DISCOVERY_MODEL_PROVIDER: str = "openai"
    LLM_FLOW_DISCOVERY_MODEL_NAME: str = "gpt-5.4-mini"
    LLM_FLOW_DISCOVERY_MAX_OUTPUT_TOKENS: int = 16384
    LLM_FLOW_DISCOVERY_MAX_CONCURRENCY: int = Field(default=5, ge=1, le=50)

    # Behaviour contract builder (env names retain legacy “behaviour intent” wording)
    BEHAVIOUR_INTENT_MODEL_PROVIDER: str = "openai"
    BEHAVIOUR_INTENT_MODEL_NAME: str = "gpt-5.4-mini"
    BEHAVIOUR_CONTRACT_BUILDER_MAX_OUTPUT_TOKENS: int = 32768

    # BDD scenario generation
    BDD_SCENARIO_GENERATION_MODEL_PROVIDER: str = "openai"
    BDD_SCENARIO_GENERATION_MODEL_NAME: str = "gpt-5.4-nano"
    BDD_SCENARIO_GENERATION_MAX_OUTPUT_TOKENS: int = 16384

    # Scenario evidence audit (env names retain legacy “scenario validation” wording)
    SCENARIO_VALIDATION_MODEL_PROVIDER: str = "openai"
    SCENARIO_VALIDATION_MODEL_NAME: str = "gpt-5.4"
    SCENARIO_EVIDENCE_AUDIT_MAX_OUTPUT_TOKENS: int = 65536
    SCENARIO_EVIDENCE_AUDIT_TIMEOUT_SECONDS: int = 600
    SCENARIO_EVIDENCE_AUDIT_SCENARIO_BATCH_SIZE: int = 3

    SAVE_RESEARCH_FINAL_OUTPUT: bool = True

    PIPELINE_RUN_LOG_ENABLED: bool = True
    PIPELINE_RUN_LOG_ROOT: str = "var/pipeline_run_logs"

    API_ERROR_LOG_ENABLED: bool = True
    API_ERROR_LOG_ROOT: str = "var/api_error_logs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

settings = Settings()
