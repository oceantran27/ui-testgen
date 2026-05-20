"""Write ``evaluation_report.md``, ``evaluation_summary.csv``, and batch CSV summaries."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, List, MutableMapping, Tuple, Union

from experiments.flow_discovery.schemas.evaluation_schema import EvaluationResult, TransitionMatchItem

CSV_HEADER_ROW: Tuple[str, ...] = (
    "app_id",
    "run_id",
    "ok",
    "error",
    "strict_precision",
    "strict_recall",
    "strict_f1",
    "relaxed_precision",
    "relaxed_recall",
    "relaxed_f1",
    "flow_membership_macro_f1",
    "ordering_accuracy",
    "branch_precision",
    "branch_recall",
    "branch_f1",
    "invalid_transition_count",
    "invalid_flow_rate",
)


def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def _float_cell(v: Any) -> str:
    if v is None:
        return ""
    try:
        return f"{float(v):.6f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _counts_from_result(result: EvaluationResult) -> Tuple[MutableMapping[str, Any], MutableMapping[str, Any]]:
    extras = getattr(result, "extras", {}) or {}
    counts = extras.get("transition_counts") or {}
    strict = counts.get("strict") or {}
    relaxed = counts.get("relaxed") or {}
    return strict, relaxed


def _section_metrics(lines: List[str], result: EvaluationResult) -> None:
    m = result.metrics
    tm = m.transition_metrics
    lines.extend(
        [
            "## Metrics",
            "",
            "### Transitions",
            "",
            _md_table(
                ["Mode", "Precision", "Recall", "F1"],
                [
                    [
                        "strict",
                        _float_cell(tm.strict_precision),
                        _float_cell(tm.strict_recall),
                        _float_cell(tm.strict_f1),
                    ],
                    [
                        "relaxed",
                        _float_cell(tm.relaxed_precision),
                        _float_cell(tm.relaxed_recall),
                        _float_cell(tm.relaxed_f1),
                    ],
                ],
            ),
            "",
            "### Flows",
            "",
        ],
    )
    fm = m.flow_metrics
    lines.append(
        _md_table(
            ["Metric", "Value"],
            [
                ["membership_macro_f1", _float_cell(fm.membership_macro_f1)],
                ["ordering_accuracy", _float_cell(fm.ordering_accuracy)],
            ],
        ),
    )
    lines.extend(["", "### Branches", ""])
    bm = m.branch_metrics
    lines.append(
        _md_table(
            ["Metric", "Value"],
            [
                ["branch_precision", _float_cell(bm.branch_precision)],
                ["branch_recall", _float_cell(bm.branch_recall)],
                ["branch_f1", _float_cell(bm.branch_f1)],
            ],
        ),
    )
    lines.extend(["", "### Errors", ""])
    em = m.error_metrics
    lines.append(
        _md_table(
            ["Metric", "Value"],
            [
                ["invalid_transition_count", str(em.invalid_transition_count)],
                ["invalid_flow_rate", _float_cell(em.invalid_flow_rate or 0.0)],
            ],
        ),
    )


def _section_transition_confusion(lines: List[str], result: EvaluationResult) -> None:
    strict_counts, relaxed_counts = _counts_from_result(result)

    rows_s = [["strict", strict_counts.get("tp", "?"), strict_counts.get("fp", "?"), strict_counts.get("fn", "?")]]
    rows_r = [["relaxed", relaxed_counts.get("tp", "?"), relaxed_counts.get("fp", "?"), relaxed_counts.get("fn", "?")]]
    blocks = [_md_table(["Mode", "TP", "FP", "FN"], rows_s), _md_table(["Mode", "TP", "FP", "FN"], rows_r)]

    lines.extend(["", "## Transition Confusion", ""])
    lines.extend([blocks[0], "", blocks[1]])
    lines.extend(["", "### Sample ambiguous strict pairs", ""])
    rows: List[List[str]] = []
    for it in result.transition_items[:20]:
        if it.match_status not in ("false_positive", "false_negative", "true_positive"):
            continue
        rows.append(
            [
                it.pred_transition_id or "",
                it.gt_transition_id or "",
                it.match_status,
                it.match_mode or "",
                ",".join(it.error_tags or []),
            ],
        )
    lines.append(rows and _md_table(["pred_id", "gt_id", "status", "mode", "error_tags"], rows) or "_None._")


def _section_branch_detection(lines: List[str], result: EvaluationResult) -> None:
    lines.extend(["", "## Branch Detection", ""])
    rows: List[List[str]] = []
    for bi in result.branch_items:
        rows.append(
            [
                bi.branch_key[:80] + ("…" if len(bi.branch_key) > 80 else ""),
                bi.gt_branch_group_id or "",
                bi.pred_semantic_cluster_id or "",
                bi.match_status,
                ",".join(bi.error_tags or []),
            ],
        )
    lines.append(
        rows
        and _md_table(["branch_key", "gt_branch_group_id", "pred_cluster", "match_status", "error_tags"], rows)
        or "_No branch evaluation rows._",
    )


def _section_ordering(lines: List[str], result: EvaluationResult) -> None:
    lines.extend(["", "## Ordering", ""])
    slices_any = ((getattr(result, "extras", None) or {}).get("flow_order_slices") or [])
    slices: List[MutableMapping[str, Any]] = [dict(x) for x in slices_any] if slices_any else []
    rows: List[List[str]] = []
    if slices:
        for sl in slices:
            gt_o = ",".join(str(x) for x in (sl.get("gt_ordered_state_ids") or []) if x)
            pr_o = ",".join(str(x) for x in (sl.get("pred_ordered_state_ids") or []) if x)
            rows.append(
                [
                    str(sl.get("gt_flow_id") or ""),
                    str(sl.get("source_flow_id") or ""),
                    _float_cell(sl.get("ordering_accuracy")),
                    str(sl.get("ordering_errors") or "0"),
                    gt_o + " vs " + pr_o if (gt_o or pr_o) else _float_cell(sl.get("membership_f1")),
                ],
            )
    else:
        for fi in result.flow_items:
            rows.append(
                [
                    fi.gt_flow_id or "",
                    fi.pred_flow_id or "",
                    _float_cell(fi.ordering_accuracy),
                    str(fi.ordering_errors),
                    _float_cell(fi.membership_f1),
                ],
            )
    headers = ["gt_flow_id", "source_flow_id", "ordering_accuracy", "ordering_errors", "gt_vs_pred_order"]
    lines.append(rows and _md_table(headers, rows) or "_No flow ordering rows._")


def _section_error_breakdown(lines: List[str], result: EvaluationResult) -> None:
    lines.extend(["", "## Error Breakdown", ""])
    if result.error_breakdown:
        eb = sorted(result.error_breakdown.items(), key=lambda kv: kv[0])
        lines.append(_md_table(["Tag", "Count"], [[k, v] for k, v in eb]))
    else:
        lines.append("_No aggregate error tags._")


def _section_false_positives_negatives(lines: List[str], result: EvaluationResult) -> None:
    fps = [i for i in result.transition_items if i.match_status == "false_positive"]
    fns = [i for i in result.transition_items if i.match_status == "false_negative"]

    lines.extend(["", "## False Positives", ""])
    rows = [[x.pred_transition_id or "", ",".join(x.error_tags)] for x in fps[:48]]
    lines.append(rows and _md_table(["pred_transition_id", "error_tags"], rows) or "_None._")

    lines.extend(["", "## False Negatives", ""])
    rows2 = [[x.gt_transition_id or "", ",".join(x.error_tags)] for x in fns[:48]]
    lines.append(rows2 and _md_table(["gt_transition_id", "error_tags"], rows2) or "_None._")


def write_evaluation_report(path: Path, result: EvaluationResult, *, sample_limit: int = 12) -> None:
    lines: List[str] = [
        f"# Flow Discovery Evaluation — {result.app_id}",
        "",
        f"- **run_id:** `{result.run_id or ''}`",
        "",
    ]
    _section_metrics(lines, result)
    _section_transition_confusion(lines, result)
    _section_branch_detection(lines, result)
    _section_ordering(lines, result)
    _section_error_breakdown(lines, result)
    _section_false_positives_negatives(lines, result)

    lines.extend(["", "## Sample transition verdicts (strict)", ""])
    samples: List[TransitionMatchItem] = []
    for it in result.transition_items:
        if len(samples) >= sample_limit:
            break
        if it.match_status in ("false_positive", "false_negative", "true_positive"):
            samples.append(it)
    lines.append(samples and _md_table(
        ["pred_id", "gt_id", "status", "mode", "error_tags"],
        [[s.pred_transition_id or "", s.gt_transition_id or "", s.match_status, s.match_mode or "", ",".join(s.error_tags)] for s in samples],
    ) or "_None._")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluation_csv_row_success(result: EvaluationResult) -> List[Any]:
    m = result.metrics
    tm = m.transition_metrics
    fm = m.flow_metrics
    bm = m.branch_metrics
    em = m.error_metrics
    return [
        result.app_id,
        result.run_id or "",
        "true",
        "",
        tm.strict_precision,
        tm.strict_recall,
        tm.strict_f1,
        tm.relaxed_precision,
        tm.relaxed_recall,
        tm.relaxed_f1,
        fm.membership_macro_f1,
        fm.ordering_accuracy,
        bm.branch_precision,
        bm.branch_recall,
        bm.branch_f1,
        em.invalid_transition_count,
        em.invalid_flow_rate,
    ]


def evaluation_csv_row_failure(*, app_id: str, run_id: str, error_message: str) -> List[Any]:
    return [
        app_id,
        run_id or "",
        "false",
        error_message,
        *[""] * 13,
    ]


def write_evaluation_summary_csv(path: Path, result: EvaluationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(CSV_HEADER_ROW))
        w.writerow(evaluation_csv_row_success(result))


BatchCsvEntry = Union[EvaluationResult, Tuple[str, str, str]]


def write_batch_summary_csv(path: Path, rows: Iterable[BatchCsvEntry]) -> None:
    """Write aggregated batch metrics. Rows are ``EvaluationResult`` or ``(app_id, run_id, error)`` tuples."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(CSV_HEADER_ROW))
        for row in rows:
            if isinstance(row, tuple):
                app_id, run_id, err = row
                w.writerow(evaluation_csv_row_failure(app_id=app_id, run_id=run_id, error_message=err))
            else:
                w.writerow(evaluation_csv_row_success(row))


__all__ = [
    "BatchCsvEntry",
    "CSV_HEADER_ROW",
    "evaluation_csv_row_failure",
    "evaluation_csv_row_success",
    "write_batch_summary_csv",
    "write_evaluation_report",
    "write_evaluation_summary_csv",
]
