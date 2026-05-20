"""Shared label normalization and evaluation keys for ui_state_extraction metrics.

Uses `normalize_label` + `(type, label)` keys. Fuzzy anchor matching still uses
`text_normalization_service.normalize_for_match` via `text_match_service`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from experiments.ui_state_extraction.services.text_normalization_service import _PUNCT_STRIP

ElementKey = tuple[str, str]
ActionKey = tuple[str, str]
FeedbackKey = tuple[str, str]
IntentKey = tuple[str, ActionKey]

_KIND_TO_TYPE_FIELD: dict[str, str] = {
    "element": "element_type",
    "action": "action_type",
    "feedback": "feedback_type",
}
_KIND_DEFAULT_TYPE: dict[str, str] = {
    "element": "other",
    "action": "unknown",
    "feedback": "unknown",
}

_HYPHEN_RUN = re.compile(r"-+")


def normalize_label(text: str | None) -> str | None:
    """Strip, lowercase, light punctuation strip, collapse whitespace, spaces -> hyphens."""
    if text is None:
        return None
    s = unicodedata.normalize("NFKC", str(text))
    s = s.lower().strip().translate(_PUNCT_STRIP)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "-")
    s = _HYPHEN_RUN.sub("-", s).strip("-")
    return s if s else None


def primary_text(texts: list[str] | None) -> str | None:
    if not texts:
        return None
    for s in texts:
        t = str(s).strip()
        if t:
            return t
    return None


def _flatten_text_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    return [str(value)]


def _label_texts_from_unit(unit: Any, *, kind: str) -> list[str]:
    if kind not in _KIND_TO_TYPE_FIELD:
        raise ValueError(f"unsupported kind: {kind}")

    out: list[str] = []
    # Actions (GT ActionRecord vs raw Joint dict): prefer model text over grounded anchors so
    # pred and GT share the same key semantics (Sprint 5).
    if kind == "action":
        if isinstance(unit, Mapping):
            sm = unit.get("source_model_texts")
            if isinstance(sm, list):
                out.extend(str(x) for x in sm)
            out.extend(_flatten_text_field(unit.get("text")))
            at = unit.get("anchor_texts")
            if isinstance(at, list):
                out.extend(str(x) for x in at)
            return out
        sm = getattr(unit, "source_model_texts", None)
        if sm:
            out.extend(str(x) for x in sm)
        tx = getattr(unit, "text", None)
        if tx is not None:
            out.extend(_flatten_text_field(tx))
        at = getattr(unit, "anchor_texts", None)
        if at:
            out.extend(str(x) for x in at)
        return out

    if isinstance(unit, Mapping):
        out.extend(_flatten_text_field(unit.get("text")))
        at = unit.get("anchor_texts")
        if isinstance(at, list):
            out.extend(str(x) for x in at)
        return out

    tx = getattr(unit, "text", None)
    if tx is not None:
        out.extend(_flatten_text_field(tx))
    at = getattr(unit, "anchor_texts", None)
    if at:
        out.extend(str(x) for x in at)
    return out


def _type_part(unit: Any, *, kind: str) -> str:
    field = _KIND_TO_TYPE_FIELD[kind]
    default = _KIND_DEFAULT_TYPE[kind]
    if isinstance(unit, Mapping):
        return str(unit.get(field) or default)
    return str(getattr(unit, field, None) or default)


def element_key(unit: Any) -> ElementKey | None:
    label = normalize_label(primary_text(_label_texts_from_unit(unit, kind="element")))
    if not label:
        return None
    return (_type_part(unit, kind="element"), label)


def action_key(unit: Any) -> ActionKey | None:
    label = normalize_label(primary_text(_label_texts_from_unit(unit, kind="action")))
    if not label:
        return None
    return (_type_part(unit, kind="action"), label)


def feedback_key(unit: Any) -> FeedbackKey | None:
    label = normalize_label(primary_text(_label_texts_from_unit(unit, kind="feedback")))
    if not label:
        return None
    return (_type_part(unit, kind="feedback"), label)


_ACTION_ID_FIELDS = (
    "gt_action_id",
    "source_model_action_id",
    "pred_action_id",
    "action_id",
)


def build_action_lookup_by_id(actions: Iterable[Any]) -> dict[str, Any]:
    """Index each action by every id field present (GT, pred, or raw dict)."""
    out: dict[str, Any] = {}
    for a in actions:
        if isinstance(a, Mapping):
            aid = str(a.get("action_id", "")).strip()
            if aid:
                out[aid] = a
            continue
        for attr in _ACTION_ID_FIELDS:
            v = getattr(a, attr, None)
            if v is not None:
                s = str(v).strip()
                if s:
                    out[s] = a
    return out


def _commit_action_ref(intent: Any) -> str:
    if isinstance(intent, Mapping):
        v = intent.get("commit_action_id")
        if v is None:
            v = intent.get("commit_pred_action_id")
        return str(v or "").strip()
    ca = getattr(intent, "commit_action_id", None)
    if ca is None:
        ca = getattr(intent, "commit_pred_action_id", None)
    return str(ca).strip() if ca is not None else ""


def intent_key(intent: Any, action_lookup: Mapping[str, Any]) -> IntentKey | None:
    commit_id = _commit_action_ref(intent)
    if isinstance(intent, Mapping):
        ik = str(intent.get("intent_kind") or "").strip()
    else:
        ik = str(getattr(intent, "intent_kind", "") or "").strip()

    if not commit_id or not ik:
        return None
    commit_action = action_lookup.get(commit_id)
    if commit_action is None:
        return None
    ck = action_key(commit_action)
    if not ck:
        return None
    return (ik, ck)


def has_evaluable_key(unit: Any, *, kind: str) -> bool:
    """True if this unit yields a non-empty evaluation key (typed + label)."""
    if kind == "element":
        return element_key(unit) is not None
    if kind == "action":
        return action_key(unit) is not None
    if kind == "feedback":
        return feedback_key(unit) is not None
    raise ValueError(f"unsupported kind: {kind}")


def summarize_evaluation_keys(doc: Any) -> dict[str, Any]:
    """Runtime summary of evaluation keys for debug (keys are not persisted on GT records)."""
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        TempGroundTruthDocument,
    )

    if not isinstance(doc, TempGroundTruthDocument):
        raise TypeError("summarize_evaluation_keys expects TempGroundTruthDocument")

    ac_lut = build_action_lookup_by_id(doc.actions)

    def fmt_pair(k: tuple[str, str] | None) -> str | None:
        if k is None:
            return None
        return f"({k[0]}, {k[1]})"

    elements_map = {el.gt_element_id: fmt_pair(element_key(el)) for el in doc.elements}
    actions_map = {ac.gt_action_id: fmt_pair(action_key(ac)) for ac in doc.actions}
    feedback_map = {fb.gt_feedback_id: fmt_pair(feedback_key(fb)) for fb in doc.feedback}
    intents_map: dict[str, str | None] = {}
    for it in doc.screen_intents:
        ik = intent_key(it, ac_lut)
        if ik is None:
            intents_map[it.gt_intent_id] = None
        else:
            kind_s, ck = ik
            intents_map[it.gt_intent_id] = f"({kind_s}, {fmt_pair(ck)})"

    return {
        "elements": elements_map,
        "actions": actions_map,
        "feedback": feedback_map,
        "intents": intents_map,
    }
