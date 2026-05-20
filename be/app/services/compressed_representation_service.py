"""Noise-stripped packaging of Phase 1+2 artefacts for batched global flow discovery."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Tuple, cast

from app.constants.ui_screen_taxonomy import normalize_screen_type
from app.constants.ui_state_taxonomy import (
    normalize_domain,
    normalize_feedback_type,
    normalize_outcome_state_type,
    normalize_presentation_scope,
)
from app.model_providers.schemas import (
    A1FeedbackType,
    A1OutcomeStateType,
    A1PresentationScope,
    A1ScreenType,
    CompressedCatalogPackage,
    CompressedDiscoveryEvidenceCard,
    CompressedTaxonomy,
    CompressedTraceIndexEntry,
)

_ELEMENT_KEYS: frozenset[str] = frozenset({"element_id", "element_type", "role_hint", "text"})
_ACTION_KEYS: frozenset[str] = frozenset({"action_id", "action_type", "text", "action_priority"})
_FEEDBACK_KEYS: frozenset[str] = frozenset({"feedback_id", "feedback_type", "text", "related_element_ids"})
_GROUP_KEYS: frozenset[str] = frozenset(
    {
        "group_id",
        "group_type",
        "group_label",
        "element_ids",
        "action_ids",
        "feedback_ids",
        "primary_action_id",
    }
)


def _norm_domain(raw: str | None) -> str:
    return normalize_domain(raw)


def _norm_presentation_scope(raw: str | None) -> A1PresentationScope:
    return cast(A1PresentationScope, normalize_presentation_scope(raw))


def _norm_outcome_state_type(raw: str | None) -> A1OutcomeStateType:
    return cast(A1OutcomeStateType, normalize_outcome_state_type(raw))


def _norm_feedback_type(raw: str | None) -> A1FeedbackType:
    return cast(A1FeedbackType, normalize_feedback_type(raw))


def _project_dict(row: Dict[str, Any], keep: frozenset[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in keep:
        if k not in row:
            continue
        v = row[k]
        if v is None:
            continue
        out[k] = v
    return out


def _filter_visible_elements(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for el in raw or []:
        if not isinstance(el, dict):
            continue
        slim = _project_dict(el, _ELEMENT_KEYS)
        if not slim:
            continue
        tx = slim.get("text")
        if isinstance(tx, list):
            slim["text"] = [str(t) for t in tx if str(t).strip()]
        elif tx is not None:
            slim["text"] = [str(tx).strip()] if str(tx).strip() else []
        else:
            slim["text"] = []
        out.append(slim)
    return out


def _filter_actions(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in raw or []:
        if not isinstance(a, dict):
            continue
        slim = _project_dict(a, _ACTION_KEYS)
        if not slim.get("action_id"):
            continue
        tx = slim.get("text")
        if isinstance(tx, list):
            slim["text"] = [str(t) for t in tx if str(t).strip()]
        elif tx is not None:
            slim["text"] = [str(tx).strip()] if str(tx).strip() else []
        else:
            slim["text"] = []
        out.append(slim)
    return out


def _filter_feedback(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fb in raw or []:
        if not isinstance(fb, dict):
            continue
        if not fb.get("feedback_id"):
            continue
        slim = _project_dict(fb, _FEEDBACK_KEYS)
        slim["feedback_type"] = _norm_feedback_type(str(slim.get("feedback_type") or ""))
        rel = slim.get("related_element_ids")
        if isinstance(rel, list):
            slim["related_element_ids"] = [str(x) for x in rel if x]
        else:
            slim["related_element_ids"] = []
        tx = slim.get("text")
        if isinstance(tx, list):
            slim["text"] = [str(t) for t in tx if str(t).strip()]
        elif tx is not None:
            slim["text"] = [str(tx).strip()] if str(tx).strip() else []
        else:
            slim["text"] = []
        out.append(slim)
    return out


def _filter_interaction_groups(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for g in raw or []:
        if not isinstance(g, dict):
            continue
        if not g.get("group_id"):
            continue
        slim = _project_dict(g, _GROUP_KEYS)
        for key in ("element_ids", "action_ids", "feedback_ids"):
            v = slim.get(key)
            if isinstance(v, list):
                slim[key] = [str(x) for x in v if x]
            else:
                slim[key] = []
        out.append(slim)
    return out


def _taxonomy_from_state(state: Dict[str, Any]) -> CompressedTaxonomy:
    screen_type = normalize_screen_type(state.get("screen_type"))
    return CompressedTaxonomy(
        domain=_norm_domain(state.get("domain")),
        screen_type=cast(A1ScreenType, screen_type),
        presentation_scope=_norm_presentation_scope(str(state.get("presentation_scope") or "")),
        outcome_state_type=_norm_outcome_state_type(str(state.get("outcome_state_type") or "")),
    )


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
        if not isinstance(row, dict):
            continue
        sid = str(row.get("source_state_id") or "")
        if sid:
            intents_by_state.setdefault(sid, []).append(dict(row))

    sip_ref = str(screen_intent_pkg.get("screen_intent_package_id") or "")
    ui_ref = str((ui_state_package or {}).get("ui_state_package_id") or "")

    cards: List[CompressedDiscoveryEvidenceCard] = []
    trace_index: Dict[str, CompressedTraceIndexEntry] = {}

    for state in state_catalog:
        sid = str(state.get("state_id") or "")
        if not sid:
            continue

        card = CompressedDiscoveryEvidenceCard(
            state_id=sid,
            screen_purpose=str(state.get("screen_purpose") or ""),
            taxonomy=_taxonomy_from_state(state),
            visible_elements=_filter_visible_elements(state.get("visible_elements")),
            available_actions=_filter_actions(state.get("available_actions")),
            visible_feedback=_filter_feedback(state.get("visible_feedback")),
            interaction_groups=_filter_interaction_groups(state.get("interaction_groups")),
            screen_intents=intents_by_state.get(sid, []),
        )
        cards.append(card)

        trace_index[sid] = CompressedTraceIndexEntry(
            source_image_id=str(state.get("source_image_id") or ""),
            ui_state_package_ref=ui_ref,
            screen_intent_package_ref=sip_ref,
        )

    pkg_id = f"cmp_pkg_{uuid.uuid4().hex[:12]}"

    llm_payload = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [c.model_dump(mode="python") for c in cards],
    }
    char_len = len(json.dumps(llm_payload, ensure_ascii=False))

    dropped_fields = [
        "upload_order",
        "visual_region",
        "bbox_coordinates",
        "group_evidence",
        "group_confidence",
        "raw_screen_intent_model_output",
    ]

    stats: Dict[str, Any] = {
        "compressed_catalog_package_id": pkg_id,
        "screen_count": len(cards),
        "intent_row_count": sum(len(c.screen_intents) for c in cards),
        "char_count": char_len,
        "token_estimate_div4": max(1, char_len // 4),
        "dropped_fields": dropped_fields,
        "catalog_json_char_len": char_len,
    }

    result = CompressedCatalogPackage(
        catalog_version="compressed_catalog_v3",
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
