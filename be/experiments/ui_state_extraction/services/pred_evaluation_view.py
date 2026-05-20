"""Key-multiset prediction view for module 3 (legacy-free path; Sprint 4+)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from experiments.ui_state_extraction.services.evaluation_key_service import (
    ActionKey,
    ElementKey,
    FeedbackKey,
    IntentKey,
)


@dataclass
class PredEvaluationDiagnostics:
    """Units seen without an evaluable key (excluded from quality multiset PRF until wired)."""

    skipped_empty_key_element: int = 0
    skipped_empty_key_action: int = 0
    skipped_empty_key_feedback: int = 0
    skipped_empty_key_intent: int = 0
    prediction_auto_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScreenEvaluationFields:
    presentation_scope: str = "unknown"
    screen_type: str = "other"
    outcome_state_type: str = "neutral"


@dataclass
class PredEvaluationView:
    """Multiset of evaluation keys from raw Joint model output (no ID matching / grounding)."""

    screen_fields: ScreenEvaluationFields
    element_keys: Counter[ElementKey] = field(default_factory=Counter)
    action_keys: Counter[ActionKey] = field(default_factory=Counter)
    feedback_keys: Counter[FeedbackKey] = field(default_factory=Counter)
    intent_keys: Counter[IntentKey] = field(default_factory=Counter)
    diagnostics: PredEvaluationDiagnostics = field(default_factory=PredEvaluationDiagnostics)
