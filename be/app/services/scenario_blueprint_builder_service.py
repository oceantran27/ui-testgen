"""Build scenario writing blueprints (mandatory anchors) from intents + compressed catalog."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from app.model_providers.schemas import BehaviourIntentA5
from app.model_providers.schemas import (
    BlueprintHiddenAssertionA6,
    BlueprintTerminalStateRefA6,
    BlueprintTraceabilityA6,
    ForbiddenContentPolicyA6,
    MandatoryAnchorA6,
    MandatoryAnchorsBySectionA6,
    ScenarioWritingBlueprint,
)
from app.services.test_path_utils import map_test_path
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
    for el in card.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        if et not in ("heading", "title"):
            continue
        for h in el.get("text") or []:
            c = _clean_headline(str(h))
            if c:
                return c
    return ""


def _primary_text_fallback(card: Dict[str, Any]) -> str:
    for el in card.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        rh = el.get("role_hint")
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        if not texts:
            continue
        if rh in ("primary_action", "required_input", "optional_input", "navigation"):
            return _clean_headline(texts[0]) or _clean_headline(" ".join(texts))
        if et in ("button", "link", "input", "select"):
            return _clean_headline(texts[0]) or _clean_headline(" ".join(texts))
    return ""


def _element_text_buckets_for_then(card: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Primary-like vs status-like visible strings from elements + feedback (no pre-aggregated signature)."""
    primary_texts: List[str] = []
    status_texts: List[str] = []
    for el in card.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        rh = el.get("role_hint")
        if rh in ("primary_action", "required_input", "optional_input", "navigation") and texts:
            primary_texts.extend(texts)
        if et in ("button", "link", "input", "select") and texts:
            primary_texts.extend(texts)
        if (rh in ("status", "status_indicator") or et in ("badge", "status")) and texts:
            status_texts.extend(texts)
    for fb in card.get("visible_feedback") or []:
        if not isinstance(fb, dict):
            continue
        for t in fb.get("text") or []:
            s = str(t).strip()
            if s:
                status_texts.append(s)
    return primary_texts, status_texts


def _card_for_sid(catalog_by_sid: Dict[str, Dict[str, Any]], sid: str) -> Dict[str, Any]:
    return dict(catalog_by_sid.get(str(sid), {}) or {})


def _resolve_trigger_action_id(
    card_start: Dict[str, Any],
    *,
    intent: BehaviourIntentA5,
) -> Optional[str]:
    ssi = intent.source_screen_intent_id
    for ig in card_start.get("screen_intents") or []:
        if not isinstance(ig, dict):
            continue
        row_ids = [
            str(ig.get("screen_intent_id") or ""),
            str(ig.get("intent_id") or ""),
        ]
        if ssi and str(ssi) not in row_ids:
            continue
        for key in ("primary_action", "commit_action"):
            pa = ig.get(key)
            if isinstance(pa, dict) and pa.get("action_id"):
                return str(pa.get("action_id"))
    trigger_fragments = [str(t).strip().lower() for t in intent.trigger_action.text or []]
    trigger_joined = "".join(trigger_fragments)
    for ig in card_start.get("screen_intents") or []:
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


_MAX_THEN_PRIMARY_TEXTS = 6
_MAX_THEN_STATUS_TEXTS = 4
_MAX_EVIDENCE_FRAGMENT_LEN = 120


def _split_evidence_into_atomic_fragments(evidence: str) -> List[str]:
    """Split long expected_ui_evidence into shorter fragments for atomic Then anchors."""
    raw = str(evidence or "").strip()
    if not raw:
        return []
    parts = re.split(r"[\n;.]+", raw)
    out: List[str] = []
    for p in parts:
        chunk = p.strip()
        if not chunk:
            continue
        if len(chunk) > _MAX_EVIDENCE_FRAGMENT_LEN:
            chunk = chunk[:_MAX_EVIDENCE_FRAGMENT_LEN].rstrip()
        if len(chunk) > 2:
            out.append(chunk)
    return out


def _selected_option_display_texts(card: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for intent in card.get("screen_intents") or []:
        if not isinstance(intent, dict):
            continue
        for opt in intent.get("selection_options") or []:
            if not isinstance(opt, dict):
                continue
            if str(opt.get("visible_status") or "").lower() != "selected":
                continue
            parts = [str(x).strip() for x in (opt.get("option_text") or opt.get("text") or []) if str(x).strip()]
            if parts:
                merged = " ".join(parts)
                c = _clean_headline(merged)
                if c:
                    out.append(c)
    return out


def _pick_then_anchors(intent: BehaviourIntentA5, end_card: Dict[str, Any]) -> List[MandatoryAnchorA6]:
    out: List[MandatoryAnchorA6] = []
    seen_norm: set[str] = set()
    idx = 0

    def _push(anchor_id: str, text: str, source: str) -> None:
        nonlocal idx
        lbl = _clean_headline(text)
        if not lbl:
            return
        nn = normalize_ui_text(lbl)
        if not nn or nn in seen_norm:
            return
        seen_norm.add(nn)
        out.append(
            MandatoryAnchorA6(
                anchor_id=anchor_id if anchor_id else f"then_anchor_{idx}",
                text=lbl,
                source=source,
                match_type="exact_or_contained",
            )
        )
        idx += 1

    # 1) End screen heading / label (visible)
    heading = _first_heading(end_card)
    if heading:
        _push("then_screen_label", heading, "end_state.visible_elements.headings")

    # 2) Feedback lines on end state
    for t in _first_feedback_texts(list(end_card.get("visible_feedback") or [])):
        _push(f"then_state_feedback_{idx}", t, "end_state.visible_feedback")

    # 3) Primary / status texts from visible elements (+ feedback counted in bucket)
    pri_b, st_b = _element_text_buckets_for_then(end_card)
    n_pri = 0
    for p in pri_b:
        if n_pri >= _MAX_THEN_PRIMARY_TEXTS:
            break
        _push(f"then_primary_text_{idx}", str(p), "end_state.visible_elements")
        n_pri += 1
    n_st = 0
    for p in st_b:
        if n_st >= _MAX_THEN_STATUS_TEXTS:
            break
        _push(f"then_status_text_{idx}", str(p), "end_state.visible_elements")
        n_st += 1

    # 4) Fallback: atomic fragments from expected_ui_evidence (never full-paragraph single anchor if split helps)
    for ev in intent.expected_ui_evidence or []:
        for frag in _split_evidence_into_atomic_fragments(str(ev)):
            _push(f"then_expected_ui_evidence_{idx}", frag, "intent.expected_ui_evidence")

    # 5) Last resort: expected_result
    if not out and (intent.expected_result or "").strip():
        _push("then_expected_result", intent.expected_result, "intent.expected_result")

    return out


def _hidden_assertions_from_intent(intent: BehaviourIntentA5) -> List[BlueprintHiddenAssertionA6]:
    hidden: List[BlueprintHiddenAssertionA6] = []
    for neg in intent.negative_expectations or []:
        n = str(neg).strip()
        if not n:
            continue
        a_type = "feedback_not_visible" if "feedback" in n.lower() else "state_not_reached"
        hidden.append(
            BlueprintHiddenAssertionA6(
                assertion_type=a_type,
                expected=n,
                render_in_gherkin=False,
                ui_text_grounding_required=False,
            )
        )
    return hidden


def _build_when_anchors(
    intent: BehaviourIntentA5, start_card: Dict[str, Any]
) -> tuple[List[MandatoryAnchorA6], List[str]]:
    """Concrete selected values and trigger first; placeholders only for requirements without a concrete slot."""
    placeholders: List[str] = []
    when_anchors: List[MandatoryAnchorA6] = []

    concrete = _selected_option_display_texts(start_card)
    for i, t in enumerate(concrete):
        when_anchors.append(
            MandatoryAnchorA6(
                anchor_id=f"when_selected_{i}",
                text=t,
                source="start_state.screen_intents.selection_options",
                match_type="exact_or_contained",
            )
        )

    for ti, txt in enumerate(intent.trigger_action.text or []):
        t = _clean_headline(txt)
        if not t:
            continue
        when_anchors.append(
            MandatoryAnchorA6(
                anchor_id="when_trigger_action" if ti == 0 else f"when_trigger_action_{ti}",
                text=t,
                source="intent.trigger_action.text",
                match_type="exact_or_contained",
            )
        )

    ph_idx = 0
    for req_i, td in enumerate(intent.test_data_requirements):
        ph = _clean_headline(f"<{td.value_type}>")
        if ph:
            placeholders.append(ph)
        if req_i >= len(concrete):
            when_anchors.append(
                MandatoryAnchorA6(
                    anchor_id=f"when_placeholder_{ph_idx}",
                    text=ph,
                    source="intent.test_data_requirements",
                    match_type="exact_or_contained",
                )
            )
            ph_idx += 1

    return when_anchors, placeholders


def _slug(parts: Sequence[str]) -> str:
    raw = "_".join(p for p in parts if p)
    raw = raw[:72]
    safe = re.sub(r"[^\w\-]+", "_", raw.strip("_"))
    return safe or uuid.uuid4().hex[:12]


def build_scenario_blueprints(
    behaviour_intents: Sequence[BehaviourIntentA5],
    compressed_catalog_package: Dict[str, Any],
) -> List[ScenarioWritingBlueprint]:

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

        tax_s_raw = sc_s.get("taxonomy")
        tax_s = tax_s_raw if isinstance(tax_s_raw, dict) else {}
        start_outcome = str(tax_s.get("outcome_state_type") or "") if tax_s else ""

        given_anchors: List[MandatoryAnchorA6] = []
        if given_anchor_text:
            given_anchors.append(
                MandatoryAnchorA6(
                    anchor_id="given_start_screen",
                    text=given_anchor_text,
                    source="start_state.visible_elements.headings_or_screen_purpose",
                    match_type="exact_or_contained",
                )
            )

        when_anchors, placeholders = _build_when_anchors(intent, sc_s)

        then_anchors = _pick_then_anchors(intent, sc_e)
        hidden_assertions = _hidden_assertions_from_intent(intent)

        trace = BlueprintTraceabilityA6(
            trigger_action_id=_resolve_trigger_action_id(sc_s, intent=intent),
            source_screen_intent_id=intent.source_screen_intent_id,
            source_transition_ids=list(intent.source_transition_ids or []),
            expected_feedback_ids=_feedback_match_ids(
                intent.expected_ui_evidence or [],
                sc_e.get("visible_feedback") or [],
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
                outcome_state_type=start_outcome or None,
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
            hidden_assertions=hidden_assertions,
            forbidden_content_policy=ForbiddenContentPolicyA6(),
            traceability=trace,
        )

        blueprints.append(blueprint)

    return blueprints
