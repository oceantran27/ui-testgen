"""Hard gates for deterministic candidate edges (Layer 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.constants.edge_taxonomy import (
    INTENTS_ALLOWED_FROM_TERMINAL_SOURCE,
    SCREEN_TRANSITION_BONUS_PAIRS,
    SOURCE_TERMINAL_OUTCOME_TYPES,
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    code: Optional[str] = None
    detail: Optional[str] = None


INTENT_CROSS_TEMPLATE_STEP_TYPES = frozenset(
    {
        "navigate",
        "open",
        "close",
        "confirm",
        "cancel",
        "invoke_action",
        "select_option",
        "toggle_option",
    }
)


def _template_steps(intent: Dict[str, Any]) -> List[Dict[str, Any]]:
    tmpls = intent.get("local_action_sequence_templates") or []
    if not tmpls:
        return []
    tmpl = tmpls[0]
    return list(tmpl.get("steps") or [])


def gate_intent_cross_state_capability(intent: Dict[str, Any]) -> GateResult:
    """
    Gate 3 — intent must expose at least one cross-state-capable action or template step.
    """
    ik = intent.get("intent_kind") or ""
    commit_act = intent.get("commit_action") or intent.get("primary_action")
    if commit_act:
        return GateResult(True)

    tmpl_steps = _template_steps(intent)
    tmpl_cross = False
    for raw in tmpl_steps:
        st = str(raw.get("step_type") or "invoke_action").strip()
        if st in INTENT_CROSS_TEMPLATE_STEP_TYPES:
            tmpl_cross = True
            break

    secondary_soft = False
    for sec in intent.get("secondary_actions") or []:
        text = " ".join(sec.get("text") or []).lower()
        if any(
            w in text
            for w in (
                "cancel",
                "confirm",
                "close",
                "dismiss",
                "got it",
                "okay",
                "ok",
            )
        ):
            secondary_soft = True
            break

    if ik == "feedback_acknowledgement":
        if secondary_soft or tmpl_cross:
            return GateResult(True)
        return GateResult(False, "no_feedback_dismiss_action", ik)

    if ik == "cancellation":
        if secondary_soft or tmpl_cross:
            return GateResult(True)
        return GateResult(False, "no_cancellation_control", ik)

    if ik == "confirmation" and secondary_soft:
        return GateResult(True)

    if tmpl_cross:
        return GateResult(True)

    if ik == "selection":
        opts = intent.get("selection_options") or []
        if not opts:
            return GateResult(False, "selection_without_options_or_commit", ik)
        for raw in tmpl_steps:
            st = str(raw.get("step_type") or "").strip()
            if st in ("select_option", "toggle_option"):
                return GateResult(True)
        return GateResult(False, "selection_requires_commit_template_or_select_step", ik)

    if ik == "navigation":
        if intent.get("primary_action") or intent.get("commit_action"):
            return GateResult(True)
        return GateResult(False, "navigation_without_primary_action", ik)

    return GateResult(False, "no_cross_state_action_or_template", ik)


def gate_source_terminal(intent_kind: str, source_outcome: str) -> GateResult:
    """Gate 5 — block transitions from terminal sources unless navigation-like intent."""
    if source_outcome not in SOURCE_TERMINAL_OUTCOME_TYPES:
        return GateResult(True)
    if intent_kind in INTENTS_ALLOWED_FROM_TERMINAL_SOURCE:
        return GateResult(True)
    return GateResult(False, "post_terminal_source_blocked", f"{intent_kind}:{source_outcome}")


def gate_target_distinguishing_evidence(
    source_card: Dict[str, Any],
    target_card: Dict[str, Any],
    source_screen: str,
    target_screen: str,
) -> GateResult:
    """Gate 6 — target must carry enough signal vs chrome-only screens."""
    vt = target_card.get("visible_text") or []
    if vt and any(str(x).strip() for x in vt):
        return GateResult(True)
    if target_card.get("feedback_texts"):
        return GateResult(True)

    sp_src = (source_card.get("screen_purpose") or "").strip().lower()
    sp_tgt = (target_card.get("screen_purpose") or "").strip().lower()
    if sp_tgt and sp_tgt != sp_src:
        return GateResult(True)

    target_outcome = target_card.get("outcome_state_type", "neutral")
    if target_outcome != "neutral":
        return GateResult(True)

    if target_screen != source_screen and (source_screen, target_screen) in SCREEN_TRANSITION_BONUS_PAIRS:
        return GateResult(True)

    ps = str(target_card.get("presentation_scope") or "").strip().lower()
    if ps in ("modal", "drawer", "popover", "overlay", "toast"):
        return GateResult(True)

    return GateResult(False, "target_missing_distinguishing_evidence", target_screen)


def hard_gate_before_targets(intent: Dict[str, Any]) -> GateResult:
    """Run Gate 3 once per intent (before iterating targets)."""
    return gate_intent_cross_state_capability(intent)


def hard_gate_per_transition(
    *,
    intent_kind: str,
    source_outcome: str,
    source_card: Dict[str, Any],
    target_card: Dict[str, Any],
    source_screen: str,
    target_screen: str,
) -> GateResult:
    """Gates 5–6 for each (source, intent, target) triple."""
    r = gate_source_terminal(intent_kind, source_outcome)
    if not r.ok:
        return r
    return gate_target_distinguishing_evidence(source_card, target_card, source_screen, target_screen)
