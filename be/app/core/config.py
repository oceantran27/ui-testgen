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

    OPENAI_TEXT_MODEL: str = "gpt-5.4-mini"
    OPENAI_VISION_MODEL: str = "gpt-5.4-mini"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Timeouts / fallback
    VISION_MODEL_TIMEOUT_SECONDS: int = 120
    TEXT_MODEL_TIMEOUT_SECONDS: int = 60
    MODEL_MAX_RETRIES: int = 1
    MODEL_RETRY_BACKOFF_SECONDS: float = 1.5
    DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT: bool = False
    DISABLE_MODEL_HTTP_TIMEOUT: bool = False

    ENABLE_MODEL_FALLBACK: bool = True
    FALLBACK_MODEL_PROVIDER: str = "openai"

    USE_LLM_FOR_BEHAVIOUR_CONTRACT_BUILDER: bool = False
    USE_LLM_FOR_SCENARIO_GENERATION: bool = False
    USE_LLM_FOR_SCENARIO_VALIDATION: bool = True

    ENABLE_MODEL_RAW_RESPONSE_ARTIFACT: bool = True

    MOCK_MODEL_MODE: str = "success"  # success | schema_mismatch | timeout | provider_error

    # Phase 1: UI state extraction
    UI_STATE_EXTRACTION_PROVIDER: str = "gemini"
    UI_STATE_EXTRACTION_MODEL_NAME: str = "gemini-2.5-flash"
    UI_STATE_EXTRACTION_FALLBACK_PROVIDER: str = "openai"
    UI_STATE_EXTRACTION_FALLBACK_MODEL_NAME: str = "gpt-5.4-mini"
    UI_STATE_EXTRACTION_TIMEOUT_SECONDS: int = 120
    UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS: int = 12288
    UI_STATE_EXTRACTION_MAX_CONCURRENCY: int = Field(default=3, ge=1, le=50)
    SAVE_UI_STATE_EXTRACTION_REPORT: bool = True

    # Phase 2: Screen intent extraction
    SCREEN_INTENT_MODEL_PROVIDER: str = "openai"
    SCREEN_INTENT_MODEL_NAME: str = "gpt-5.4-nano"
    SCREEN_INTENT_FALLBACK_MODEL_NAME: str = "gpt-5.4-mini"
    SCREEN_INTENT_MAX_OUTPUT_TOKENS: int = 4096
    SCREEN_INTENT_MAX_CONCURRENCY: int = Field(default=8, ge=1, le=50)

    # Phase 3: Candidate edge resolver
    CANDIDATE_EDGE_STRONG_THRESHOLD: int = Field(default=85, ge=0, le=100)
    CANDIDATE_EDGE_ACCEPT_THRESHOLD: int = Field(default=72, ge=0, le=100)
    CANDIDATE_EDGE_PRUNE_THRESHOLD: int = Field(default=72, ge=0, le=100)
    CANDIDATE_EDGE_WEAK_THRESHOLD: int = Field(default=60, ge=0, le=100)
    CANDIDATE_EDGE_DISABLE_WEAK_BAND: bool = True
    CANDIDATE_EDGE_NEGATIVE_THRESHOLD: int = Field(default=68, ge=0, le=100)
    CANDIDATE_EDGE_NEUTRAL_PROGRESS_THRESHOLD: int = Field(default=78, ge=0, le=100)
    CANDIDATE_EDGE_FEEDBACK_ACK_THRESHOLD: int = Field(default=75, ge=0, le=100)
    # Deprecated: ignored by resolver v2 (kept for env compatibility).
    CANDIDATE_EDGE_DROP_BELOW_THRESHOLD: bool = False
    CANDIDATE_EDGE_MIN_NORMALIZED_SCORE: float = Field(default=0.25, ge=0.0, le=1.0)

    # Phase 4: Intent-aware flow discovery
    FLOW_DISCOVERY_MODEL_PROVIDER: str = "openai"
    FLOW_DISCOVERY_MODEL_NAME: str = "gpt-5.4-mini"
    FLOW_DISCOVERY_FALLBACK_MODEL_NAME: str = "gpt-5.4"
    FLOW_DISCOVERY_MAX_OUTPUT_TOKENS: int = 8192
    FLOW_DISCOVERY_MAX_CONCURRENCY: int = Field(default=3, ge=1, le=50)

    # Phase 5: Behaviour contract builder
    BEHAVIOUR_INTENT_MODEL_PROVIDER: str = "none"
    BEHAVIOUR_INTENT_MODEL_NAME: str = ""
    BEHAVIOUR_CONTRACT_BUILDER_MAX_OUTPUT_TOKENS: int = 8192

    # Phase 6: Scenario generation
    BDD_SCENARIO_GENERATION_MODEL_PROVIDER: str = "none"
    BDD_SCENARIO_GENERATION_MODEL_NAME: str = ""
    BDD_SCENARIO_GENERATION_MAX_OUTPUT_TOKENS: int = 4096

    # Phase 7: Scenario evidence audit
    SCENARIO_VALIDATION_MODEL_PROVIDER: str = "openai"
    SCENARIO_VALIDATION_MODEL_NAME: str = "gpt-5.4-mini"
    SCENARIO_VALIDATION_FALLBACK_MODEL_NAME: str = "gpt-5.4"
    SCENARIO_EVIDENCE_AUDIT_MAX_OUTPUT_TOKENS: int = 32768
    SCENARIO_EVIDENCE_AUDIT_TIMEOUT_SECONDS: int = 300
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
