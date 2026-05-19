"""Pure helpers for conversion_report review priority and severity hints (module 2)."""

from __future__ import annotations

from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
    ConversionReport,
    TempGroundTruthDocument,
)


_HIGH_FLAG_PREFIXES: tuple[str, ...] = (
    "element_anchor_text_empty:",
    "feedback_anchor_text_empty:",
    "action_grounding_not_found:",
    "group_invalid_element_ref",
    "group_invalid_action_ref",
    "group_invalid_feedback_ref",
    "group_primary_action_not_in_group",
    "orphan_element",
    "orphan_action",
    "orphan_feedback",
    "multi_group_element",
    "multi_group_action",
    "multi_group_feedback",
    "evidence_ref_invalid",
)

_MEDIUM_FLAG_PREFIXES: tuple[str, ...] = (
    "multiple_sequence_templates_review_needed:",
    "outcome_prediction_allowed_not_false",
    "non_text_label_skipped:",
)


def _flag_severity(flag: str) -> str | None:
    for p in _HIGH_FLAG_PREFIXES:
        if flag == p or flag.startswith(p):
            return "high"
    for p in _MEDIUM_FLAG_PREFIXES:
        if flag == p or flag.startswith(p):
            return "medium"
    return None


def compute_review_priority(
    report: ConversionReport,
    *,
    unresolved_group_count: int = 0,
) -> str:
    """Spec §8: high / medium / low from invalid refs, flags, warnings."""
    if report.invalid_references:
        return "high"
    for f in report.auto_flags:
        if _flag_severity(f) == "high":
            return "high"
    for w in report.warnings:
        if w.startswith("action_grounding_not_found:") or "invalid" in w.lower():
            return "high"
    for f in report.auto_flags:
        if _flag_severity(f) == "medium":
            return "medium"
    if report.warnings:
        return "medium"
    if unresolved_group_count >= 2:
        return "medium"
    return "low"


def sync_conversion_counts(doc: TempGroundTruthDocument) -> None:
    """Fill conversion_report.counts from list lengths."""
    c = doc.conversion_report.counts
    c.elements = len(doc.elements)
    c.actions = len(doc.actions)
    c.feedback = len(doc.feedback)
    c.groups = len(doc.groups)
    c.screen_intents = len(doc.screen_intents)
    c.unresolved_groups = len(doc.unresolved_groups)
