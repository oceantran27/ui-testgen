"""Write JSON, CSV, and Markdown evaluation reports (module 3)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from experiments.ui_state_extraction.schemas.evaluation_metric_schema import (
    AggregateMetrics,
    DatasetSummary,
    EvaluationSummaryDocument,
)
from experiments.ui_state_extraction.schemas.evaluation_result_schema import PerImageEvaluationResult


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def aggregate_metrics_from_flat_dict(data: dict[str, float | None]) -> AggregateMetrics:
    """Populate AggregateMetrics from micro/macro flat keys; ignore unknown keys."""
    fields = set(AggregateMetrics.model_fields.keys())
    return AggregateMetrics(**{k: v for k, v in data.items() if k in fields})


def write_per_image_json(path: Path, results: list[PerImageEvaluationResult]) -> None:
    body = [r.model_dump(mode="json") for r in results]
    _write_json(path, body)


def write_evaluation_summary_json(
    path: Path,
    *,
    schema_version: str,
    dataset_summary: DatasetSummary,
    micro: dict[str, float | None],
    macro: dict[str, float | None],
    skipped_items: list[dict[str, Any]],
) -> None:
    doc = EvaluationSummaryDocument(
        schema_version=schema_version,
        dataset_summary=dataset_summary,
        aggregate_metrics=aggregate_metrics_from_flat_dict(micro),
        aggregate_metrics_macro=aggregate_metrics_from_flat_dict(macro),
        skipped_items=skipped_items,
    )
    _write_json(path, doc.model_dump(mode="json"))


def metrics_summary_csv_rows(
    micro: dict[str, float | None],
    macro: dict[str, float | None],
    *,
    count: int,
) -> list[list[Any]]:
    rows: list[list[Any]] = [["metric_name", "micro_value", "macro_value", "count", "notes"]]
    keys = sorted(set(micro.keys()) | set(macro.keys()))
    for name in keys:
        rows.append([name, micro.get(name), macro.get(name), count, ""])
    return rows


def write_csv(path: Path, rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)


def per_image_csv_rows(results: list[PerImageEvaluationResult]) -> list[list[Any]]:
    header = [
        "image_id",
        "relative_path",
        "screen_enum_accuracy",
        "element_precision",
        "element_recall",
        "element_f1",
        "element_type_accuracy",
        "role_hint_accuracy",
        "pred_empty_anchor_element_count",
        "gt_empty_anchor_element_count",
        "empty_anchor_element_delta",
        "pred_empty_anchor_element_rate",
        "gt_empty_anchor_element_rate",
        "text_grounded_pred_count",
        "text_grounded_gt_count",
        "text_grounded_matched_count",
        "action_precision",
        "action_recall",
        "action_f1",
        "action_type_accuracy",
        "action_grounding_accuracy",
        "feedback_precision",
        "feedback_recall",
        "feedback_f1",
        "feedback_type_accuracy",
        "group_precision",
        "group_recall",
        "group_f1",
        "group_membership_f1",
        "group_primary_action_accuracy",
        "intent_precision",
        "intent_recall",
        "intent_f1",
        "intent_kind_accuracy",
        "commit_action_accuracy",
        "required_input_f1",
        "evidence_target_f1",
        "invalid_reference_rate",
        "hallucination_rate",
    ]
    out: list[list[Any]] = [header]
    for r in results:
        em = r.element_metrics
        am = r.action_metrics
        fm = r.feedback_metrics
        gm = r.group_metrics
        im = r.intent_metrics
        cm = r.consistency_metrics
        out.append(
            [
                r.image_id,
                r.relative_path,
                r.screen_metrics.accuracy,
                em.precision,
                em.recall,
                em.f1,
                em.element_type_accuracy,
                em.role_hint_accuracy,
                em.pred_empty_anchor_element_count,
                em.gt_empty_anchor_element_count,
                em.empty_anchor_element_delta,
                em.pred_empty_anchor_element_rate,
                em.gt_empty_anchor_element_rate,
                em.text_grounded_pred_count,
                em.text_grounded_gt_count,
                em.text_grounded_matched_count,
                am.precision,
                am.recall,
                am.f1,
                am.action_type_accuracy,
                am.action_grounding_accuracy,
                fm.precision,
                fm.recall,
                fm.f1,
                fm.feedback_type_accuracy,
                gm.precision,
                gm.recall,
                gm.f1,
                gm.group_membership_f1,
                gm.primary_action_accuracy,
                im.precision,
                im.recall,
                im.f1,
                im.intent_kind_accuracy,
                im.intent_commit_action_accuracy,
                im.required_input_f1,
                im.evidence_target_f1,
                cm.invalid_reference_rate,
                cm.hallucination_rate,
            ]
        )
    return out


def category_metric_csv_rows(
    category: str,
    results: list[PerImageEvaluationResult],
) -> list[list[Any]]:
    """One row per image with key metrics for a category (for thesis tables)."""
    if category == "element":
        header = [
            "image_id",
            "precision",
            "recall",
            "f1",
            "type_acc",
            "role_acc",
            "region_acc",
            "pred_empty_n",
            "gt_empty_n",
            "pred_empty_rate",
        ]
        rows = [header]
        for r in results:
            m = r.element_metrics
            rows.append(
                [
                    r.image_id,
                    m.precision,
                    m.recall,
                    m.f1,
                    m.element_type_accuracy,
                    m.role_hint_accuracy,
                    m.visual_region_accuracy,
                    m.pred_empty_anchor_element_count,
                    m.gt_empty_anchor_element_count,
                    m.pred_empty_anchor_element_rate,
                ]
            )
    elif category == "action":
        header = ["image_id", "precision", "recall", "f1", "type_acc", "ground_acc", "region_acc"]
        rows = [header]
        for r in results:
            m = r.action_metrics
            rows.append(
                [
                    r.image_id,
                    m.precision,
                    m.recall,
                    m.f1,
                    m.action_type_accuracy,
                    m.action_grounding_accuracy,
                    m.action_region_accuracy,
                ]
            )
    elif category == "feedback":
        header = ["image_id", "precision", "recall", "f1", "type_acc", "related_el_acc"]
        rows = [header]
        for r in results:
            m = r.feedback_metrics
            rows.append(
                [
                    r.image_id,
                    m.precision,
                    m.recall,
                    m.f1,
                    m.feedback_type_accuracy,
                    m.feedback_related_element_accuracy,
                ]
            )
    elif category == "group":
        header = ["image_id", "precision", "recall", "f1", "membership_f1", "type_acc", "primary_acc"]
        rows = [header]
        for r in results:
            m = r.group_metrics
            rows.append(
                [
                    r.image_id,
                    m.precision,
                    m.recall,
                    m.f1,
                    m.group_membership_f1,
                    m.group_type_accuracy,
                    m.primary_action_accuracy,
                ]
            )
    elif category == "intent":
        header = [
            "image_id",
            "precision",
            "recall",
            "f1",
            "kind_acc",
            "commit_acc",
            "req_input_f1",
            "evidence_f1",
            "step_acc",
        ]
        rows = [header]
        for r in results:
            m = r.intent_metrics
            rows.append(
                [
                    r.image_id,
                    m.precision,
                    m.recall,
                    m.f1,
                    m.intent_kind_accuracy,
                    m.intent_commit_action_accuracy,
                    m.required_input_f1,
                    m.evidence_target_f1,
                    m.step_grounding_accuracy,
                ]
            )
    else:
        rows = [["error", f"unknown category {category}"]]
    return rows


def write_markdown_report(
    path: Path,
    *,
    dataset_summary: DatasetSummary,
    micro: dict[str, float | None],
) -> None:
    lines = [
        "# UI State Extraction Evaluation Report",
        "",
        "## Dataset Summary",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Raw outputs | {dataset_summary.total_raw_outputs} |",
        f"| Ground truth files | {dataset_summary.total_ground_truth_files} |",
        f"| Evaluated pairs | {dataset_summary.total_evaluated} |",
        f"| Skipped | {dataset_summary.total_skipped} |",
        "",
        "## Main Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]

    def pick(key: str) -> str:
        v = micro.get(key)
        if v is None:
            return ""
        return f"{float(v):.4f}"

    pairs = [
        ("Screen enum accuracy", "screen_enum_accuracy"),
        ("Element F1 (text-grounded only)", "element_f1"),
        ("Pred empty-anchor element rate", "pred_empty_anchor_element_rate"),
        ("GT empty-anchor element rate", "gt_empty_anchor_element_rate"),
        ("Action F1", "action_f1"),
        ("Action grounding accuracy", "action_grounding_accuracy"),
        ("Feedback F1", "feedback_f1"),
        ("Group membership F1", "group_membership_f1"),
        ("Intent F1", "intent_f1"),
        ("Commit action accuracy", "commit_action_accuracy"),
        ("Required input F1", "required_input_f1"),
        ("Evidence target F1", "evidence_target_f1"),
        ("Invalid reference rate", "invalid_reference_rate"),
        ("Hallucination rate", "hallucination_rate"),
    ]
    for label, key in pairs:
        lines.append(f"| {label} | {pick(key)} |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Element precision / recall / F1 count only **text-grounded** elements (non-empty anchors after normalization). Empty-anchor elements are reported separately (counts and rates).",
            "- Required-input / evidence / step grounding / group membership / feedback `related_element_ids` metrics use only **text-grounded** GT element references. References to empty-anchor elements are excluded from F1/accuracy and summarized as `*_empty_anchor_excluded_*` counts in per-image results and aggregates.",
            "- Action grounding accuracy includes only matched actions whose GT `grounded_element_id` is absent or points to a text-grounded element (empty-anchor targets are excluded from the denominator).",
            "- Free-text fields such as `intent_name`, `local_user_goal`, `group_label` are not evaluated.",
            "- No-label icons and ungrounded visual controls are excluded from the dataset.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
