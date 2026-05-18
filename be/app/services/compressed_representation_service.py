"""Deterministic compression of Phase 1+2 artefacts into a token-light catalogue for batched global flow discovery."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, List, Literal, Optional, Tuple, cast, get_args

from app.constants.screen_intent_taxonomy import VISIBLE_STATUS_VALUES
from app.constants.ui_screen_taxonomy import normalize_screen_type
from app.model_providers.schemas import (
    A1ActionPriority,
    A1FeedbackType,
    A1OutcomeStateType,
    A1PresentationScope,
    A1ScreenType,
    CompressedActionRef,
    CompressedCatalogPackage,
    CompressedContinuityEntity,
    CompressedContinuityEntityType,
    CompressedEvidenceRef,
    CompressedFormField,
    CompressedFormSelectionOption,
    CompressedFormStateSummary,
    CompressedIntentGroup,
    CompressedLocalActionStep,
    CompressedNavigationCues,
    CompressedScreenCard,
    CompressedStateFeedbackItem,
    CompressedTaxonomy,
    CompressedTraceIndexEntry,
    CompressedVisibleSignature,
)

_PRESENTATION_OK: frozenset[str] = frozenset(get_args(A1PresentationScope))
_OUTCOME_OK: frozenset[str] = frozenset(get_args(A1OutcomeStateType))
_FEEDBACK_OK: frozenset[str] = frozenset(get_args(A1FeedbackType))
_OPTION_REF_OK = frozenset({"element", "action"})

_MAX_HEADINGS = 8
_MAX_PRIMARY_TEXTS = 10
_MAX_STATUS_TEXTS = 8
_MAX_BREADCRUMB_PARTS = 12

_STEP_FRACTION_RE = re.compile(r"step\s*(\d+)\s*/\s*(\d+)", re.I)
_STEP_OF_RE = re.compile(r"step\s*(\d+)\s+of\s+(\d+)", re.I)

# Continuity: deterministic strings only (cap 8 / screen). See _build_continuity_entities docstring.
_MAX_CONTINUITY_ENTITIES = 8
_MAX_CONTINUITY_CANDIDATE_LEN = 200
_RE_CONT_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?\b", re.I)
_RE_CONT_DATE_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_RE_CONT_DATE_SLASH = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_RE_CONT_AMOUNT = re.compile(
    r"[$\u20AC\u00A3\u20BD]\s*\d[\d,]*(?:\.\d{2})?\b|\b\d[\d,]*(?:\.\d{2})?\s*(?:USD|EUR|GBP|VND)\b",
    re.I,
)
_RE_CONT_ORDER = re.compile(r"\b(?:order|booking|confirmation|ref)\s*#?\s*[\w-]{3,}\b", re.I)
_RE_CONT_ORDER_HASH = re.compile(r"#\s*[\dA-Z]{4,}\b")
_RE_CONT_APPOINT = re.compile(r"\b(?:appointment|booking|reservation)\b", re.I)
_ALLOWED_CONTINUITY_TYPES: frozenset[str] = frozenset(get_args(CompressedContinuityEntityType))


def _norm_domain(raw: str | None) -> str:
    t = (raw or "").strip()
    return t if t else "unknown"


def _norm_presentation_scope(raw: str | None) -> A1PresentationScope:
    s = (raw or "unknown").strip().lower() or "unknown"
    if s in _PRESENTATION_OK:
        return cast(A1PresentationScope, s)
    return "unknown"


def _norm_outcome_state_type(raw: str | None) -> A1OutcomeStateType:
    s = (raw or "unknown").strip().lower() or "unknown"
    if s in _OUTCOME_OK:
        return cast(A1OutcomeStateType, s)
    return "unknown"


def _norm_feedback_type(raw: str | None) -> A1FeedbackType:
    s = (raw or "unknown").strip().lower() or "unknown"
    if s in _FEEDBACK_OK:
        return cast(A1FeedbackType, s)
    return "unknown"


def _dedupe_cap(strings: List[str], cap: int) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for x in strings:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s[:200])
        if len(out) >= cap:
            break
    return out


def _merge_action_with_catalog(
    intent_fragment: Dict[str, Any] | None,
    actions_by_id: Dict[str, Dict[str, Any]],
    *,
    default_priority: str,
) -> Dict[str, Any] | None:
    if not isinstance(intent_fragment, dict):
        return None
    aid = intent_fragment.get("action_id")
    if not aid:
        return None
    aid = str(aid)
    base = dict(actions_by_id.get(aid) or {})
    merged: Dict[str, Any] = {
        "action_id": aid,
        "action_type": str(base.get("action_type") or intent_fragment.get("action_type") or "unknown"),
        "text": list(base.get("text") or intent_fragment.get("text") or []),
        "action_priority": base.get("action_priority") or intent_fragment.get("action_priority"),
    }
    return merged


def _to_action_ref(row: Dict[str, Any], default_priority: str = "primary") -> CompressedActionRef | None:
    aid = row.get("action_id")
    if not aid:
        return None
    pr = row.get("action_priority") or default_priority
    pr = str(pr).strip().lower()
    if pr not in ("primary", "secondary", "tertiary"):
        pr = default_priority
    return CompressedActionRef(
        action_id=str(aid),
        action_type=str(row.get("action_type") or "unknown"),
        text=[str(t) for t in (row.get("text") or []) if str(t).strip()],
        priority=cast(A1ActionPriority, pr),
    )


def _build_visible_signature(state: Dict[str, Any], feedback_rows: List[Dict[str, Any]]) -> CompressedVisibleSignature:
    headings: List[str] = []
    primary_texts: List[str] = []
    status_texts: List[str] = []

    for el in state.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        rh = el.get("role_hint")
        if et in ("heading",) and texts:
            headings.extend(texts[:2])
        if rh in ("primary_action", "required_input", "optional_input", "navigation") and texts:
            primary_texts.extend(texts[:2])
        if rh == "status_indicator" and texts:
            status_texts.extend(texts[:2])

    for fb in feedback_rows:
        for t in fb.get("text") or []:
            s = str(t).strip()
            if s:
                status_texts.append(s)

    return CompressedVisibleSignature(
        headings=_dedupe_cap(headings, _MAX_HEADINGS),
        primary_texts=_dedupe_cap(primary_texts, _MAX_PRIMARY_TEXTS),
        status_texts=_dedupe_cap(status_texts, _MAX_STATUS_TEXTS),
    )


def _build_navigation_cues(state: Dict[str, Any]) -> CompressedNavigationCues:
    breadcrumb_texts: List[str] = []
    active_tab_text: Optional[str] = None
    step_label_text: Optional[str] = None
    step_index_visible: Optional[int] = None
    step_total_visible: Optional[int] = None
    progress_text: Optional[str] = None

    all_text_chunks: List[str] = []

    for el in state.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        blob = " ".join(texts)
        if blob:
            all_text_chunks.append(blob)
        if et == "navigation" and ">" in blob:
            parts = [p.strip() for p in blob.split(">") if p.strip()]
            breadcrumb_texts.extend(parts[:_MAX_BREADCRUMB_PARTS])
        if et == "tab" and texts:
            active_tab_text = active_tab_text or texts[0]
        if et in ("progress", "badge") and texts and progress_text is None:
            progress_text = texts[0]

    combined = " | ".join(all_text_chunks)
    for rx in (_STEP_FRACTION_RE, _STEP_OF_RE):
        m = rx.search(combined)
        if m:
            step_index_visible = int(m.group(1))
            step_total_visible = int(m.group(2))
            progress_text = progress_text or m.group(0).strip()
            break

    for el in state.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        if et != "text":
            continue
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        for t in texts:
            if any(k in t.lower() for k in ("shipping", "payment", "review", "confirm")) and step_label_text is None:
                step_label_text = t[:120]
                break

    return CompressedNavigationCues(
        breadcrumb_texts=_dedupe_cap(breadcrumb_texts, _MAX_BREADCRUMB_PARTS),
        active_tab_text=active_tab_text,
        step_label_text=step_label_text,
        step_index_visible=step_index_visible,
        step_total_visible=step_total_visible,
        progress_text=progress_text,
    )


def _feedback_rows(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [f for f in (state.get("visible_feedback") or []) if isinstance(f, dict)]


def _build_state_feedback_summary(state: Dict[str, Any]) -> List[CompressedStateFeedbackItem]:
    out: List[CompressedStateFeedbackItem] = []
    for fb in _feedback_rows(state):
        fid = fb.get("feedback_id")
        if not fid:
            continue
        out.append(
            CompressedStateFeedbackItem(
                feedback_id=str(fid),
                feedback_type=_norm_feedback_type(str(fb.get("feedback_type") or "")),
                text=[str(t) for t in (fb.get("text") or []) if str(t).strip()],
                related_element_ids=[str(x) for x in (fb.get("related_element_ids") or []) if x],
                visual_region=str(fb.get("visual_region") or "unknown"),
            )
        )
    return out


def _build_form_state_summary(state: Dict[str, Any]) -> CompressedFormStateSummary:
    required_inputs: List[CompressedFormField] = []
    optional_inputs: List[CompressedFormField] = []
    selected_options: List[CompressedFormSelectionOption] = []

    has_validation_feedback = False
    for fb in _feedback_rows(state):
        ft = str(fb.get("feedback_type") or "").lower()
        if ft == "validation_error":
            has_validation_feedback = True
            break

    has_visible_values = False
    has_form = False

    for el in state.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or "")
        eid = el.get("element_id")
        texts = [str(t) for t in (el.get("text") or []) if str(t).strip()]
        rh = el.get("role_hint")

        if et in ("input", "textarea", "select", "checkbox", "radio", "date_picker") or rh in (
            "required_input",
            "optional_input",
        ):
            has_form = True
        if texts and et in ("input", "textarea", "select"):
            has_visible_values = True

        if eid and rh == "required_input":
            required_inputs.append(CompressedFormField(element_id=str(eid), text=texts))
        elif eid and rh == "optional_input":
            optional_inputs.append(CompressedFormField(element_id=str(eid), text=texts))

        vs = el.get("visible_status")
        if vs and eid and str(vs).lower() == "selected":
            selected_options.append(
                CompressedFormSelectionOption(
                    option_ref_type="element",
                    option_element_id=str(eid),
                    option_action_id=None,
                    text=texts or [str(eid)],
                    visible_status=str(vs),
                )
            )

    if not has_form and (required_inputs or optional_inputs):
        has_form = True

    return CompressedFormStateSummary(
        has_form=has_form,
        required_inputs=required_inputs,
        optional_inputs=optional_inputs,
        selected_options=selected_options,
        has_visible_values=has_visible_values,
        has_validation_feedback=has_validation_feedback,
    )


def _classify_continuity_entity_type(blob: str) -> str:
    """Map free text to `CompressedContinuityEntityType` when patterns match; else unknown."""
    b = blob.strip()
    if not b:
        return "unknown"
    if _RE_CONT_ORDER.search(b) or _RE_CONT_ORDER_HASH.search(b):
        return "order"
    if _RE_CONT_AMOUNT.search(b):
        return "amount"
    if _RE_CONT_TIME.search(b):
        return "time"
    if _RE_CONT_DATE_ISO.search(b) or _RE_CONT_DATE_SLASH.search(b):
        return "date"
    if _RE_CONT_APPOINT.search(b):
        return "appointment"
    return "unknown"


def _continuity_candidate_tuples_from_state(state: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """Yield (display_text, element_id) from visible elements and short feedback lines."""
    out: List[Tuple[str, Optional[str]]] = []
    for el in state.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        eid_raw = el.get("element_id")
        eid = str(eid_raw) if eid_raw else None
        et = str(el.get("element_type") or "")
        rh = str(el.get("role_hint") or "")
        texts = [str(t).strip() for t in (el.get("text") or []) if str(t).strip()]
        if not texts:
            continue
        blob = " ".join(texts[:6])[:_MAX_CONTINUITY_CANDIDATE_LEN]
        if et == "heading":
            if len(blob) <= 140:
                out.append((blob, eid))
        elif et in ("input", "textarea", "select", "checkbox", "radio", "date_picker") or rh in (
            "required_input",
            "optional_input",
            "primary_action",
            "status_indicator",
        ):
            out.append((blob, eid))
        elif et == "text" and rh in ("required_input", "optional_input", "status_indicator"):
            out.append((blob, eid))
    for fb in _feedback_rows(state):
        ft = str(fb.get("feedback_type") or "").lower()
        if ft not in ("error", "warning", "success", "info", "validation_error", "toast"):
            continue
        for t in fb.get("text") or []:
            s = str(t).strip()
            if 4 <= len(s) <= _MAX_CONTINUITY_CANDIDATE_LEN:
                out.append((s, None))
    return out


def _build_continuity_entities(state: Dict[str, Any]) -> List[CompressedContinuityEntity]:
    """Grounded continuity tokens for cross-screen discovery / blueprint anchors.

    Heuristics: regex for time, date, amount, order/booking ref, appointment wording; otherwise
    only short value-like strings with an element_id and a digit. At most
    ``_MAX_CONTINUITY_ENTITIES`` per state; deduped by normalized text. No LLM.
    """
    seen_norm: set[str] = set()
    entities: List[CompressedContinuityEntity] = []
    for blob, eid in _continuity_candidate_tuples_from_state(state):
        blob = blob.strip()
        if not blob:
            continue
        nkey = " ".join(blob.lower().split())
        if not nkey or nkey in seen_norm:
            continue
        ent_kind = _classify_continuity_entity_type(blob)
        if ent_kind == "unknown":
            if eid and len(blob) <= 55 and re.search(r"\d", blob):
                pass
            else:
                continue
        ent_kind = ent_kind if ent_kind in _ALLOWED_CONTINUITY_TYPES else "unknown"
        seen_norm.add(nkey)
        entities.append(
            CompressedContinuityEntity(
                entity_type=cast(CompressedContinuityEntityType, ent_kind),
                text=[blob],
                source_element_id=eid,
            )
        )
        if len(entities) >= _MAX_CONTINUITY_ENTITIES:
            break
    return entities


def _state_level_evidence_refs(state: Dict[str, Any]) -> List[CompressedEvidenceRef]:
    refs: List[CompressedEvidenceRef] = []
    for el in (state.get("visible_elements") or [])[:24]:
        if not isinstance(el, dict):
            continue
        if str(el.get("element_type") or "") == "heading" and el.get("element_id"):
            refs.append(CompressedEvidenceRef(evidence_type="heading", source_id=str(el["element_id"])))
            break
    for g in (state.get("interaction_groups") or [])[:3]:
        if isinstance(g, dict) and g.get("group_id"):
            refs.append(CompressedEvidenceRef(evidence_type="interaction_group", source_id=str(g["group_id"])))
            break
    return refs


def _feedback_ids_from_evidence(evidence_refs: List[CompressedEvidenceRef]) -> List[str]:
    out: List[str] = []
    for er in evidence_refs:
        et = (er.evidence_type or "").lower()
        if "feedback" in et:
            sid = str(er.source_id or "").strip()
            if sid and sid not in out:
                out.append(sid)
    return out


def _norm_visible_status_for_actions(raw: str) -> str:
    s = (raw or "unknown").strip().lower()
    if s in VISIBLE_STATUS_VALUES:
        return s
    return "unknown"


def _action_text_and_value(option_texts: List[str], catalog_texts: List[str]) -> tuple[str, str]:
    """Join option copy with catalogue; value prefers last line when multiple tokens."""
    opt = [str(t).strip() for t in option_texts if str(t).strip()]
    cat = [str(t).strip() for t in catalog_texts if str(t).strip()]
    lines = opt if opt else cat
    if not lines:
        return "", ""
    action_text = " ".join(lines)
    value = lines[-1] if len(lines) >= 2 else lines[0]
    return action_text, value


def _intent_action_rows(
    intent: Dict[str, Any],
    actions_by_id: Dict[str, Dict[str, Any]],
    pa_row: Dict[str, Any] | None,
) -> List[Tuple[str, str, str, str, str]]:
    """One row per selectable/action-backed option plus primary if missing: id, type, text, value, status."""
    rows: List[Tuple[str, str, str, str, str]] = []
    seen: set[str] = set()

    for so in intent.get("selection_options") or []:
        if not isinstance(so, dict):
            continue
        aid_raw = so.get("option_action_id")
        if not aid_raw:
            continue
        aid = str(aid_raw).strip()
        if not aid or aid in seen:
            continue
        merged = _merge_action_with_catalog(
            {"action_id": aid},
            actions_by_id,
            default_priority="primary",
        )
        opt_texts = list(so.get("option_text") or so.get("text") or [])
        cat_texts = list((merged or {}).get("text") or [])
        action_text, value = _action_text_and_value(opt_texts, cat_texts)
        if not action_text and merged:
            action_text, value = _action_text_and_value(cat_texts, [])
        if not action_text:
            action_text = aid
        if not value:
            value = action_text
        atype = str((merged or {}).get("action_type") or "unknown")
        status = _norm_visible_status_for_actions(str(so.get("visible_status") or "unknown"))
        rows.append((aid, atype, action_text, value, status))
        seen.add(aid)

    if isinstance(pa_row, dict):
        pid = str(pa_row.get("action_id") or "").strip()
        if pid and pid not in seen:
            texts = [str(t) for t in (pa_row.get("text") or []) if str(t).strip()]
            action_text, value = _action_text_and_value(texts, [])
            if not action_text:
                action_text = pid
            if not value:
                value = action_text
            atype = str(pa_row.get("action_type") or "unknown")
            rows.append((pid, atype, action_text, value, "unknown"))
            seen.add(pid)

    return rows


def _flatten_local_action_sequence(intent: Dict[str, Any]) -> List[CompressedLocalActionStep]:
    steps_out: List[CompressedLocalActionStep] = []
    for tmpl in intent.get("local_action_sequence_templates") or []:
        if not isinstance(tmpl, dict):
            continue
        for st in tmpl.get("steps") or []:
            if not isinstance(st, dict):
                continue
            steps_out.append(
                CompressedLocalActionStep(
                    step_type=str(st.get("step_type") or "invoke_action"),
                    source_action_id=str(st["source_action_id"]) if st.get("source_action_id") else None,
                    source_element_id=str(st["source_element_id"]) if st.get("source_element_id") else None,
                )
            )
    return steps_out


def _intent_selection_options(intent: Dict[str, Any]) -> List[CompressedFormSelectionOption]:
    opts: List[CompressedFormSelectionOption] = []
    for so in intent.get("selection_options") or []:
        if not isinstance(so, dict):
            continue
        ort = str(so.get("option_ref_type") or "element").lower()
        if ort not in _OPTION_REF_OK:
            ort = "element"
        txt = list(so.get("option_text") or so.get("text") or [])
        opts.append(
            CompressedFormSelectionOption(
                option_ref_type=cast(Literal["element", "action"], ort),
                option_element_id=str(so["option_element_id"]) if so.get("option_element_id") else None,
                option_action_id=str(so["option_action_id"]) if so.get("option_action_id") else None,
                text=[str(t) for t in txt if str(t).strip()],
                visible_status=str(so.get("visible_status") or "unknown"),
            )
        )
    return opts


def _build_intent_groups(
    intents: List[Dict[str, Any]],
    actions_by_id: Dict[str, Dict[str, Any]],
) -> List[CompressedIntentGroup]:
    groups: List[CompressedIntentGroup] = []
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        iid = str(intent.get("screen_intent_id") or "")
        gid = str(intent.get("source_group_id") or "")
        if not iid:
            continue

        pa_row = _merge_action_with_catalog(intent.get("primary_action"), actions_by_id, default_priority="primary")
        ca_row = _merge_action_with_catalog(intent.get("commit_action"), actions_by_id, default_priority="primary")
        secondary_refs: List[CompressedActionRef] = []
        for sec in intent.get("secondary_actions") or []:
            if not isinstance(sec, dict):
                continue
            row = _merge_action_with_catalog(sec, actions_by_id, default_priority="secondary")
            if row:
                ref = _to_action_ref(row, "secondary")
                if ref:
                    secondary_refs.append(ref)

        ev_refs: List[CompressedEvidenceRef] = []
        for er in intent.get("evidence_refs") or []:
            if isinstance(er, dict) and er.get("source_id") is not None:
                ev_refs.append(
                    CompressedEvidenceRef(
                        evidence_type=str(er.get("evidence_type") or "element_text"),
                        source_id=str(er["source_id"]),
                    )
                )

        action_rows = _intent_action_rows(intent, actions_by_id, pa_row)
        groups.append(
            CompressedIntentGroup(
                intent_id=iid,
                source_group_id=gid or "__whole_state__",
                intent_kind=str(intent.get("intent_kind") or ""),
                intent_name=str(intent.get("intent_name") or ""),
                local_user_goal=str(intent.get("local_user_goal") or ""),
                actions=action_rows,
                primary_action=_to_action_ref(pa_row, "primary") if pa_row else None,
                commit_action=_to_action_ref(ca_row, "primary") if ca_row else None,
                secondary_actions=secondary_refs,
                selection_options=_intent_selection_options(intent),
                local_action_sequence=_flatten_local_action_sequence(intent),
                required_input_element_ids=[str(x) for x in (intent.get("required_input_element_ids") or []) if x],
                feedback_refs=_feedback_ids_from_evidence(ev_refs),
                evidence_refs=ev_refs,
            )
        )
    return groups


def run_build_compressed_catalog(
    *,
    run_id: str,
    state_catalog: List[Dict[str, Any]],
    screen_intent_pkg: Dict[str, Any],
    ui_state_package: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    intents_raw = screen_intent_pkg.get("screen_intent_catalog") or []
    intents_by_state: Dict[str, List[Dict[str, Any]]] = {}
    for row in intents_raw:
        sid = str(row.get("source_state_id") or "")
        if sid:
            intents_by_state.setdefault(sid, []).append(row)

    sip_ref = str(screen_intent_pkg.get("screen_intent_package_id") or "")
    ui_ref = str((ui_state_package or {}).get("ui_state_package_id") or "")

    cards: List[CompressedScreenCard] = []
    trace_index: Dict[str, CompressedTraceIndexEntry] = {}
    total_int_groups = 0

    for state in state_catalog:
        sid = str(state.get("state_id") or "")
        if not sid:
            continue

        actions_by_id = {
            str(a.get("action_id")): a for a in (state.get("available_actions") or []) if a.get("action_id")
        }
        fb_rows = _feedback_rows(state)
        screen_type = normalize_screen_type(state.get("screen_type"))
        taxonomy = CompressedTaxonomy(
            domain=_norm_domain(state.get("domain")),
            screen_type=cast(A1ScreenType, screen_type),
            presentation_scope=_norm_presentation_scope(str(state.get("presentation_scope") or "")),
            outcome_state_type=_norm_outcome_state_type(str(state.get("outcome_state_type") or "")),
        )

        igroups = _build_intent_groups(intents_by_state.get(sid, []), actions_by_id)
        total_int_groups += len(igroups)

        card = CompressedScreenCard(
            state_id=sid,
            screen_purpose=str(state.get("screen_purpose") or ""),
            taxonomy=taxonomy,
            visible_signature=_build_visible_signature(state, fb_rows),
            navigation_cues=_build_navigation_cues(state),
            state_feedback_summary=_build_state_feedback_summary(state),
            form_state_summary=_build_form_state_summary(state),
            continuity_entities=_build_continuity_entities(state),
            intent_groups=igroups,
            evidence_refs=_state_level_evidence_refs(state),
        )
        cards.append(card)

        src_img = str(state.get("source_image_id") or "")
        trace_index[sid] = CompressedTraceIndexEntry(
            source_image_id=src_img,
            ui_state_package_ref=ui_ref,
            screen_intent_package_ref=sip_ref,
        )

    pkg_id = f"cmp_pkg_{uuid.uuid4().hex[:12]}"

    llm_payload = {
        "catalog_version": "compressed_catalog_v2",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [c.model_dump(mode="python") for c in cards],
    }
    char_len = len(json.dumps(llm_payload, ensure_ascii=False))

    dropped_fields = [
        "upload_order",
        "full_visible_elements",
        "full_available_actions_unreferenced",
        "interaction_group_full_evidence",
        "raw_screen_intent_model_output",
    ]

    stats: Dict[str, Any] = {
        "compressed_catalog_package_id": pkg_id,
        "screen_count": len(cards),
        "intent_group_count": total_int_groups,
        "char_count": char_len,
        "token_estimate_div4": max(1, char_len // 4),
        "dropped_fields": dropped_fields,
        # legacy metric keys (optional consumers)
        "catalog_json_char_len": char_len,
    }

    result = CompressedCatalogPackage(
        catalog_version="compressed_catalog_v2",
        catalog_purpose="global_flow_discovery_input",
        compressed_catalog_package_id=pkg_id,
        compressed_catalog=cards,
        trace_index=trace_index,
        compression_stats=stats,
    )

    payload = result.model_dump(mode="python")
    payload.setdefault("warnings", [])
    payload.setdefault("report", {"run_id": run_id})

    return payload


def validate_compressed_catalog_size(
    pkg: Dict[str, Any],
    *,
    max_screens: int,
) -> Tuple[bool, str | None]:
    cat = pkg.get("compressed_catalog") or []
    if len(cat) > max_screens:
        return False, f"COMPRESSED_CATALOG_TOO_LARGE: {len(cat)} screens > limit {max_screens}"
    if not cat:
        return False, "EMPTY_COMPRESSED_CATALOG"
    return True, None
