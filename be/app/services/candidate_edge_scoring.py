"""Layer 2 numeric scoring for candidate edges (0–100 scale)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from app.constants.edge_taxonomy import (
    EMPTY_OUTCOME_TYPES,
    GENERIC_GLOBAL_NAV_SCREEN_TYPES,
    NEGATIVE_OUTCOME_TYPES,
    transition_pair_allowed,
    transition_pair_bonus_eligible,
)


@dataclass
class ScoreResult:
    value: int
    reasons: List[str]
    risk_flags: List[str]


def _clamp_score(v: float) -> int:
    return max(0, min(100, int(round(v))))


def _cap_bucket(total: float, add: float, cap: float) -> float:
    room = max(0.0, cap - total)
    return total + min(add, room)


_KEYWORD_SPLIT = re.compile(r"[a-z0-9]{3,}")


def _tokens(blob: str) -> Set[str]:
    return set(_KEYWORD_SPLIT.findall(blob.lower()))


def _intent_action_roles_aligned(intent_kind: str, steps: List[Dict[str, Any]]) -> bool:
    roles = [str(s.get("action_role") or "") for s in steps]
    if not roles:
        return False
    if intent_kind == "submission":
        return any(r in ("commit", "confirm", "navigate") for r in roles)
    if intent_kind == "cancellation":
        return any(r in ("cancel", "navigate") for r in roles)
    if intent_kind == "navigation":
        return any(r in ("navigate", "commit") for r in roles)
    if intent_kind == "feedback_acknowledgement":
        return any(r in ("cancel", "confirm") for r in roles)
    return True


def _tight_intent_outcome_fit(intent_kind: str, target_outcome: str, edge_kind: str) -> bool:
    if intent_kind == "submission":
        return edge_kind == "success_terminal" or edge_kind in NEGATIVE_OUTCOME_TYPES or edge_kind in (
            "confirmation_required",
            "review_required",
        )
    if intent_kind == "search":
        return target_outcome in ("empty", "neutral")
    if intent_kind == "deletion":
        return target_outcome in ("success", "neutral", "empty")
    if intent_kind == "feedback_acknowledgement":
        return target_outcome == "neutral"
    return True


_EMPTY_CORPUS_HINTS = (
    "no results",
    "no items",
    "nothing found",
    "no upcoming",
    "no bookings",
    "empty",
)


def score_candidate_edge(
    *,
    intent_kind: str,
    intent_confidence: str,
    validation_confidence: str,
    source_outcome: str,
    target_outcome: str,
    edge_kind: str,
    source_screen: str,
    target_screen: str,
    source_upload_order: Optional[int],
    target_upload_order: Optional[int],
    source_corpus: str,
    target_corpus: str,
    source_visible_texts: List[str],
    target_visible_texts: List[str],
    source_screen_purpose: str,
    target_screen_purpose: str,
    source_domain: Optional[str],
    target_domain: Optional[str],
    source_presentation_scope: str,
    target_presentation_scope: str,
    uses_template_sequence: bool,
    action_steps: List[Dict[str, Any]],
    source_group_id: Optional[str],
    source_screen_intent_id: Optional[str],
    main_action_texts: List[str],
    specific_value_matched: bool,
    target_has_extracted_specific_values: bool,
    ambiguous_selection: bool,
    unresolved_selection: bool,
    intent_has_evidence: bool,
    unordered_images_allowed: bool,
) -> ScoreResult:
    del intent_has_evidence  # reserved for future tuning
    reasons: List[str] = []
    risk_flags: List[str] = []

    base = 40.0
    reasons.append("base_after_gates=40")

    ga = 0.0
    if uses_template_sequence:
        ga = _cap_bucket(ga, 8.0, 20.0)
        reasons.append("+8 group_a_template_sequence")
    if action_steps and source_screen_intent_id and source_group_id:
        ids_ok = all(
            s.get("source_screen_intent_id") == source_screen_intent_id
            and s.get("source_group_id") == source_group_id
            for s in action_steps
        )
        if ids_ok:
            ga = _cap_bucket(ga, 4.0, 20.0)
            reasons.append("+4 group_a_trace_ids_complete")
    if action_steps and _intent_action_roles_aligned(intent_kind, action_steps):
        ga = _cap_bucket(ga, 5.0, 20.0)
        reasons.append("+5 group_a_roles_fit_intent")
    blob_steps = " ".join(" ".join(s.get("action_text") or []) for s in action_steps).strip()
    text_blob = blob_steps or " ".join(main_action_texts).strip()
    if text_blob:
        ga = _cap_bucket(ga, 3.0, 20.0)
        reasons.append("+3 group_a_non_empty_action_text")

    gb = 0.0
    corpus_low = target_corpus.lower()
    if target_outcome in (
        "success",
        "validation_error",
        "warning",
        "error",
        "failure",
        "empty",
        "confirmation_required",
        "review_required",
    ):
        if corpus_low.strip():
            gb = _cap_bucket(gb, 10.0, 20.0)
            reasons.append("+10 group_b_outcome_with_text_signal")

    tgt_joined = " ".join(target_visible_texts).lower()
    src_joined = " ".join(source_visible_texts).lower()
    if tgt_joined and tgt_joined != src_joined:
        gb = _cap_bucket(gb, 5.0, 20.0)
        reasons.append("+5 group_b_target_evidence_distinct")

    if _tight_intent_outcome_fit(intent_kind, target_outcome, edge_kind):
        gb = _cap_bucket(gb, 5.0, 20.0)
        reasons.append("+5 group_b_intent_outcome_tight_fit")

    if intent_kind == "search" and target_outcome in EMPTY_OUTCOME_TYPES:
        if any(h in corpus_low for h in _EMPTY_CORPUS_HINTS):
            gb = _cap_bucket(gb, 6.0, 20.0)
            reasons.append("+6 group_b_search_empty_evidence")

    gc = 0.0
    act_tokens = _tokens(text_blob or " ".join(main_action_texts))
    tgt_tokens = _tokens(target_corpus)
    if act_tokens and tgt_tokens and len(act_tokens & tgt_tokens) >= 2:
        gc = _cap_bucket(gc, 5.0, 15.0)
        reasons.append("+5 group_c_keyword_overlap")

    sp_src = source_screen_purpose.strip().lower()
    sp_tgt = target_screen_purpose.strip().lower()
    if sp_src and sp_tgt:
        if _tokens(sp_src) & _tokens(sp_tgt):
            gc = _cap_bucket(gc, 4.0, 15.0)
            reasons.append("+4 group_c_screen_purpose_continuity")

    if transition_pair_allowed(source_screen, target_screen) and transition_pair_bonus_eligible(
        source_screen, target_screen
    ):
        gc = _cap_bucket(gc, 4.0, 15.0)
        reasons.append("+4 group_c_transition_matrix_bonus")

    dom_s = (source_domain or "").strip().lower()
    dom_t = (target_domain or "").strip().lower()
    if dom_s and dom_t and dom_s == dom_t:
        gc = _cap_bucket(gc, 2.0, 15.0)
        reasons.append("+2 group_c_same_domain")

    gd = 0.0
    if specific_value_matched and target_has_extracted_specific_values:
        gd = _cap_bucket(gd, 15.0, 15.0)
        reasons.append("+15 group_d_specific_value_bound")
    elif not target_has_extracted_specific_values:
        needs_binding = intent_kind == "submission" and target_outcome in NEGATIVE_OUTCOME_TYPES
        if not needs_binding:
            gd = _cap_bucket(gd, 5.0, 15.0)
            reasons.append("+5 group_d_no_specific_value_expected")

    if unresolved_selection:
        gd -= 10.0
        reasons.append("-10 group_d_unresolved_selection_penalty")
        risk_flags.append("unresolved_selection_option")
    if ambiguous_selection:
        risk_flags.append("ambiguous_selection_requires_evidence")

    gd = max(-15.0, min(15.0, gd))

    ge_cap = 5.0 if unordered_images_allowed else 10.0
    ge = 0.0
    if (
        source_upload_order is not None
        and target_upload_order is not None
        and target_upload_order > source_upload_order
    ):
        bump = 2.5 if unordered_images_allowed else 5.0
        ge = _cap_bucket(ge, bump, ge_cap)
        reasons.append(f"+{bump:g} group_e_upload_order_forward")

    ps_tgt = target_presentation_scope.strip().lower()
    ps_src = source_presentation_scope.strip().lower()
    chromeish = {"modal", "drawer", "popover", "overlay"}
    if ps_tgt in chromeish and ps_src not in chromeish:
        bump = 1.5 if unordered_images_allowed else 3.0
        ge = _cap_bucket(ge, bump, ge_cap)
        reasons.append(f"+{bump:g} group_e_target_overlay")

    if intent_kind == "cancellation":
        if (
            source_upload_order is not None
            and target_upload_order is not None
            and target_upload_order < source_upload_order
        ):
            bump = 1.0 if unordered_images_allowed else 2.0
            ge = _cap_bucket(ge, bump, ge_cap)
            reasons.append(f"+{bump:g} group_e_cancellation_prior_upload_order")

    penalties: List[float] = []

    if intent_kind == "submission" and target_screen in GENERIC_GLOBAL_NAV_SCREEN_TYPES:
        penalties.append(12.0)
        reasons.append("-12 group_f_generic_nav_penalty")

    if edge_kind == "progress" and source_outcome == "neutral" and target_outcome == "neutral":
        if len(target_visible_texts) < 6:
            penalties.append(15.0)
            reasons.append("-15 group_f_neutral_progress_thin_target")

    ic = intent_confidence.strip().lower()
    if ic == "low":
        penalties.append(10.0)
        reasons.append("-10 group_f_intent_confidence_low")
    elif ic == "medium":
        penalties.append(4.0)
        reasons.append("-4 group_f_intent_confidence_medium")

    vc = validation_confidence.strip().lower()
    if vc == "low":
        penalties.append(8.0)
        reasons.append("-8 group_f_validation_confidence_low")

    if target_screen == "landing" and len(target_visible_texts) < 5 and intent_kind == "submission":
        penalties.append(10.0)
        reasons.append("-10 group_f_sparse_landing_target")

    penalty_sum = sum(penalties)
    if penalty_sum > 40:
        scale = 40.0 / penalty_sum
        penalties = [p * scale for p in penalties]
        penalty_sum = sum(penalties)
        reasons.append(f"group_f_penalties_scaled_to_cap40 was_adjusted")

    raw_total = base + ga + gb + gc + gd + ge - penalty_sum
    value = _clamp_score(raw_total)
    return ScoreResult(value=value, reasons=reasons, risk_flags=risk_flags)


def apply_many_compatible_targets_penalty(edges: List[Dict[str, Any]], *, excess_threshold: int = 6) -> None:
    """Apply diminishing penalty when one intent emits many surviving edges."""
    from collections import defaultdict

    buckets: Dict[tuple[str, Optional[str]], List[int]] = defaultdict(list)

    def _intent_id(e: Dict[str, Any]) -> Optional[str]:
        seq = e.get("action_sequence") or []
        if not seq:
            return None
        return seq[0].get("source_screen_intent_id")

    for idx, edge in enumerate(edges):
        buckets[(edge.get("from_state") or "", _intent_id(edge))].append(idx)

    for _, idxs in buckets.items():
        n = len(idxs)
        if n <= excess_threshold:
            continue
        pen = min(15.0, float((n - excess_threshold) * 3))
        ipen = int(round(pen))
        for i in idxs:
            e = edges[i]
            new_score = max(0, int(e.get("edge_score", 0)) - ipen)
            e["edge_score"] = float(new_score)
            rs = list(e.get("edge_score_reasons") or [])
            rs.append(f"many_compatible_targets_penalty=-{ipen}")
            e["edge_score_reasons"] = rs
            rf = list(e.get("edge_risk_flags") or [])
            rf.append("many_compatible_targets")
            e["edge_risk_flags"] = rf
