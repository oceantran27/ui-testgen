from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import model_validator

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API for UI TestGen, providing endpoints to analyze UI screenshots and generate test cases."

    # HTTP server (local `python main.py`; override via env BACKEND_PORT)
    BACKEND_PORT: int = 18080

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    # Gemini
    GEMINI_API_KEY: Optional[str] = None

    # Vision Extractor (behavior-level JSON)
    VISION_EXTRACTOR_PROMPT_PATH: str = "app/llm_prompts/vision_extractor_system_prompt.txt"

    # BDD happy path (Gherkin from UI screenshot)
    BDD_HAPPY_PATH_PROMPT_PATH: str = "app/llm_prompts/bdd_happy_path_from_ui_system_prompt.txt"

    # BDD two-stage Module 2 (UI hierarchy vision JSON → text-only Gherkin JSON)
    BDD_BRIDGE_STAGE1_PROMPT_PATH: str = "app/llm_prompts/ui_extraction_system_prompt.txt"
    BDD_BRIDGE_STAGE2_PROMPT_PATH: str = "app/llm_prompts/bdd_from_ui_hierarchy_system_prompt.txt"

    # BDD scenario ordering by business_intent (text-only LLM)
    BDD_SCENARIO_RANKING_PROMPT_PATH: str = "app/llm_prompts/bdd_scenario_rank_from_business_intent_system_prompt.txt"

    # Multi-image behavior flow clustering and ordering
    BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH: str = "app/llm_prompts/behavior_flow_cluster_order_system_prompt.txt"
    # Limits for POST /behavior-flows/organize
    BEHAVIOR_FLOW_MAX_IMAGES: int = 40
    BEHAVIOR_FLOW_MAX_FILE_BYTES: int = 12 * 1024 * 1024  # 12 MiB per file
    BEHAVIOR_FLOW_MAX_IMAGE_EDGE: int = 1280  # max longer edge when resizing for Gemini (px)

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
            self.VISION_EXTRACTOR_PROMPT_PATH = "app/llm_prompts/vision_extractor_system_prompt.txt"

        if not self.BDD_HAPPY_PATH_PROMPT_PATH:
            self.BDD_HAPPY_PATH_PROMPT_PATH = "app/llm_prompts/bdd_happy_path_from_ui_system_prompt.txt"

        if not self.BDD_BRIDGE_STAGE1_PROMPT_PATH:
            self.BDD_BRIDGE_STAGE1_PROMPT_PATH = "app/llm_prompts/ui_extraction_system_prompt.txt"

        if not self.BDD_BRIDGE_STAGE2_PROMPT_PATH:
            self.BDD_BRIDGE_STAGE2_PROMPT_PATH = "app/llm_prompts/bdd_from_ui_hierarchy_system_prompt.txt"

        if not self.BDD_SCENARIO_RANKING_PROMPT_PATH:
            self.BDD_SCENARIO_RANKING_PROMPT_PATH = "app/llm_prompts/bdd_scenario_rank_from_business_intent_system_prompt.txt"

        if not self.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH:
            self.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH = "app/llm_prompts/behavior_flow_cluster_order_system_prompt.txt"

        if self.BEHAVIOR_FLOW_MAX_IMAGES <= 0:
            self.BEHAVIOR_FLOW_MAX_IMAGES = 40
        if self.BEHAVIOR_FLOW_MAX_FILE_BYTES <= 0:
            self.BEHAVIOR_FLOW_MAX_FILE_BYTES = 12 * 1024 * 1024
        if self.BEHAVIOR_FLOW_MAX_IMAGE_EDGE <= 0:
            self.BEHAVIOR_FLOW_MAX_IMAGE_EDGE = 1280

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
