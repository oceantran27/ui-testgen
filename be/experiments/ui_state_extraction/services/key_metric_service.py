"""Multiset Counter precision/recall/F1 over hashable Counter keys (Sprint 6)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import TempGroundTruthDocument
from experiments.ui_state_extraction.services.ground_truth_normalizer_service import (
    GtEvaluationView,
    build_gt_evaluation_view,
)
from experiments.ui_state_extraction.services.pred_evaluation_view import PredEvaluationView
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    build_prediction_evaluation_view,
)

K = TypeVar("K")


def _prf_ratios(
    correct: int,
    pred_count: int,
    gt_count: int,
) -> tuple[float | None, float | None, float | None]:
    """Aligned with metric_calculation_service._prf."""
    prec = (float(correct) / pred_count) if pred_count else None
    rec = (float(correct) / gt_count) if gt_count else None
    if prec is None or rec is None:
        return prec, rec, None
    if prec + rec == 0:
        return prec, rec, 0.0
    return prec, rec, (2 * prec * rec / (prec + rec))


@dataclass(frozen=True)
class KeyPrfResult(Generic[K]):
    correct_count: int
    pred_count: int
    gt_count: int
    precision: float | None
    recall: float | None
    f1: float | None
    extra: Counter[K]
    missing: Counter[K]


def counter_prf(pred: Counter[K], gt: Counter[K]) -> KeyPrfResult[K]:
    """Multiset overlap Σ_k min(pred[k], gt[k]) as intersection multiplicity."""
    correct = 0
    for key in pred.keys() | gt.keys():
        correct += min(pred[key], gt[key])
    pred_n = sum(pred.values())
    gt_n = sum(gt.values())
    p, r, f1 = _prf_ratios(correct, pred_n, gt_n)
    return KeyPrfResult(
        correct_count=correct,
        pred_count=pred_n,
        gt_count=gt_n,
        precision=p,
        recall=r,
        f1=f1,
        extra=pred - gt,
        missing=gt - pred,
    )


def counter_to_json_repr(cnt: Counter[Any]) -> dict[str, int]:
    """JSON-stable key strings via repr for tuple-shaped keys."""
    out: dict[str, int] = {}
    for key, mul in sorted(cnt.items(), key=lambda kv: repr(kv[0])):
        out[repr(key)] = mul
    return out


@dataclass(frozen=True)
class PrincipalMultisetMetricBundle:
    """Multiset PRF for element/action/feedback/intent + 3-field screen enums."""

    element: KeyPrfResult[Any]
    action: KeyPrfResult[Any]
    feedback: KeyPrfResult[Any]
    intent: KeyPrfResult[Any]
    presentation_scope_correct: bool
    screen_type_correct: bool
    outcome_state_type_correct: bool
    screen_enum_accuracy: float


def compute_multiset_principal_metrics(
    raw_model_output: dict[str, Any],
    gt_doc: TempGroundTruthDocument,
) -> tuple[PrincipalMultisetMetricBundle, PredEvaluationView, GtEvaluationView]:
    pred_view = build_prediction_evaluation_view(raw_model_output)
    gt_view = build_gt_evaluation_view(gt_doc)

    el = counter_prf(pred_view.element_keys, gt_view.element_keys)
    ac = counter_prf(pred_view.action_keys, gt_view.action_keys)
    fb = counter_prf(pred_view.feedback_keys, gt_view.feedback_keys)
    it = counter_prf(pred_view.intent_keys, gt_view.intent_keys)

    ps = pred_view.screen_fields
    gs = gt_doc.screen
    psc = ps.presentation_scope == gs.presentation_scope
    st_ok = ps.screen_type == gs.screen_type
    ost_ok = ps.outcome_state_type == gs.outcome_state_type
    screen_enum_accuracy = sum((psc, st_ok, ost_ok)) / 3.0

    bundle = PrincipalMultisetMetricBundle(
        element=el,
        action=ac,
        feedback=fb,
        intent=it,
        presentation_scope_correct=psc,
        screen_type_correct=st_ok,
        outcome_state_type_correct=ost_ok,
        screen_enum_accuracy=screen_enum_accuracy,
    )
    return bundle, pred_view, gt_view


def multiset_debug_dict(
    bundle: PrincipalMultisetMetricBundle,
    pred_view: PredEvaluationView,
    gt_view: GtEvaluationView,
) -> dict[str, Any]:
    """Per-image diagnostics for aggregation / JSON reports."""
    return {
        "screen": {
            "presentation_scope_correct": bundle.presentation_scope_correct,
            "screen_type_correct": bundle.screen_type_correct,
            "outcome_state_type_correct": bundle.outcome_state_type_correct,
            "screen_enum_accuracy": bundle.screen_enum_accuracy,
        },
        "element_extra": counter_to_json_repr(bundle.element.extra),
        "element_missing": counter_to_json_repr(bundle.element.missing),
        "action_extra": counter_to_json_repr(bundle.action.extra),
        "action_missing": counter_to_json_repr(bundle.action.missing),
        "feedback_extra": counter_to_json_repr(bundle.feedback.extra),
        "feedback_missing": counter_to_json_repr(bundle.feedback.missing),
        "intent_extra": counter_to_json_repr(bundle.intent.extra),
        "intent_missing": counter_to_json_repr(bundle.intent.missing),
        "prediction_auto_flags_pred_view": pred_view.diagnostics.prediction_auto_flags,
        "gt_evaluation_auto_flags": gt_view.diagnostics.gt_evaluation_auto_flags,
    }
