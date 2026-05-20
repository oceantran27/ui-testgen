"""Multiset evaluation keys from TempGroundTruthDocument (Sprint 5, mirrors PredEvaluationView)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import TempGroundTruthDocument
from experiments.ui_state_extraction.services.evaluation_key_service import (
    ActionKey,
    ElementKey,
    FeedbackKey,
    IntentKey,
    action_key,
    build_action_lookup_by_id,
    element_key,
    feedback_key,
    intent_key,
)
from experiments.ui_state_extraction.services.pred_evaluation_view import ScreenEvaluationFields


@dataclass
class GtEvaluationDiagnostics:
    """Counts of GT units omitted from multiset (no evaluable key)."""

    skipped_empty_key_element: int = 0
    skipped_empty_key_action: int = 0
    skipped_empty_key_feedback: int = 0
    skipped_empty_key_intent: int = 0
    gt_evaluation_auto_flags: list[str] = field(default_factory=list)


@dataclass
class GtEvaluationView:
    """Multiset of evaluation keys from module-2 temp ground truth."""

    screen_fields: ScreenEvaluationFields
    element_keys: Counter[ElementKey] = field(default_factory=Counter)
    action_keys: Counter[ActionKey] = field(default_factory=Counter)
    feedback_keys: Counter[FeedbackKey] = field(default_factory=Counter)
    intent_keys: Counter[IntentKey] = field(default_factory=Counter)
    diagnostics: GtEvaluationDiagnostics = field(default_factory=GtEvaluationDiagnostics)


def build_gt_evaluation_view(gt: TempGroundTruthDocument) -> GtEvaluationView:
    diag = GtEvaluationDiagnostics()
    scr = gt.screen

    screen_fields = ScreenEvaluationFields(
        presentation_scope=str(scr.presentation_scope or "unknown"),
        screen_type=str(scr.screen_type or "other"),
        outcome_state_type=str(scr.outcome_state_type or "neutral"),
    )

    element_keys: Counter[ElementKey] = Counter()
    for el in gt.elements:
        ek = element_key(el)
        if ek is None:
            diag.skipped_empty_key_element += 1
            diag.gt_evaluation_auto_flags.append(f"gt_element_key_missing:{el.gt_element_id}")
        else:
            element_keys[ek] += 1

    action_keys: Counter[ActionKey] = Counter()
    for ac in gt.actions:
        ak = action_key(ac)
        if ak is None:
            diag.skipped_empty_key_action += 1
            diag.gt_evaluation_auto_flags.append(f"gt_action_key_missing:{ac.gt_action_id}")
        else:
            action_keys[ak] += 1

    feedback_keys: Counter[FeedbackKey] = Counter()
    for fb in gt.feedback:
        fk = feedback_key(fb)
        if fk is None:
            diag.skipped_empty_key_feedback += 1
            diag.gt_evaluation_auto_flags.append(f"gt_feedback_key_missing:{fb.gt_feedback_id}")
        else:
            feedback_keys[fk] += 1

    intent_keys: Counter[IntentKey] = Counter()
    ac_lut = build_action_lookup_by_id(gt.actions)
    for it in gt.screen_intents:
        ik = intent_key(it, ac_lut)
        if ik is None:
            diag.skipped_empty_key_intent += 1
            diag.gt_evaluation_auto_flags.append(f"gt_intent_key_missing:{it.gt_intent_id}")
        else:
            intent_keys[ik] += 1

    return GtEvaluationView(
        screen_fields=screen_fields,
        element_keys=element_keys,
        action_keys=action_keys,
        feedback_keys=feedback_keys,
        intent_keys=intent_keys,
        diagnostics=diag,
    )
