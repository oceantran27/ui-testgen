from typing import Optional

from pydantic import AliasChoices, Field, model_validator

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"

    PROJECT_NAME: str = "UI TestGen Backend"

    PROJECT_VERSION: str = "1.0.0"

    PROJECT_DESCRIPTION: str = (
        "API for UI TestGen: LangGraph pipeline for state graph and scenario generation from screenshots."
    )

    BACKEND_PORT: int = 18080

    OPENAI_API_KEY: Optional[str] = None

    GEMINI_API_KEY: Optional[str] = None

    UI_EXTRACTION_PROMPT_PATH: str = Field(
        default="app/llm_prompts/ui_extraction_system_prompt.txt",
        validation_alias=AliasChoices("UI_EXTRACTION_PROMPT_PATH", "TWO_STAGE_UI_HIERARCHY_PROMPT_PATH"),
    )

    # Multi-image state-graph upload limits (shared name with legacy behavior-flow settings)
    BEHAVIOR_FLOW_MAX_IMAGES: int = 40

    BEHAVIOR_FLOW_MAX_FILE_BYTES: int = 12 * 1024 * 1024  # 12 MiB per file

    STATE_GRAPH_FROM_INTENTS_PROMPT_PATH: str = (
        "app/llm_prompts/state_graph_from_ui_intents_system_prompt.txt"
    )

    STATE_GRAPH_UI_EXTRACTION_MODEL: str = "gemini-2.5-flash"

    STATE_GRAPH_USER_INTENT_MODEL: str = "gpt-5-mini"
    STATE_GRAPH_FLOW_MODEL: str = "gpt-5-mini"

    STATE_GRAPH_E2E_SCENARIO_MODEL: str = "gpt-5-mini"

    STATE_GRAPH_ISOLATED_SCENARIOS_PROMPT_PATH: str = (
        "app/llm_prompts/isolated_scenarios_generation_system_prompt.txt"
    )
    STATE_GRAPH_FLOW_SCENARIOS_PROMPT_PATH: str = "app/llm_prompts/flow_scenarios_generation_system_prompt.txt"
    STATE_GRAPH_CRITIC_PROMPT_PATH: str = "app/llm_prompts/critic_scenarios_evaluation_system_prompt.txt"

    STATE_GRAPH_CLIP_MODEL_ID: str = "openai/clip-vit-base-patch32"

    STATE_GRAPH_CLIP_DEVICE: Optional[str] = None  # e.g. "cuda", "cpu"; None = auto

    STATE_GRAPH_IMAGE_DEDUP_COSINE_THRESHOLD: float = 0.92

    @model_validator(mode="after")
    def normalize_state_graph_settings(self) -> "Settings":
        if self.BEHAVIOR_FLOW_MAX_IMAGES <= 0:
            self.BEHAVIOR_FLOW_MAX_IMAGES = 40
        if self.BEHAVIOR_FLOW_MAX_FILE_BYTES <= 0:
            self.BEHAVIOR_FLOW_MAX_FILE_BYTES = 12 * 1024 * 1024

        if not self.UI_EXTRACTION_PROMPT_PATH:
            self.UI_EXTRACTION_PROMPT_PATH = "app/llm_prompts/ui_extraction_system_prompt.txt"

        if not self.STATE_GRAPH_FROM_INTENTS_PROMPT_PATH:
            self.STATE_GRAPH_FROM_INTENTS_PROMPT_PATH = (
                "app/llm_prompts/state_graph_from_ui_intents_system_prompt.txt"
            )

        if not (self.STATE_GRAPH_UI_EXTRACTION_MODEL or "").strip():
            self.STATE_GRAPH_UI_EXTRACTION_MODEL = "gemini-2.5-flash"
        else:
            self.STATE_GRAPH_UI_EXTRACTION_MODEL = self.STATE_GRAPH_UI_EXTRACTION_MODEL.strip()

        if not (self.STATE_GRAPH_USER_INTENT_MODEL or "").strip():
            self.STATE_GRAPH_USER_INTENT_MODEL = "gpt-5-mini"
        else:
            self.STATE_GRAPH_USER_INTENT_MODEL = self.STATE_GRAPH_USER_INTENT_MODEL.strip()

        if not (self.STATE_GRAPH_FLOW_MODEL or "").strip():
            self.STATE_GRAPH_FLOW_MODEL = "gpt-5-mini"
        else:
            self.STATE_GRAPH_FLOW_MODEL = self.STATE_GRAPH_FLOW_MODEL.strip()

        if not (getattr(self, "STATE_GRAPH_E2E_SCENARIO_MODEL", None) or "").strip():
            self.STATE_GRAPH_E2E_SCENARIO_MODEL = "gpt-5-mini"
        else:
            self.STATE_GRAPH_E2E_SCENARIO_MODEL = self.STATE_GRAPH_E2E_SCENARIO_MODEL.strip()

        if not getattr(self, "STATE_GRAPH_ISOLATED_SCENARIOS_PROMPT_PATH", None):
            self.STATE_GRAPH_ISOLATED_SCENARIOS_PROMPT_PATH = (
                "app/llm_prompts/isolated_scenarios_generation_system_prompt.txt"
            )

        if not getattr(self, "STATE_GRAPH_FLOW_SCENARIOS_PROMPT_PATH", None):
            self.STATE_GRAPH_FLOW_SCENARIOS_PROMPT_PATH = (
                "app/llm_prompts/flow_scenarios_generation_system_prompt.txt"
            )

        if not getattr(self, "STATE_GRAPH_CRITIC_PROMPT_PATH", None):
            self.STATE_GRAPH_CRITIC_PROMPT_PATH = "app/llm_prompts/critic_scenarios_evaluation_system_prompt.txt"

        return self

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
