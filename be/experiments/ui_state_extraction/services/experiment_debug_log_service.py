"""Structured JSONL debug log for module 2 (temp GT build) and module 3 (evaluation)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging import logger

from experiments.ui_state_extraction.schemas.evaluation_result_schema import PerImageEvaluationResult
from experiments.ui_state_extraction.schemas.evaluation_unit_schema import PredictionEvaluationBundle
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import ConversionReport, TempGroundTruthDocument
from experiments.ui_state_extraction.services.unit_matching_service import (
    match_all_units,
    required_input_mapping_explain,
)


EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION = "experiment_pipeline_debug_v1"
_INVALID_REF_PREVIEW_LIMIT = 20


def new_debug_log_path(log_dir: Path, *, run_prefix: str = "experiment_debug") -> Path:
    """Path to a new JSONL file for one CLI run (UTC timestamp in filename)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return log_dir / f"{run_prefix}_{ts}.jsonl"


def append_jsonl_line(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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
) -> None:
    """Append one module-3 line: metrics heads + intent required_input explain (needs rematch)."""
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
            "step_grounding_accuracy": per_image.intent_metrics.step_grounding_accuracy,
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
    }
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
