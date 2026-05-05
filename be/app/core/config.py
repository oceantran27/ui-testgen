from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI TestGen Backend"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = (
        "API for UI TestGen: generate natural-language test scenarios from screenshots and organize behavior flows."
    )

    # HTTP server (local `python main.py`; override via env BACKEND_PORT)
    BACKEND_PORT: int = 18080

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None

    # Gemini
    GEMINI_API_KEY: Optional[str] = None

    # Single-stage: screenshot → structured test scenario suite JSON
    SINGLE_STAGE_TEST_SCENARIO_PROMPT_PATH: str = "app/llm_prompts/test_scenarios_from_ui_system_prompt.txt"

    # Two-stage: UI hierarchy JSON (stage 1) → test scenario suite JSON (stage 2)
    TWO_STAGE_UI_HIERARCHY_PROMPT_PATH: str = "app/llm_prompts/ui_extraction_system_prompt.txt"
    TWO_STAGE_TEST_SCENARIO_PROMPT_PATH: str = "app/llm_prompts/test_scenarios_from_ui_hierarchy_system_prompt.txt"
    # Defaults when POST /test-scenarios/from-image-bridged calls generate() with no model args (hybrid Gemini → OpenAI)
    TWO_STAGE_STAGE1_MODEL: str = "gemini-2.5-flash"
    TWO_STAGE_STAGE2_MODEL: str = "gpt-5"

    # Multi-image behavior flow clustering and ordering
    BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH: str = "app/llm_prompts/behavior_flow_cluster_order_system_prompt.txt"
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

    B2_PRESIGNED_EXPIRES_SECONDS: int = 3600
    B2_PRESIGNED_GET_EXPIRES_SECONDS: int = 3600

    SUPABASE_URL: Optional[str] = None
    SUPABASE_KEY: Optional[str] = None
    SUPABASE_ANALYSIS_TABLE: str = "user_goals_history"

    DATA_RETENTION_DAYS: int = 15

    B2_DEFAULT_INPUTS_PREFIX: str = "default-inputs"
    B2_USER_INPUTS_PREFIX: str = "user-inputs"

    @model_validator(mode="after")
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

        if not self.SINGLE_STAGE_TEST_SCENARIO_PROMPT_PATH:
            self.SINGLE_STAGE_TEST_SCENARIO_PROMPT_PATH = (
                "app/llm_prompts/test_scenarios_from_ui_system_prompt.txt"
            )

        if not self.TWO_STAGE_UI_HIERARCHY_PROMPT_PATH:
            self.TWO_STAGE_UI_HIERARCHY_PROMPT_PATH = "app/llm_prompts/ui_extraction_system_prompt.txt"

        if not self.TWO_STAGE_TEST_SCENARIO_PROMPT_PATH:
            self.TWO_STAGE_TEST_SCENARIO_PROMPT_PATH = (
                "app/llm_prompts/test_scenarios_from_ui_hierarchy_system_prompt.txt"
            )

        if not (self.TWO_STAGE_STAGE1_MODEL or "").strip():
            self.TWO_STAGE_STAGE1_MODEL = "gemini-2.5-flash"
        else:
            self.TWO_STAGE_STAGE1_MODEL = self.TWO_STAGE_STAGE1_MODEL.strip()

        if not (self.TWO_STAGE_STAGE2_MODEL or "").strip():
            self.TWO_STAGE_STAGE2_MODEL = "gpt-5"
        else:
            self.TWO_STAGE_STAGE2_MODEL = self.TWO_STAGE_STAGE2_MODEL.strip()

        if not self.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH:
            self.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH = (
                "app/llm_prompts/behavior_flow_cluster_order_system_prompt.txt"
            )

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
