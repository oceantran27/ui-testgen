"""Dedupe judge mappings, per-screen and micro Recall / Precision / F1."""

from __future__ import annotations

from experiments.intent_coverage_judge.schemas import EvaluationResult, IntentMapping


def dedupe_mappings_by_generated(
    mappings: list[IntentMapping],
) -> tuple[list[IntentMapping], list[str]]:
    """
    Align judge output with strict 1:1 pairing (each ``generated_id`` and each
    ``ground_truth_id`` at most once; see judge prompt §5). First mapping wins
    in API order; dropped rows produce warnings.
    """
    seen_gen: set[str] = set()
    seen_gt: set[str] = set()
    out: list[IntentMapping] = []
    warnings: list[str] = []
    for m in mappings:
        if m.generated_id in seen_gen:
            warnings.append(f"duplicate generated_id dropped: {m.generated_id}")
            continue
        if m.ground_truth_id in seen_gt:
            warnings.append(
                f"dropped mapping {m.generated_id!r} -> {m.ground_truth_id!r}: "
                "ground_truth_id already mapped (1:1)"
            )
            continue
        seen_gen.add(m.generated_id)
        seen_gt.add(m.ground_truth_id)
        out.append(m)
    return out, warnings


def per_screen_mapping_sets(
    deduped: list[IntentMapping],
    gt_ids: set[str],
    gen_ids: set[str],
) -> tuple[set[str], set[str], list[str]]:
    """
    Distinct GT ids covered and generated ids mapped (valid id references only).

    Returns (covered_gt_ids, mapped_gen_ids, validation_warnings).
    """
    warnings: list[str] = []
    for m in deduped:
        if m.generated_id not in gen_ids:
            warnings.append(f"mapping references unknown generated_id: {m.generated_id}")
        if m.ground_truth_id not in gt_ids:
            warnings.append(f"mapping references unknown ground_truth_id: {m.ground_truth_id}")

    valid = [
        m
        for m in deduped
        if m.generated_id in gen_ids and m.ground_truth_id in gt_ids
    ]
    covered = {m.ground_truth_id for m in valid}
    mapped = {m.generated_id for m in valid}
    return covered, mapped, warnings


def per_screen_mapping_counts(
    deduped: list[IntentMapping],
    gt_ids: set[str],
    gen_ids: set[str],
) -> tuple[int, int, list[str]]:
    covered, mapped, w = per_screen_mapping_sets(deduped, gt_ids, gen_ids)
    return len(covered), len(mapped), w


def judge_lists_consistency_warnings(
    result: EvaluationResult,
    gt_ids: set[str],
    gen_ids: set[str],
    covered_gt_ids: set[str],
    mapped_gen_ids: set[str],
) -> list[str]:
    """Warn if judge missing/extra lists disagree with mapping-derived sets."""
    w: list[str] = []
    computed_missing = set(gt_ids) - covered_gt_ids
    judge_missing = set(result.missing_ground_truth_ids)
    if judge_missing != computed_missing:
        w.append(
            "judge missing_ground_truth_ids differs from mappings-derived missing: "
            f"judge_only={sorted(judge_missing - computed_missing)} "
            f"computed_only={sorted(computed_missing - judge_missing)}"
        )
    computed_extra = set(gen_ids) - mapped_gen_ids
    judge_extra = set(result.extra_generated_ids)
    if judge_extra != computed_extra:
        w.append(
            "judge extra_generated_ids differs from mappings-derived extras: "
            f"judge_only={sorted(judge_extra - computed_extra)} "
            f"computed_only={sorted(computed_extra - judge_extra)}"
        )
    return w


def recall_precision_f1(
    covered_gt: int,
    n_gt: int,
    mapped_gen: int,
    n_gen: int,
) -> tuple[float | None, float | None, float | None]:
    """Per-screen metrics; None if denominator zero."""
    recall = covered_gt / n_gt if n_gt > 0 else None
    precision = mapped_gen / n_gen if n_gen > 0 else None
    f1: float | None
    if recall is None or precision is None:
        f1 = None
    elif recall + precision == 0:
        f1 = 0.0
    else:
        f1 = 2 * recall * precision / (recall + precision)
    return recall, precision, f1


def micro_recall_precision_f1(
    screen_rows: list[tuple[int, int, int, int]],
) -> tuple[float | None, float | None, float | None]:
    """
    Dataset-level micro metrics.

    Each tuple is ``(n_gt, n_gen, covered_gt, mapped_gen)`` for one screen.

    Recall denominator: sum of ``n_gt`` over screens with ``n_gt > 0``.
    Precision denominator: sum of ``n_gen`` over screens with ``n_gen > 0``.
    """
    sum_gt = sum(n_gt for n_gt, _, _, _ in screen_rows if n_gt > 0)
    sum_covered = sum(cv for n_gt, _, cv, _ in screen_rows if n_gt > 0)
    sum_gen = sum(ng for _, ng, _, _ in screen_rows if ng > 0)
    sum_mapped = sum(mg for _, ng, _, mg in screen_rows if ng > 0)
    recall = sum_covered / sum_gt if sum_gt > 0 else None
    precision = sum_mapped / sum_gen if sum_gen > 0 else None
    if recall is None or precision is None:
        f1 = None
    elif recall + precision == 0:
        f1 = 0.0
    else:
        f1 = 2 * recall * precision / (recall + precision)
    return recall, precision, f1
