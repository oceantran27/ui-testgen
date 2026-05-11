"""
Schema Registry — Pydantic v2 output schemas for all model calls.

Each schema is a Pydantic BaseModel that the model's structured output must conform to.
Active schemas are fully defined; skeleton schemas have minimal fields for future phases.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Active Schemas (used in current phases)
# ──────────────────────────────────────────────

class SemanticDuplicateVerificationResult(BaseModel):
    """Phase 3 VLM hook — pairwise semantic duplicate check."""
    schema_name: str = "SemanticDuplicateVerificationResult"
    schema_version: str = "v1"
    verdict: Literal["same_state", "different_state", "uncertain"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str
    evidence: Optional[List[str]] = None


class ScreenshotQualityVLMJudgement(BaseModel):
    """Phase 2 VLM hook — screenshot quality assessment."""
    schema_name: str = "ScreenshotQualityVLMJudgement"
    schema_version: str = "v1"
    is_valid: bool
    quality_score: float = Field(..., ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)
    reason: str


# ──────────────────────────────────────────────
# Skeleton Schemas (Phase 6+)
# ──────────────────────────────────────────────

class UIElementData(BaseModel):
    """A single UI element extracted by VLM."""
    type: Literal[
        "button", "input", "textarea", "checkbox", "radio", "dropdown", "link",
        "tab", "menu_item", "table", "table_row", "card", "image", "icon",
        "modal", "toast", "banner", "error_message", "success_message", 
        "warning_message", "navigation_item", "pagination", "breadcrumb", "unknown"
    ]
    label: Optional[str] = None
    text: Optional[str] = None
    placeholder: Optional[str] = None
    # Bbox from Gemini is typically [ymin, xmin, ymax, xmax] in 0-1000 scale.
    bbox_ymin_xmin_ymax_xmax: List[int] = Field(min_length=4, max_length=4)
    
    actionable: bool = False
    action_type: Optional[Literal[
        "click", "type", "select", "check", "uncheck", "open", "close",
        "navigate", "submit", "search", "filter", "unknown"
    ]] = None
    
    is_feedback: bool = False
    feedback_type: Optional[Literal[
        "error", "success", "warning", "info", "validation", "toast",
        "modal", "empty_state", "loading", "confirmation", "unknown"
    ]] = None

    confidence: float = Field(..., ge=0.0, le=1.0)


class UIStateExtractionResult(BaseModel):
    """Phase 6 — UI state extraction from screenshot."""
    schema_name: str = "UIStateExtractionResult"
    schema_version: str = "v1"
    
    page_type: Literal[
        "login_page", "register_page", "forgot_password_page", "dashboard_page",
        "home_page", "product_list_page", "product_detail_page", "cart_page",
        "checkout_page", "payment_page", "order_confirmation_page", "search_results_page",
        "form_page", "data_table_page", "settings_page", "profile_page", "admin_page",
        "modal_state", "error_page", "success_page", "empty_state_page", "unknown_page"
    ]
    state_summary: str
    
    has_form: bool
    has_table: bool
    has_modal: bool
    has_feedback: bool
    
    ui_elements: List[UIElementData] = Field(default_factory=list)
    visible_texts: List[str] = Field(default_factory=list)
    
    confidence: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)


class PairwiseStateComparisonResult(BaseModel):
    """Phase 6 — Compare two UI states."""
    schema_name: str = "PairwiseStateComparisonResult"
    schema_version: str = "v1"
    verdict: Literal["same", "different", "uncertain"] = "uncertain"
    confidence: float = 0.0
    differences: List[str] = Field(default_factory=list)
    reason: str = ""


class InputLevelClassificationResult(BaseModel):
    """Phase 6 — Classify input complexity level."""
    schema_name: str = "InputLevelClassificationResult"
    schema_version: str = "v1"
    level: Literal["single_screen", "multi_screen_single_flow", "multi_screen_multi_flow"] = "single_screen"
    confidence: float = 0.0
    reason: str = ""


class FlowDiscoveryResult(BaseModel):
    """Phase 7 — Discover user flows from UI states."""
    schema_name: str = "FlowDiscoveryResult"
    schema_version: str = "v1"
    flows: List[Dict] = Field(default_factory=list)
    flow_count: int = 0
    reasoning: str = ""


class MissingStepAnalysisResult(BaseModel):
    """Phase 7 — Detect missing steps in flows."""
    schema_name: str = "MissingStepAnalysisResult"
    schema_version: str = "v1"
    missing_steps: List[Dict] = Field(default_factory=list)
    completeness_score: float = 0.0
    reason: str = ""


class BehaviourIntentResult(BaseModel):
    """Phase 8 — Infer user intents from flows."""
    schema_name: str = "BehaviourIntentResult"
    schema_version: str = "v1"
    intents: List[Dict] = Field(default_factory=list)
    reason: str = ""


class BehaviourScenarioGenerationResult(BaseModel):
    """Phase 8 — Generate BDD scenarios."""
    schema_name: str = "BehaviourScenarioGenerationResult"
    schema_version: str = "v1"
    scenarios: List[Dict] = Field(default_factory=list)
    total_scenarios: int = 0


# ──────────────────────────────────────────────
# Research Model-First Schemas (v1)
# ──────────────────────────────────────────────

class SemanticDuplicateMember(BaseModel):
    state_id: str
    image_id: str
    role: Literal["canonical", "duplicate"]

class SemanticDuplicateGroup(BaseModel):
    group_id: str
    canonical_state_id: str
    duplicate_state_ids: List[str]
    duplicate_type: Literal[
        "same_observable_ui_state",
        "minor_visual_variation",
        "focus_or_cursor_only",
        "dynamic_content_only"
    ]
    confidence: float
    evidence: List[str]
    reason: str
    should_merge: bool

class SemanticDuplicateOutput(BaseModel):
    duplicate_groups: List[SemanticDuplicateGroup]
    non_duplicate_state_ids: List[str]
    warnings: List[str] = Field(default_factory=list)


class FlowTransitionJudgement(BaseModel):
    from_state_id: str
    to_state_id: str
    transition_type: Literal[
        "form_submission_success",
        "form_submission_error",
        "navigation_result",
        "modal_opened",
        "filter_or_search_result",
        "create_update_delete_result",
        "same_page_feedback",
        "unknown_transition"
    ]
    hypothesized_user_action: str
    observed_result: str
    evidence_state_ids: List[str]
    evidence_element_ids: List[str] = Field(default_factory=list)
    inference_level: Literal[
        "grounded_by_before_after_states",
        "partially_inferred_from_ui_delta",
        "inferred_only"
    ]
    confidence: float
    confidence_label: Literal["high", "medium", "low"]
    reason: str
    warnings: List[str] = Field(default_factory=list)

class FlowClusterOutput(BaseModel):
    flow_name: str
    flow_type: Literal[
        "positive_behaviour_flow",
        "negative_behaviour_flow",
        "navigation_flow",
        "single_state_inferred_flow",
        "unknown_flow"
    ]
    ordered_state_ids: List[str]
    transitions: List[FlowTransitionJudgement]
    behaviour_hint: str
    completeness_status: Literal[
        "complete_enough",
        "missing_initial_state",
        "missing_final_verification",
        "single_state_inferred",
        "uncertain_order"
    ]
    scenario_generation_mode: Literal[
        "grounded",
        "partially_inferred",
        "inferred_only",
        "do_not_generate"
    ]
    confidence: float
    reason: str
    warnings: List[str] = Field(default_factory=list)

class LLMFlowDiscoveryOutput(BaseModel):
    flows: List[FlowClusterOutput]
    unassigned_state_ids: List[str]
    global_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {
    "SemanticDuplicateVerificationResult": SemanticDuplicateVerificationResult,
    "ScreenshotQualityVLMJudgement": ScreenshotQualityVLMJudgement,
    "UIStateExtractionResult": UIStateExtractionResult,
    "PairwiseStateComparisonResult": PairwiseStateComparisonResult,
    "InputLevelClassificationResult": InputLevelClassificationResult,
    "FlowDiscoveryResult": FlowDiscoveryResult,
    "MissingStepAnalysisResult": MissingStepAnalysisResult,
    "BehaviourIntentResult": BehaviourIntentResult,
    "BehaviourScenarioGenerationResult": BehaviourScenarioGenerationResult,
    "SemanticDuplicateOutput": SemanticDuplicateOutput,
    "LLMFlowDiscoveryOutput": LLMFlowDiscoveryOutput,
}


def get_schema(name: str) -> Type[BaseModel]:
    """Look up a schema by name. Raises KeyError if not found."""
    if name not in SCHEMA_REGISTRY:
        raise KeyError(f"Schema '{name}' not found in registry. Available: {list(SCHEMA_REGISTRY.keys())}")
    return SCHEMA_REGISTRY[name]
