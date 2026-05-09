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
    
    # Phase 2 — Image viewport bands (orientation-invariant)
    VIEWPORT_SHORT_EDGE_MIN: int = 900
    VIEWPORT_SHORT_EDGE_MAX: int = 1400
    VIEWPORT_LONG_EDGE_MIN: int = 1400
    VIEWPORT_LONG_EDGE_MAX: int = 2500
    VIEWPORT_ASPECT_RATIO_MIN: float = 1.5
    VIEWPORT_ASPECT_RATIO_MAX: float = 2.0
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
    
    # Phase 4 — Graph Configuration
    ENABLE_GRAPH_CHECKPOINT: bool = True
    ENABLE_GRAPH_ARTIFACT_SNAPSHOT: bool = True
    ENABLE_FUTURE_AI_NODES: bool = False
    
    # Phase 5 — Model Provider
    DEFAULT_MODEL_PROVIDER: str = "gemini"
    
    # Per-provider model names (override per node via config or env)
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"
    OPENAI_TEXT_MODEL: str = "gpt-5-mini"
    OPENAI_VISION_MODEL: str = "gpt-5-mini"
    
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    
    MODEL_DEFAULT_TIMEOUT_SECONDS: int = 60
    VISION_MODEL_TIMEOUT_SECONDS: int = 90
    TEXT_MODEL_TIMEOUT_SECONDS: int = 60
    
    MODEL_MAX_RETRIES: int = 2
    MODEL_RETRY_BACKOFF_SECONDS: float = 2.0
    
    ENABLE_MODEL_FALLBACK: bool = False
    FALLBACK_MODEL_PROVIDER: str = "openai"
    
    USE_VLM_FOR_UI_STATE_EXTRACTION: bool = True
    USE_LLM_FOR_FLOW_DISCOVERY: bool = True
    USE_LLM_FOR_SCENARIO_GENERATION: bool = True
    USE_LLM_FOR_SCENARIO_VALIDATION: bool = True
    
    ENABLE_MODEL_RAW_RESPONSE_ARTIFACT: bool = True
    ENABLE_MODEL_REQUEST_SUMMARY_ARTIFACT: bool = False
    
    MOCK_MODEL_MODE: str = "success"      # success | schema_mismatch | timeout | provider_error
    
    # Phase 6 — UI State Understanding
    ENABLE_UI_STATE_EXTRACTION_NODE: bool = True
    USE_OCR_FOR_UI_TEXT_EXTRACTION: bool = False  # Set False for MVP as requested
    SAVE_UI_STATE_RAW_EXTRACTION: bool = True
    SAVE_UI_STATE_EXTRACTION_REPORT: bool = True
    
    # Provider for Phase 6 (overrideable)
    UI_STATE_EXTRACTION_PROVIDER: str = "gemini"
    UI_STATE_EXTRACTION_TIMEOUT_SECONDS: int = 120
    UI_STATE_EXTRACTION_MAX_RETRIES: int = 2
    # Phase 6 JSON can be very large (many ui_elements); default 4096 often truncates mid-string.
    UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS: int = 16384

    # Phase 7 — Input Level Detection
    ENABLE_INPUT_LEVEL_DETECTION_NODE: bool = True
    LEVEL3_GROUP_SEPARATION_THRESHOLD: float = 0.70
    LEVEL2_COHERENCE_THRESHOLD: float = 0.60
    LOW_CONFIDENCE_STATE_PENALTY: float = 0.10
    AMBIGUITY_PENALTY: float = 0.15
    USE_LLM_FOR_INPUT_LEVEL_DETECTION: bool = False
    SAVE_INPUT_LEVEL_DETECTION_REPORT: bool = True

    # Phase 8 — Flow Discovery
    ENABLE_FLOW_DISCOVERY_NODE: bool = True
    TRANSITION_STRONG_THRESHOLD: float = 0.85
    TRANSITION_ACCEPT_THRESHOLD: float = 0.65
    TRANSITION_WEAK_THRESHOLD: float = 0.45
    FLOW_CLUSTERING_THRESHOLD: float = 0.60
    USE_LLM_FOR_FLOW_DISCOVERY: bool = False
    SAVE_FLOW_DISCOVERY_REPORT: bool = True
    
    # Phase 9 — Missing Step Analysis
    ENABLE_MISSING_STEP_ANALYSIS_NODE: bool = True
    CRITICAL_MISSING_STEP_PENALTY: float = 0.40
    HIGH_MISSING_STEP_PENALTY: float = 0.25
    MEDIUM_MISSING_STEP_PENALTY: float = 0.15
    LOW_MISSING_STEP_PENALTY: float = 0.05
    MAX_MISSING_STEP_TOTAL_PENALTY: float = 0.70
    MIN_USABLE_FLOW_CONFIDENCE_AFTER_PENALTY: float = 0.30
    USE_LLM_FOR_MISSING_STEP_ANALYSIS: bool = False
    SAVE_MISSING_STEP_ANALYSIS_REPORT: bool = True
    
    # Phase 10 — Behaviour Intent Inference
    ENABLE_BEHAVIOUR_INTENT_INFERENCE_NODE: bool = True
    MIN_INTENT_CONFIDENCE_TO_GENERATE: float = 0.40
    MIN_INTENT_CONFIDENCE_FOR_GROUNDED: float = 0.65
    USE_LLM_FOR_BEHAVIOUR_INTENT_INFERENCE: bool = True # Enabled as per user request
    BEHAVIOUR_INTENT_MODEL_PROVIDER: str = "openai"
    BEHAVIOUR_INTENT_MODEL_NAME: str = "gpt-4o-mini"
    SAVE_BEHAVIOUR_INTENT_REPORT: bool = True
    
    # Phase 11 — Behaviour Scenario Generation
    ENABLE_BEHAVIOUR_SCENARIO_GENERATION_NODE: bool = True
    USE_LLM_FOR_SCENARIO_GENERATION: bool = True
    ALLOW_INFERRED_ONLY_SCENARIOS: bool = True
    SAVE_SCENARIO_GENERATION_REPORT: bool = True
    
    # Phase 12 — Scenario Grounding & Validation
    ENABLE_SCENARIO_GROUNDING_VALIDATION_NODE: bool = True
    USE_LLM_FOR_SCENARIO_VALIDATION: bool = True
    VALIDATED_GROUNDING_SCORE_THRESHOLD: float = 0.75
    LOW_CONFIDENCE_GROUNDING_SCORE_THRESHOLD: float = 0.50
    SAVE_SCENARIO_VALIDATION_REPORT: bool = True
    
    # Phase 13 — Scenario Curation
    ENABLE_SCENARIO_CURATION_NODE: bool = True
    USE_LLM_FOR_SCENARIO_CURATION: bool = True
    SAVE_SCENARIO_CURATION_REPORT: bool = True
    
    # Phase 14 — Output Assembly
    ENABLE_OUTPUT_ASSEMBLY_NODE: bool = True
    SAVE_FINAL_OUTPUT_JSON: bool = True
    SAVE_GHERKIN_EXPORT: bool = True
    SAVE_MARKDOWN_SUMMARY_REPORT: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()
