"""Write JSON, CSV, and Markdown evaluation reports (module 3)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from experiments.ui_state_extraction.schemas.evaluation_metric_schema import (
    AggregateMetrics,
    AggregateMetricsV4,
    DatasetSummary,
    DiagnosticMetrics,
    EvaluationSummaryDocument,
)
from experiments.ui_state_extraction.schemas.evaluation_result_schema import PerImageEvaluationResult

SPRINT10_PER_IMAGE_CSV_HEADER: list[str] = [
    "image_id",
    "screen_type_accuracy",
    "presentation_scope_accuracy",
    "outcome_state_type_accuracy",
    "screen_enum_accuracy",
    "element_precision",
    "element_recall",
    "element_f1",
    "element_correct_count",
    "element_pred_count",
    "element_gt_count",
    "action_precision",
    "action_recall",
    "action_f1",
    "action_correct_count",
    "action_pred_count",
    "action_gt_count",
    "feedback_precision",
    "feedback_recall",
    "feedback_f1",
    "feedback_correct_count",
    "feedback_pred_count",
    "feedback_gt_count",
    "intent_precision",
    "intent_recall",
    "intent_f1",
    "intent_correct_count",
    "intent_pred_count",
    "intent_gt_count",
    "skipped_empty_key_element_count",
    "skipped_empty_key_action_count",
    "skipped_empty_key_feedback_count",
    "intent_key_missing_count",
]


def _screen_bool_to_accuracy(value: Optional[bool]) -> Optional[float]:
    if value is None:
        return None
    return 1.0 if value else 0.0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def aggregate_metrics_v4_from_flat_dict(data: dict[str, float | None]) -> AggregateMetricsV4:
    """Populate Sprint 8 summary aggregate_metrics / aggregate_metrics_macro blocks."""
    fields = set(AggregateMetricsV4.model_fields.keys())
    return AggregateMetricsV4(**{k: v for k, v in data.items() if k in fields})


def aggregate_metrics_from_flat_dict(data: dict[str, float | None]) -> AggregateMetrics:
    """Populate DiagnosticMetrics from legacy flat keys (alias: AggregateMetrics)."""
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
    diagnostic: DiagnosticMetrics | None = None,
) -> None:
    doc = EvaluationSummaryDocument(
        schema_version=schema_version,
        dataset_summary=dataset_summary,
        aggregate_metrics=aggregate_metrics_v4_from_flat_dict(micro),
        aggregate_metrics_macro=aggregate_metrics_v4_from_flat_dict(macro),
        diagnostic_metrics=diagnostic,
        skipped_items=skipped_items,
    )
    _write_json(path, doc.model_dump(mode="json"))


def metrics_summary_csv_rows(
    micro: dict[str, float | None],
    macro: dict[str, float | None],
    *,
    count: int,
    diagnostic: dict[str, Any] | None = None,
) -> list[list[Any]]:
    diag = diagnostic or {}
    rows: list[list[Any]] = [
        ["metric_name", "aggregate_micro_v4", "aggregate_macro_v4", "diagnostic_micro_legacy", "count", "notes"],
    ]
    keys = sorted(set(micro.keys()) | set(macro.keys()) | set(diag.keys()))
    for name in keys:
        rows.append([name, micro.get(name), macro.get(name), diag.get(name), count, ""])
    return rows


def write_csv(path: Path, rows: Iterable[Iterable[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)


def per_image_csv_rows(results: list[PerImageEvaluationResult]) -> list[list[Any]]:
    """Sprint 10: one row per image, main UI-unit metrics and key-skip diagnostics only."""
    out: list[list[Any]] = [list(SPRINT10_PER_IMAGE_CSV_HEADER)]
    for r in results:
        sm = r.screen_metrics
        em = r.element_metrics
        am = r.action_metrics
        fm = r.feedback_metrics
        im = r.intent_metrics
        kd = r.key_diagnostics
        out.append(
            [
                r.image_id,
                _screen_bool_to_accuracy(sm.screen_type_match),
                _screen_bool_to_accuracy(sm.presentation_scope_match),
                _screen_bool_to_accuracy(sm.outcome_state_type_match),
                sm.accuracy,
                em.precision,
                em.recall,
                em.f1,
                em.text_grounded_matched_count,
                em.text_grounded_pred_count,
                em.text_grounded_gt_count,
                am.precision,
                am.recall,
                am.f1,
                am.matched_count,
                am.pred_count,
                am.gt_count,
                fm.precision,
                fm.recall,
                fm.f1,
                fm.matched_count,
                fm.pred_count,
                fm.gt_count,
                im.precision,
                im.recall,
                im.f1,
                im.matched_count,
                im.pred_count,
                im.gt_count,
                kd.skipped_empty_key_element_count,
                kd.skipped_empty_key_action_count,
                kd.skipped_empty_key_feedback_count,
                kd.intent_key_missing_count,
            ]
        )
    return out


def _fmt_metric_val(v: float | None, *, counts: bool = False) -> str:
    if v is None:
        return ""
    if counts:
        return str(int(round(float(v))))
    return f"{float(v):.4f}"


def write_markdown_report(
    path: Path,
    *,
    dataset_summary: DatasetSummary,
    micro: dict[str, float | None],
    macro: dict[str, float | None] | None = None,
    results: list[PerImageEvaluationResult] | None = None,
) -> None:
    """Sprint 10: eight sections; dataset-level aggregates only (no long auxiliary metric tables)."""
    lines = [
        "# UI State Extraction Evaluation Report",
        "",
        "## 1. Dataset summary",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Raw outputs | {dataset_summary.total_raw_outputs} |",
        f"| Ground truth files | {dataset_summary.total_ground_truth_files} |",
        f"| Evaluated pairs | {dataset_summary.total_evaluated} |",
        f"| Skipped | {dataset_summary.total_skipped} |",
        "",
    ]
    reasons = dataset_summary.skip_reasons or {}
    if reasons:
        lines.extend(["### Skip reasons", "", "| Reason | Count |", "|---|---:|"])
        for reason, cnt in sorted(reasons.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"| {reason} | {cnt} |")
        lines.append("")

    use_macro = macro is not None

    def row_screen(label: str, micro_key: str) -> str:
        mv = _fmt_metric_val(micro.get(micro_key))
        if not use_macro:
            return f"| {label} | {mv} |"
        mac = _fmt_metric_val(macro.get(micro_key) if macro else None)
        return f"| {label} | {mv} | {mac} |"

    lines.extend(
        [
            "## 2. Screen classification results",
            "",
        ]
    )
    if use_macro:
        lines.extend(["| Metric | Micro (dataset) | Macro (mean / image) |", "|---|---:|---:|"])
    else:
        lines.extend(["| Metric | Micro (dataset) |", "|---|---:|"])

    screen_labels = [
        ("Screen type accuracy", "screen_type_accuracy"),
        ("Presentation scope accuracy", "presentation_scope_accuracy"),
        ("Outcome state type accuracy", "outcome_state_type_accuracy"),
        ("Screen enum accuracy (mean of three)", "screen_enum_accuracy"),
    ]
    for label, key in screen_labels:
        lines.append(row_screen(label, key))
    lines.append("")

    def prf_count_block(title: str, prefix: str) -> None:
        lines.extend([f"## {title}", ""])
        if use_macro:
            lines.extend(
                [
                    "| Metric | Micro (dataset) | Macro (mean / image) |",
                    "|---|---:|---:|",
                ]
            )
        else:
            lines.extend(["| Metric | Micro (dataset) |", "|---|---:|"])

        def pair(label: str, key: str, *, counts: bool = False) -> None:
            mv = _fmt_metric_val(micro.get(key), counts=counts)
            if use_macro:
                mac = _fmt_metric_val(macro.get(key) if macro else None, counts=counts)
                lines.append(f"| {label} | {mv} | {mac} |")
            else:
                lines.append(f"| {label} | {mv} |")

        pair("Precision", f"{prefix}_precision")
        pair("Recall", f"{prefix}_recall")
        pair("F1", f"{prefix}_f1")
        pair("Correct count", f"{prefix}_correct_count", counts=True)
        pair("Pred count", f"{prefix}_pred_count", counts=True)
        pair("GT count", f"{prefix}_gt_count", counts=True)
        lines.append("")

    prf_count_block("3. Element extraction results", "element")
    prf_count_block("4. Action extraction results", "action")
    prf_count_block("5. Feedback extraction results", "feedback")
    prf_count_block("6. Intent inference results", "intent")

    lines.extend(
        [
            "## 7. Diagnostics: skipped/missing keys",
            "",
            "Counts aggregate multiset evaluation-key skips (pred-side empty keys; intent column includes pred + GT misses).",
            "",
        ]
    )
    rs = results or []
    tot_el = sum(r.key_diagnostics.skipped_empty_key_element_count for r in rs)
    tot_ac = sum(r.key_diagnostics.skipped_empty_key_action_count for r in rs)
    tot_fb = sum(r.key_diagnostics.skipped_empty_key_feedback_count for r in rs)
    tot_int = sum(r.key_diagnostics.intent_key_missing_count for r in rs)
    lines.extend(
        [
            "| Diagnostic | Dataset total |",
            "|---|---:|",
            f"| Skipped empty-key elements (pred) | {tot_el} |",
            f"| Skipped empty-key actions (pred) | {tot_ac} |",
            f"| Skipped empty-key feedback (pred) | {tot_fb} |",
            f"| Intent key missing (pred + GT) | {tot_int} |",
            "",
        ]
    )
    scored = sorted(
        rs,
        key=lambda r: (
            r.key_diagnostics.skipped_empty_key_element_count
            + r.key_diagnostics.skipped_empty_key_action_count
            + r.key_diagnostics.skipped_empty_key_feedback_count
            + r.key_diagnostics.intent_key_missing_count
        ),
        reverse=True,
    )
    flagged = [
        r
        for r in scored
        if (
            r.key_diagnostics.skipped_empty_key_element_count
            + r.key_diagnostics.skipped_empty_key_action_count
            + r.key_diagnostics.skipped_empty_key_feedback_count
            + r.key_diagnostics.intent_key_missing_count
        )
        > 0
    ][:10]
    if flagged:
        lines.extend(["### Images with non-zero key skips (top 10)", "", "| image_id | Sum of skip counts |", "|---|---:|"])
        for r in flagged:
            s = (
                r.key_diagnostics.skipped_empty_key_element_count
                + r.key_diagnostics.skipped_empty_key_action_count
                + r.key_diagnostics.skipped_empty_key_feedback_count
                + r.key_diagnostics.intent_key_missing_count
            )
            lines.append(f"| {r.image_id} | {s} |")
        lines.append("")

    lines.extend(
        [
            "## 8. Notes and limitations",
            "",
            "- **Summary v4 (micro):** Pooled precision/recall/F1 use summed matched / pred / GT counts across images. Screen accuracies are mean per-image over three taxonomy fields (**domain** excluded).",
            "- **Element counts** follow **text-grounded** denominators (evaluable label keys); see `evaluation_per_image.json` for full per-image blocks.",
            "- **Auxiliary metrics** (interaction groups, ID grounding, intent sub-multisets, reference consistency) are not listed here; see `evaluation_summary.json` → `diagnostic_metrics` and optional pipeline JSONL debug logs.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
