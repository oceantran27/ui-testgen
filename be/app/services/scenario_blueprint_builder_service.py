"""Build scenario writing blueprints (mandatory anchors) from intents + compressed catalog."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from app.model_providers.schemas import BehaviourIntentA5
from app.model_providers.schemas import (
    BlueprintTerminalStateRefA6,
    BlueprintTraceabilityA6,
    ForbiddenContentPolicyA6,
    MandatoryAnchorA6,
    MandatoryAnchorsBySectionA6,
    ScenarioWritingBlueprint,
)
from app.services.behaviour_contract_service import map_test_path
from app.services.ui_text_normalize import normalize_ui_text


def _clean_headline(txt: Optional[str]) -> str:
    t = str(txt or "").strip()
    return t[:200] if t else ""


def _feedback_match_ids(
    evidence_strings: Sequence[str], state_feedback_summary: Sequence[Dict[str, Any]]
) -> List[str]:
    out: List[str] = []
    seen = set()
    for ev in evidence_strings:
        en = normalize_ui_text(str(ev))
        if not en:
            continue
        for row in state_feedback_summary or []:
            if not isinstance(row, dict):
                continue
            fid = str(row.get("feedback_id") or "").strip()
            if not fid or fid in seen:
                continue
            for fb_text in row.get("text") or []:
                fn = normalize_ui_text(str(fb_text))
                if not fn:
                    continue
                if fn in en or en in fn:
                    out.append(fid)
                    seen.add(fid)
                    break
    return out


def _first_heading(card: Dict[str, Any]) -> str:
    vis = card.get("visible_signature") or {}
    for h in vis.get("headings") or []:
        c = _clean_headline(str(h))
        if c:
            return c
    return ""


def _primary_text_fallback(card: Dict[str, Any]) -> str:
    vis = card.get("visible_signature") or {}
    for p in vis.get("primary_texts") or []:
        c = _clean_headline(str(p))
        if c and len(c) > 2:
            return c
    return ""


def _card_for_sid(catalog_by_sid: Dict[str, Dict[str, Any]], sid: str) -> Dict[str, Any]:
    return dict(catalog_by_sid.get(str(sid), {}) or {})


def _resolve_trigger_action_id(
    card_start: Dict[str, Any],
    *,
    intent: BehaviourIntentA5,
) -> Optional[str]:
    ssi = intent.source_screen_intent_id
    for ig in card_start.get("intent_groups") or []:
        if not isinstance(ig, dict):
            continue
        if ssi and str(ig.get("intent_id") or "") == str(ssi):
            for key in ("primary_action", "commit_action"):
                pa = ig.get(key)
                if isinstance(pa, dict) and pa.get("action_id"):
                    return str(pa.get("action_id"))
    trigger_fragments = [str(t).strip().lower() for t in intent.trigger_action.text or []]
    trigger_joined = "".join(trigger_fragments)
    for ig in card_start.get("intent_groups") or []:
        if not isinstance(ig, dict):
            continue
        for key in ("primary_action", "commit_action"):
            pa = ig.get(key)
            if isinstance(pa, dict):
                texts = "".join([(str(x) or "").strip().lower() for x in pa.get("text") or []])
                if texts and trigger_joined and (trigger_joined in texts or texts in trigger_joined):
                    if pa.get("action_id"):
                        return str(pa.get("action_id"))
    return None


def _first_feedback_texts(rows: Sequence[Dict[str, Any]]) -> List[str]:
    texts: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for t in row.get("text") or []:
            c = _clean_headline(str(t))
            if c:
                texts.append(c)
    return texts


def _pick_then_anchors(intent: BehaviourIntentA5, end_card: Dict[str, Any]) -> List[MandatoryAnchorA6]:
    out: List[MandatoryAnchorA6] = []
    feedback_rows = list(end_card.get("state_feedback_summary") or [])
    ev_list = list(intent.expected_ui_evidence or [])
    neg_list = list(intent.negative_expectations or [])
    idx = 0

    for ev in ev_list:
        lbl = _clean_headline(ev)
        if lbl:
            out.append(
                MandatoryAnchorA6(
                    anchor_id=f"then_expected_ui_evidence_{idx}",
                    text=lbl,
                    source="intent.expected_ui_evidence",
                    match_type="exact_or_contained",
                )
            )
            idx += 1

    for neg in neg_list:
        lbl = _clean_headline(neg)
        if lbl:
            out.append(
                MandatoryAnchorA6(
                    anchor_id=f"then_negative_expectation_{idx}",
                    text=lbl,
                    source="intent.negative_expectations",
                    match_type="exact_or_contained",
                )
            )
            idx += 1

    if not out:
        fb_texts = _first_feedback_texts(feedback_rows)
        err_like = []
        for t in fb_texts:
            norm = normalize_ui_text(t)
            if "error" in norm or "invalid" in norm or "warn" in norm:
                err_like.append(t)
        pool = err_like if err_like else fb_texts[:2]
        for lbl in pool:
            c = _clean_headline(lbl)
            if c:
                out.append(
                    MandatoryAnchorA6(
                        anchor_id=f"then_state_feedback_summary_{idx}",
                        text=c,
                        source="end_state.state_feedback_summary",
                        match_type="exact_or_contained",
                    )
                )
                idx += 1

    if not out and (intent.expected_result or "").strip():
        er = _clean_headline(intent.expected_result)
        if er:
            out.append(
                MandatoryAnchorA6(
                    anchor_id="then_expected_result",
                    text=er,
                    source="intent.expected_result",
                    match_type="exact_or_contained",
                )
            )

    return out


def _slug(parts: Sequence[str]) -> str:
    raw = "_".join(p for p in parts if p)
    raw = raw[:72]
    safe = re.sub(r"[^\w\-]+", "_", raw.strip("_"))
    return safe or uuid.uuid4().hex[:12]


def build_scenario_blueprints(
    behaviour_intents: Sequence[BehaviourIntentA5],
    compressed_catalog_package: Dict[str, Any],
    *,
    screen_intent_package: Optional[Dict[str, Any]] = None,
) -> List[ScenarioWritingBlueprint]:
    _ = screen_intent_package

    catalog_by_sid: Dict[str, Dict[str, Any]] = {}
    for row in compressed_catalog_package.get("compressed_catalog") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("state_id") or "").strip()
        if sid:
            catalog_by_sid[sid] = row

    blueprints: List[ScenarioWritingBlueprint] = []

    for intent in behaviour_intents:
        start_sid = str(intent.start_state or "")
        end_sid = str(intent.end_state or "")
        sc_s = _card_for_sid(catalog_by_sid, start_sid)
        sc_e = _card_for_sid(catalog_by_sid, end_sid)

        given_heading = _first_heading(sc_s) or _primary_text_fallback(sc_s)
        purpose = _clean_headline(sc_s.get("screen_purpose"))
        if purpose and len(purpose) <= 120:
            given_anchor_text = purpose
        elif given_heading:
            given_anchor_text = given_heading
        else:
            given_anchor_text = ""

        outcome_type = ""
        tax_e = sc_e.get("taxonomy")
        tax = tax_e if isinstance(tax_e, dict) else {}
        if tax:
            outcome_type = str(tax.get("outcome_state_type") or "")

        given_anchors: List[MandatoryAnchorA6] = []
        if given_anchor_text:
            given_anchors.append(
                MandatoryAnchorA6(
                    anchor_id="given_start_screen",
                    text=given_anchor_text,
                    source="start_state.visible_signature.headings_or_screen_purpose",
                    match_type="exact_or_contained",
                )
            )

        when_anchors: List[MandatoryAnchorA6] = []
        for wi, txt in enumerate(intent.trigger_action.text or []):
            t = _clean_headline(txt)
            if not t:
                continue
            when_anchors.append(
                MandatoryAnchorA6(
                    anchor_id="when_trigger_action" if wi == 0 else f"when_trigger_action_{wi}",
                    text=t,
                    source="intent.trigger_action.text",
                    match_type="exact_or_contained",
                )
            )

        placeholders: List[str] = []
        ph_idx = 0
        for td in intent.test_data_requirements:
            ph = _clean_headline(f"<{td.value_type}>")
            placeholders.append(ph)
            when_anchors.append(
                MandatoryAnchorA6(
                    anchor_id=f"when_placeholder_{ph_idx}",
                    text=ph,
                    source="intent.test_data_requirements",
                    match_type="exact_or_contained",
                )
            )
            ph_idx += 1

        then_anchors = _pick_then_anchors(intent, sc_e)

        trace = BlueprintTraceabilityA6(
            trigger_action_id=_resolve_trigger_action_id(sc_s, intent=intent),
            source_screen_intent_id=intent.source_screen_intent_id,
            source_transition_ids=list(intent.source_transition_ids or []),
            expected_feedback_ids=_feedback_match_ids(
                intent.expected_ui_evidence or [],
                sc_e.get("state_feedback_summary") or [],
            ),
        )

        bid = _slug(["bp", intent.intent_id[-16:]])
        if not bid.startswith("bp"):
            bid = f"bp_{bid}"

        blueprint = ScenarioWritingBlueprint(
            blueprint_id=bid,
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            scenario_type=map_test_path(intent.intent_type),
            start_state=BlueprintTerminalStateRefA6(
                state_id=start_sid,
                screen_label=given_heading or purpose or start_sid,
                outcome_state_type=None,
            ),
            end_state=BlueprintTerminalStateRefA6(
                state_id=end_sid,
                screen_label=_first_heading(sc_e) or end_sid,
                outcome_state_type=outcome_type or None,
            ),
            writing_goal=(
                f"Write a natural BDD scenario for {intent.behaviour_name} "
                f"(intent {intent.intent_id}); keep mandatory anchors in the correct Given/When/Then blocks."
            ),
            mandatory_anchors=MandatoryAnchorsBySectionA6(given=given_anchors, when=when_anchors, then=then_anchors),
            allowed_test_data_placeholders=placeholders,
            forbidden_content_policy=ForbiddenContentPolicyA6(),
            traceability=trace,
        )

        blueprints.append(blueprint)

    return blueprints
