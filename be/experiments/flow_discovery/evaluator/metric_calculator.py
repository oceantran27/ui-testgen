"""Aggregate P/R/F1 and error stats from matcher outputs."""

from __future__ import annotations

from typing import List

from experiments.flow_discovery.evaluator.transition_matcher import TransitionMatchBundle
from experiments.flow_discovery.schemas.evaluation_schema import (
    BranchMetrics,
    ErrorMetrics,
    EvaluationMetricsNested,
    FlowEvalItem,
    FlowMetrics,
    TransitionMetrics,
    TransitionMatchItem,
)


def _prf1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if fn == 0 else 0.0)
    rec = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if fp == 0 else 0.0)
    if prec + rec == 0:
        return prec, rec, 0.0
    f1 = 2 * prec * rec / (prec + rec)
    return prec, rec, f1


def transition_prf_from_bundle(bundle: TransitionMatchBundle, *, relaxed: bool = False) -> tuple[int, int, int, float, float, float]:
    items = bundle.relaxed_items if relaxed else bundle.strict_items
    fns = bundle.false_negatives_relaxed if relaxed else bundle.false_negatives_strict
    tp = sum(1 for i in items if i.match_status == "true_positive")
    fp = sum(1 for i in items if i.match_status == "false_positive")
    fn = len(fns)
    p, r, f = _prf1(tp, fp, fn)
    return tp, fp, fn, p, r, f


def flow_aggregates(flow_items: List[FlowEvalItem]) -> tuple[float, float]:
    if not flow_items:
        return 1.0, 1.0
    f1s = [float(it.membership_f1 or 0.0) for it in flow_items]
    ords = [float(it.ordering_accuracy or 1.0) for it in flow_items]
    return sum(f1s) / len(f1s), sum(ords) / len(ords)


def build_metrics(
    bundle: TransitionMatchBundle,
    flow_items: List[FlowEvalItem],
    branch_precision: float,
    branch_recall: float,
    branch_f1: float,
    *,
    invalid_transition_count: int,
    invalid_flow_rate: float,
) -> EvaluationMetricsNested:
    _, _, _, sp, sr, sf = transition_prf_from_bundle(bundle, relaxed=False)
    _, _, _, rp, rr, rf = transition_prf_from_bundle(bundle, relaxed=True)
    mem_f1, ord_acc = flow_aggregates(flow_items)

    return EvaluationMetricsNested(
        transition_metrics=TransitionMetrics(
            strict_precision=sp,
            strict_recall=sr,
            strict_f1=sf,
            relaxed_precision=rp,
            relaxed_recall=rr,
            relaxed_f1=rf,
        ),
        flow_metrics=FlowMetrics(
            membership_macro_f1=mem_f1,
            ordering_accuracy=ord_acc,
        ),
        branch_metrics=BranchMetrics(
            branch_precision=branch_precision,
            branch_recall=branch_recall,
            branch_f1=branch_f1,
        ),
        error_metrics=ErrorMetrics(
            invalid_transition_count=invalid_transition_count,
            invalid_flow_rate=invalid_flow_rate,
        ),
    )


def all_transition_items_for_report(bundle: TransitionMatchBundle) -> List[TransitionMatchItem]:
    """Strict-mode TP/FP plus FN rows (primary report view)."""

    return list(bundle.strict_items) + list(bundle.false_negatives_strict)
