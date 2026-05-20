"""Structured JSONL debug log for module 2 (temp GT build) and module 3 (evaluation)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from app.core.logging import logger

from experiments.ui_state_extraction.schemas.evaluation_result_schema import PerImageEvaluationResult
from experiments.ui_state_extraction.schemas.evaluation_unit_schema import PredictionEvaluationBundle
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import ConversionReport, TempGroundTruthDocument
from experiments.ui_state_extraction.services.evaluation_key_service import summarize_evaluation_keys
from experiments.ui_state_extraction.services.ground_truth_normalizer_service import GtEvaluationView
from experiments.ui_state_extraction.services.key_metric_service import (
    PrincipalMultisetMetricBundle,
    compute_multiset_principal_metrics,
)
from experiments.ui_state_extraction.services.pred_evaluation_view import PredEvaluationView
from experiments.ui_state_extraction.services.unit_matching_service import (
    compute_intent_field_metrics,
    match_all_units,
    required_input_mapping_explain,
)


EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION = "experiment_pipeline_debug_v2"
_INVALID_REF_PREVIEW_LIMIT = 20
_EVAL_KEY_SUMMARY_EACH_CAP = 25

K = TypeVar("K")


def new_debug_log_path(log_dir: Path, *, run_prefix: str = "experiment_debug") -> Path:
    """Path to a new JSONL file for one CLI run (UTC timestamp in filename)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return log_dir / f"{run_prefix}_{ts}.jsonl"


def append_jsonl_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _evaluation_key_to_json(key: Any) -> Any:
    """Tuples (incl. IntentKey nesting) → JSON-serializable nested lists."""
    if isinstance(key, tuple):
        return [_evaluation_key_to_json(x) for x in key]
    return key


def _expand_counter_sorted_json(cnt: Counter[K]) -> list[Any]:
    """Multiset expansion into lists (stable repr sort), multiplicity preserved."""
    out: list[Any] = []
    for k, n in sorted(cnt.items(), key=lambda kv: repr(kv[0])):
        plain = _evaluation_key_to_json(k)
        out.extend([plain] * int(n))
    return out


def _matched_multiset(pred: Counter[K], gt: Counter[K]) -> Counter[K]:
    m: Counter[K] = Counter()
    for key in pred.keys() | gt.keys():
        c = min(int(pred[key]), int(gt[key]))
        if c > 0:
            m[key] = c
    return m


def _key_human_readable(key: Any) -> str:
    if isinstance(key, tuple):
        inner = ",".join(_key_human_readable(k) if isinstance(k, tuple) else repr(str(k)) for k in key)
        return f"({inner})"
    return repr(str(key))


def _category_debug_blocks(
    pred_c: Counter[K],
    gt_c: Counter[K],
    extra: Counter[K],
    missing: Counter[K],
) -> dict[str, Any]:
    return {
        "pred_keys": _expand_counter_sorted_json(pred_c),
        "gt_keys": _expand_counter_sorted_json(gt_c),
        "matched_keys": _expand_counter_sorted_json(_matched_multiset(pred_c, gt_c)),
        "extra_keys": _expand_counter_sorted_json(extra),
        "missing_keys": _expand_counter_sorted_json(missing),
    }


def _parse_skipped_ids_from_auto_flags(
    pred_view: PredEvaluationView,
    gt_view: GtEvaluationView,
) -> dict[str, list[str]]:
    """Split pred/gt *_key_missing:<id|idx> traces into predictable bucket names."""
    out: dict[str, list[str]] = {
        "elements_missing_key_pred": [],
        "elements_missing_key_gt": [],
        "actions_missing_key_pred": [],
        "actions_missing_key_gt": [],
        "feedback_missing_key_pred": [],
        "feedback_missing_key_gt": [],
        "intents_missing_key_pred": [],
        "intents_missing_key_gt": [],
    }

    pred_map = (
        ("pred_element_key_missing:", "elements_missing_key_pred"),
        ("pred_action_key_missing:", "actions_missing_key_pred"),
        ("pred_feedback_key_missing:", "feedback_missing_key_pred"),
        ("pred_intent_key_missing:", "intents_missing_key_pred"),
    )
    gt_map = (
        ("gt_element_key_missing:", "elements_missing_key_gt"),
        ("gt_action_key_missing:", "actions_missing_key_gt"),
        ("gt_feedback_key_missing:", "feedback_missing_key_gt"),
        ("gt_intent_key_missing:", "intents_missing_key_gt"),
    )

    for flag in pred_view.diagnostics.prediction_auto_flags:
        for pref, rk in pred_map:
            if flag.startswith(pref):
                out[rk].append(flag[len(pref) :])
                break

    for flag in gt_view.diagnostics.gt_evaluation_auto_flags:
        for pref, rk in gt_map:
            if flag.startswith(pref):
                out[rk].append(flag[len(pref) :])
                break

    return out


def _eval_key_summaries_from_bundle(bundle: PrincipalMultisetMetricBundle, *, cap_each: int) -> list[str]:
    specs = (
        ("element", bundle.element),
        ("action", bundle.action),
        ("feedback", bundle.feedback),
        ("intent", bundle.intent),
    )
    lines: list[str] = []
    for name, kr in specs:
        n_ex = 0
        for k, mul in sorted(kr.extra.items(), key=lambda kv: repr(kv[0])):
            for _ in range(int(mul)):
                if n_ex >= cap_each:
                    break
                lines.append(f"Pred extra ({name}): {_key_human_readable(k)}")
                n_ex += 1
            if n_ex >= cap_each:
                break
        n_miss = 0
        for k, mul in sorted(kr.missing.items(), key=lambda kv: repr(kv[0])):
            for _ in range(int(mul)):
                if n_miss >= cap_each:
                    break
                lines.append(f"GT missing ({name}): {_key_human_readable(k)}")
                n_miss += 1
            if n_miss >= cap_each:
                break
    return lines


def build_eval_key_debug_payload(
    raw_model_output: dict[str, Any],
    gt: TempGroundTruthDocument,
) -> tuple[dict[str, Any], list[str]]:
    """Multiset Pred/GT key debug blocks + human-readable imbalance lines."""
    bundle, pred_view, gt_view = compute_multiset_principal_metrics(raw_model_output, gt)

    element_block = _category_debug_blocks(
        pred_view.element_keys,
        gt_view.element_keys,
        bundle.element.extra,
        bundle.element.missing,
    )
    action_block = _category_debug_blocks(
        pred_view.action_keys,
        gt_view.action_keys,
        bundle.action.extra,
        bundle.action.missing,
    )
    feedback_block = _category_debug_blocks(
        pred_view.feedback_keys,
        gt_view.feedback_keys,
        bundle.feedback.extra,
        bundle.feedback.missing,
    )

    intent_block = _category_debug_blocks(
        pred_view.intent_keys,
        gt_view.intent_keys,
        bundle.intent.extra,
        bundle.intent.missing,
    )

    skipped_units = _parse_skipped_ids_from_auto_flags(pred_view, gt_view)
    summaries = _eval_key_summaries_from_bundle(bundle, cap_each=_EVAL_KEY_SUMMARY_EACH_CAP)

    return (
        {
            "element_debug": element_block,
            "action_debug": {}
            if (bundle.action.pred_count == 0 and bundle.action.gt_count == 0)
            else action_block,
            "feedback_debug": {}
            if (bundle.feedback.pred_count == 0 and bundle.feedback.gt_count == 0)
            else feedback_block,
            "intent_debug": {}
            if (bundle.intent.pred_count == 0 and bundle.intent.gt_count == 0)
            else intent_block,
            "skipped_units": skipped_units,
        },
        summaries,
    )


def _summarize_invalid_references(report: ConversionReport) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ir in report.invalid_references[:_INVALID_REF_PREVIEW_LIMIT]:
        out.append({"field": ir.field, "source_id": ir.source_id, "reason": ir.reason})
    return out


def append_module2_event(
    log_path: Path,
    *,
    image_id: str,
    relative_path: str,
    conversion_status: str,
    error_message: str | None = None,
    raw_output_path: str = "",
    temp_ground_truth_path: str = "",
    review_priority: str | None = None,
    conversion_report: ConversionReport | None = None,
    verbose_log: bool = False,
    gt_document: TempGroundTruthDocument | None = None,
) -> None:
    """Append one module-2 line: conversion outcome + summary of flags / invalid refs."""
    record: dict[str, Any] = {
        "schema_version": EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION,
        "module": "m2",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "image_id": image_id,
        "relative_path": relative_path,
        "conversion_status": conversion_status,
        "error_message": error_message,
        "paths": {
            "raw_output": raw_output_path,
            "temp_ground_truth": temp_ground_truth_path,
        },
        "review_priority": review_priority,
    }
    if conversion_report is not None:
        ct = conversion_report.counts
        record["conversion_summary"] = {
            "auto_flag_count": len(conversion_report.auto_flags),
            "invalid_reference_count": len(conversion_report.invalid_references),
            "counts": {
                "elements": ct.elements,
                "actions": ct.actions,
                "feedback": ct.feedback,
                "groups": ct.groups,
                "screen_intents": ct.screen_intents,
                "unresolved_groups": ct.unresolved_groups,
            },
            "invalid_references_preview": _summarize_invalid_references(conversion_report),
        }
        if verbose_log:
            record["conversion_summary"]["auto_flags"] = list(conversion_report.auto_flags)
        elif len(conversion_report.auto_flags) <= 30:
            record["conversion_summary"]["auto_flags"] = list(conversion_report.auto_flags)
        else:
            record["conversion_summary"]["auto_flags_head"] = conversion_report.auto_flags[:30]
    if verbose_log and gt_document is not None and conversion_status == "converted":
        record["evaluation_keys"] = summarize_evaluation_keys(gt_document)
    append_jsonl_line(log_path, record)
    if verbose_log:
        logger.info(
            "[m2-debug] %s image_id=%s flags=%s invalid=%s",
            conversion_status,
            image_id,
            len(conversion_report.auto_flags) if conversion_report else 0,
            len(conversion_report.invalid_references) if conversion_report else 0,
        )


def append_module3_event(
    log_path: Path,
    *,
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    per_image: PerImageEvaluationResult,
    group_jaccard_threshold: float,
    raw_output_path: str = "",
    temp_ground_truth_path: str = "",
    verbose_log: bool = False,
    raw_model_output: dict[str, Any] | None = None,
) -> None:
    """Append one module-3 line: metrics heads, intent remap explain, multiset key debug."""
    m = match_all_units(pred, gt, group_jaccard_threshold=group_jaccard_threshold)
    el_m = m.pred_to_gt_element
    intent_explain: list[dict[str, Any]] = []
    for p_int in pred.intents:
        g_int = m.pred_intent_index_to_gt_intent.get(p_int.pred_intent_index)
        if not g_int:
            continue
        row = required_input_mapping_explain(p_int, g_int, el_m, gt)
        intent_explain.append(row)

    em = per_image.element_metrics
    ac_m = m.pred_to_gt_action
    fb_m = m.pred_to_gt_feedback
    ig_m = m.pred_to_gt_group
    intent_step_debug: list[dict[str, Any]] = []
    for p_int in pred.intents:
        g_int = m.pred_intent_index_to_gt_intent.get(p_int.pred_intent_index)
        if not g_int:
            continue
        mfields = compute_intent_field_metrics(p_int, g_int, el_m, ac_m, fb_m, ig_m, gt)
        sd = mfields.get("step_debug") or {}
        intent_step_debug.append(
            {
                "pred_intent_index": p_int.pred_intent_index,
                "gt_intent_id": g_int.gt_intent_id,
                **sd,
            },
        )

    record: dict[str, Any] = {
        "schema_version": EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION,
        "module": "m3",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "image_id": gt.image.image_id,
        "relative_path": gt.image.relative_path,
        "group_jaccard_threshold": group_jaccard_threshold,
        "paths": {
            "raw_output": raw_output_path,
            "temp_ground_truth": temp_ground_truth_path,
        },
        "metrics_head": {
            "element_f1": per_image.element_metrics.f1,
            "text_grounded_matched_count": em.text_grounded_matched_count,
            "text_grounded_pred_count": em.text_grounded_pred_count,
            "text_grounded_gt_count": em.text_grounded_gt_count,
            "pred_empty_anchor_element_count": em.pred_empty_anchor_element_count,
            "gt_empty_anchor_element_count": em.gt_empty_anchor_element_count,
            "intent_matched_count": per_image.intent_metrics.matched_count,
            "required_input_f1_block": per_image.intent_metrics.required_input_f1,
            "required_input_correct_count": per_image.intent_metrics.required_input_correct_count,
            "required_input_pred_count": per_image.intent_metrics.required_input_pred_count,
            "required_input_gt_count": per_image.intent_metrics.required_input_gt_count,
            "evidence_target_f1": per_image.intent_metrics.evidence_target_f1,
            "evidence_target_correct_count": per_image.intent_metrics.evidence_target_correct_count,
            "evidence_target_pred_count": per_image.intent_metrics.evidence_target_pred_count,
            "evidence_target_gt_count": per_image.intent_metrics.evidence_target_gt_count,
            "step_grounding_accuracy": per_image.intent_metrics.step_grounding_accuracy,
            "step_f1": per_image.intent_metrics.step_f1,
            "step_correct_count": per_image.intent_metrics.step_correct_count,
            "step_pred_count": per_image.intent_metrics.step_pred_count,
            "step_gt_count": per_image.intent_metrics.step_gt_count,
            "empty_anchor_excluded_refs": {
                "required_input_gt": per_image.intent_metrics.required_input_empty_anchor_excluded_gt_refs,
                "required_input_pred": per_image.intent_metrics.required_input_empty_anchor_excluded_pred_refs,
                "evidence_gt": per_image.intent_metrics.evidence_empty_anchor_excluded_gt_refs,
                "evidence_pred": per_image.intent_metrics.evidence_empty_anchor_excluded_pred_refs,
                "steps": per_image.intent_metrics.step_empty_anchor_excluded_count,
                "feedback_related_gt": per_image.feedback_metrics.feedback_related_empty_anchor_excluded_gt_refs,
                "feedback_related_pred": per_image.feedback_metrics.feedback_related_empty_anchor_excluded_pred_refs,
                "group_membership_gt": per_image.group_metrics.group_membership_empty_anchor_excluded_gt_refs,
                "group_membership_pred": per_image.group_metrics.group_membership_empty_anchor_excluded_pred_refs,
            },
        },
        "intent_required_input_explain": intent_explain,
        "intent_step_debug": intent_step_debug,
    }
    if raw_model_output is not None:
        eval_body, summary_lines = build_eval_key_debug_payload(raw_model_output, gt)
        record["eval_key_debug"] = eval_body
        if summary_lines:
            record["eval_key_debug_summary"] = summary_lines
    if verbose_log:
        record["unmatched_pred_elements"] = [
            r["pred_element_id"] for r in m.element_rows if not r.get("gt_element_id")
        ]
    append_jsonl_line(log_path, record)
    if verbose_log:
        logger.info(
            "[m3-debug] image_id=%s intent_explain=%s ri_f1=%s",
            gt.image.image_id,
            len(intent_explain),
            per_image.intent_metrics.required_input_f1,
        )
