"""Build production-shaped state_catalog rows from normalized joint ui_state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from experiments.flow_discovery.adapters import system_readonly_adapter
from experiments.flow_discovery.input_builder.experiment_id_factory import ExperimentIdFactory
from experiments.flow_discovery.schemas.input_builder_schema import NormalizedJointOutput

_UI_STATE_KEYS = (
    "screen_purpose",
    "page_purpose",
    "purpose",
    "screen_name",
)
_ELEM_KEYS = ("visible_elements", "elements", "ui_elements")
_ACT_KEYS = ("available_actions", "actions", "actionable_elements")
_FB_KEYS = ("visible_feedback", "feedback", "messages", "validation_messages")
_GRP_KEYS = ("interaction_groups", "groups")


def _first_str(d: Mapping[str, Any], keys: tuple[str, ...], *, default: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() != "null":
            return s
    return default


def _merge_list(ui: Mapping[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for k in keys:
        v = ui.get(k)
        if isinstance(v, list):
            return list(v)
    return []


def _infer_outcome(ui: Mapping[str, Any], feedbacks: list[Any]) -> str | None:
    if _first_str(ui, ("outcome_state_type", "state_type"), default=""):
        return None
    text_blob = ""
    for fb in feedbacks:
        if not isinstance(fb, dict):
            continue
        fbt = str(fb.get("feedback_type") or "").lower()
        if fbt == "validation_error":
            return "validation_error"
        if fbt == "error":
            return "error"
        for t in fb.get("text") or []:
            text_blob += " " + str(t).lower()
    purpose = _first_str(ui, _UI_STATE_KEYS, default="").lower()
    if "success" in purpose or "success" in text_blob:
        return "success"
    return None


def _sanitize_screen_type(token: str) -> str:
    return system_readonly_adapter.normalize_screen_type(token or None)


def _coerce_element(raw: Any, id_factory: ExperimentIdFactory, state_id: str, idx: int) -> dict[str, Any]:
    el = dict(raw) if isinstance(raw, dict) else {}
    eid = str(el.get("element_id") or "").strip()
    if not eid:
        eid = id_factory.fallback_element_id(state_id, idx)
        el["element_id"] = eid
    el.setdefault("element_type", "other")
    el.setdefault("text", [])
    if not isinstance(el["text"], list):
        el["text"] = [str(el["text"])]
    el.setdefault("role_hint", None)
    el.setdefault("visual_region", "unknown")
    return el


def _coerce_action(raw: Any, id_factory: ExperimentIdFactory, state_id: str, idx: int) -> dict[str, Any]:
    ac = dict(raw) if isinstance(raw, dict) else {}
    aid = str(ac.get("action_id") or "").strip()
    if not aid:
        aid = id_factory.fallback_action_id(state_id, idx)
        ac["action_id"] = aid
    ac.setdefault("action_type", "unknown")
    ac.setdefault("text", [])
    if not isinstance(ac["text"], list):
        ac["text"] = [str(ac["text"])]
    ac.setdefault("action_priority", None)
    ac.setdefault("visual_region", "unknown")
    return ac


def _coerce_feedback(raw: Any, id_factory: ExperimentIdFactory, state_id: str, idx: int) -> dict[str, Any]:
    fb = dict(raw) if isinstance(raw, dict) else {}
    fid = str(fb.get("feedback_id") or "").strip()
    if not fid:
        fid = id_factory.fallback_feedback_id(state_id, idx)
        fb["feedback_id"] = fid
    fb.setdefault("feedback_type", "unknown")
    fb.setdefault("text", [])
    if not isinstance(fb["text"], list):
        fb["text"] = [str(fb["text"])]
    fb.setdefault("related_element_ids", [])
    fb.setdefault("visual_region", "unknown")
    return fb


def _coerce_group(
    raw: Any,
    id_factory: ExperimentIdFactory,
    state_id: str,
    idx: int,
) -> dict[str, Any]:
    g = dict(raw) if isinstance(raw, dict) else {}
    gid = str(g.get("group_id") or "").strip()
    if not gid:
        gid = id_factory.fallback_group_id(state_id, idx)
        g["group_id"] = gid
    gt = str(g.get("group_type") or "content_section").strip().lower()
    if gt == "whole_state":
        gt = "content_section"
    g["group_type"] = gt
    g.setdefault("group_label", None)
    for k in ("element_ids", "action_ids", "feedback_ids"):
        v = g.get(k)
        if isinstance(v, list):
            g[k] = [str(x) for x in v if str(x).strip()]
        else:
            g[k] = []
    g.setdefault("primary_action_id", None)
    g.setdefault("group_evidence", [])
    g.setdefault("group_confidence", "low")
    return g


def _experiment_interaction_group_fallback(
    elements: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    feedbacks: list[dict[str, Any]],
    purpose: str,
    id_factory: ExperimentIdFactory,
    state_id: str,
) -> dict[str, Any]:
    has_submit = any(str(a.get("action_type") or "") == "submit" for a in actions)
    has_input = any(
        str(e.get("element_type") or "") in ("input", "textarea", "select", "checkbox", "radio") for e in elements
    )
    if has_input or has_submit:
        el_ids = [str(e["element_id"]) for e in elements if e.get("element_id")]
        input_ids = [
            str(e["element_id"])
            for e in elements
            if str(e.get("element_type") or "") in ("input", "textarea", "select", "checkbox", "radio")
            and e.get("element_id")
        ]
        primary_aid = None
        for a in actions:
            if str(a.get("action_type") or "") == "submit" and a.get("action_id"):
                primary_aid = str(a["action_id"])
                break
        if not primary_aid:
            for a in actions:
                if str(a.get("action_priority") or "").lower() == "primary" and a.get("action_id"):
                    primary_aid = str(a["action_id"])
                    break
        act_ids = [str(a["action_id"]) for a in actions if a.get("action_id")]
        fb_ids = [str(f["feedback_id"]) for f in feedbacks if f.get("feedback_id")]
        raw_grp = {
            "group_id": id_factory.fallback_group_id(state_id, 0),
            "group_type": "form",
            "group_label": purpose or "Form",
            "element_ids": input_ids or el_ids,
            "action_ids": act_ids,
            "feedback_ids": fb_ids,
            "primary_action_id": primary_aid,
            "group_evidence": [],
            "group_confidence": "low",
        }
        return _coerce_group(raw_grp, id_factory, state_id, 0)
    el_ids = [str(e["element_id"]) for e in elements if e.get("element_id")]
    act_ids = [str(a["action_id"]) for a in actions if a.get("action_id")]
    fb_ids = [str(f["feedback_id"]) for f in feedbacks if f.get("feedback_id")]
    primary_aid = None
    if actions:
        primary_aid = str(actions[0].get("action_id") or "") or None
    raw_grp = {
        "group_id": id_factory.fallback_group_id(state_id, 0),
        "group_type": "content_section",
        "group_label": purpose or "Screen",
        "element_ids": el_ids,
        "action_ids": act_ids,
        "feedback_ids": fb_ids,
        "primary_action_id": primary_aid,
        "group_evidence": [],
        "group_confidence": "low",
    }
    return _coerce_group(raw_grp, id_factory, state_id, 0)


def _dedupe_codes(ids: list[str], code: str, warnings: list[str]) -> None:
    seen: set[str] = set()
    dups: set[str] = set()
    for i in ids:
        if not i:
            continue
        if i in seen:
            dups.add(i)
        seen.add(i)
    if dups:
        warnings.append(f"{code}:{sorted(dups)[:8]}")


def _validate_group_refs(state: dict[str, Any], warnings: list[str]) -> None:
    elem_ids = {str(e.get("element_id")) for e in (state.get("visible_elements") or []) if isinstance(e, dict)}
    act_ids = {str(a.get("action_id")) for a in (state.get("available_actions") or []) if isinstance(a, dict)}
    fb_ids = {str(f.get("feedback_id")) for f in (state.get("visible_feedback") or []) if isinstance(f, dict)}
    for g in state.get("interaction_groups") or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("group_id") or "")
        for eid in g.get("element_ids") or []:
            if str(eid) not in elem_ids:
                warnings.append(f"GROUP_REF_UNKNOWN_ELEMENT:{gid}:{eid}")
        for aid in g.get("action_ids") or []:
            if str(aid) not in act_ids:
                warnings.append(f"GROUP_REF_UNKNOWN_ACTION:{gid}:{aid}")
        for fid in g.get("feedback_ids") or []:
            if str(fid) not in fb_ids:
                warnings.append(f"GROUP_REF_UNKNOWN_FEEDBACK:{gid}:{fid}")
        pa = g.get("primary_action_id")
        if pa and str(pa) not in act_ids:
            warnings.append(f"GROUP_REF_UNKNOWN_ACTION:{gid}:primary:{pa}")


def _validate_state_row(state: dict[str, Any], warnings: list[str]) -> None:
    if not str(state.get("state_id") or "").strip():
        warnings.append("EMPTY_STATE_ID")
    if not str(state.get("source_image_id") or "").strip():
        warnings.append("EMPTY_SOURCE_IMAGE_ID_ROW")
    for key, label in (
        ("visible_elements", "VISIBLE_ELEMENTS_NOT_LIST"),
        ("available_actions", "AVAILABLE_ACTIONS_NOT_LIST"),
        ("visible_feedback", "VISIBLE_FEEDBACK_NOT_LIST"),
        ("interaction_groups", "INTERACTION_GROUPS_NOT_LIST"),
    ):
        if not isinstance(state.get(key), list):
            warnings.append(label)
    elems = state.get("visible_elements") or []
    acts = state.get("available_actions") or []
    fbs = state.get("visible_feedback") or []
    grps = state.get("interaction_groups") or []
    _dedupe_codes(
        [str(e.get("element_id")) for e in elems if isinstance(e, dict) and e.get("element_id")],
        "DUPLICATE_ELEMENT_ID",
        warnings,
    )
    _dedupe_codes(
        [str(a.get("action_id")) for a in acts if isinstance(a, dict) and a.get("action_id")],
        "DUPLICATE_ACTION_ID",
        warnings,
    )
    _dedupe_codes(
        [str(f.get("feedback_id")) for f in fbs if isinstance(f, dict) and f.get("feedback_id")],
        "DUPLICATE_FEEDBACK_ID",
        warnings,
    )
    _dedupe_codes(
        [str(g.get("group_id")) for g in grps if isinstance(g, dict) and g.get("group_id")],
        "DUPLICATE_GROUP_ID",
        warnings,
    )
    _validate_group_refs(state, warnings)


class ExperimentStateCatalogBuilder:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    def build_state_catalog(
        self,
        normalized_outputs: list[NormalizedJointOutput],
        id_factory: ExperimentIdFactory,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        all_warnings: list[str] = []
        fallback_group_count = 0

        sorted_norm = sorted(normalized_outputs, key=lambda x: x.raw_file_name)
        for idx, norm in enumerate(sorted_norm, start=1):
            row_warnings: list[str] = []
            ui = dict(norm.ui_state)
            source_image_id = norm.source_image_id

            purpose = _first_str(ui, _UI_STATE_KEYS, default=source_image_id)
            domain = _first_str(ui, ("domain",), default=self._app_id)
            raw_screen = _first_str(ui, ("screen_type", "page_type"), default="")
            canonical = _sanitize_screen_type(raw_screen if raw_screen else None)
            pres = str(ui.get("presentation_scope") or "").strip().lower() or "unknown"
            if pres in ("page", ""):
                pres = "full_screen"
            elif pres not in (
                "full_screen",
                "modal",
                "drawer",
                "popover",
                "toast",
                "banner",
                "inline",
                "overlay",
                "unknown",
            ):
                pres = "unknown"
            out_raw = _first_str(ui, ("outcome_state_type", "state_type"), default="")
            inferred = _infer_outcome(ui, _merge_list(ui, _FB_KEYS))
            if out_raw.lower() in ("normal",):
                outcome = "neutral"
            elif out_raw:
                outcome = out_raw
            elif inferred:
                outcome = inferred
            else:
                outcome = "neutral"

            elems_raw = _merge_list(ui, _ELEM_KEYS)
            acts_raw = _merge_list(ui, _ACT_KEYS)
            fbs_raw = _merge_list(ui, _FB_KEYS)
            grps_raw = _merge_list(ui, _GRP_KEYS)

            state_id = id_factory.state_id(source_image_id, idx)
            elements = [_coerce_element(e, id_factory, state_id, i) for i, e in enumerate(elems_raw)]
            actions = [_coerce_action(a, id_factory, state_id, i) for i, a in enumerate(acts_raw)]
            feedbacks = [_coerce_feedback(f, id_factory, state_id, i) for i, f in enumerate(fbs_raw)]

            groups = [_coerce_group(g, id_factory, state_id, i) for i, g in enumerate(grps_raw)]

            used_experiment_fallback = False
            if not groups and (elements or actions or feedbacks):
                groups = [
                    _experiment_interaction_group_fallback(
                        elements,
                        actions,
                        feedbacks,
                        purpose,
                        id_factory,
                        state_id,
                    ),
                ]
                used_experiment_fallback = True
                row_warnings.append("EXPERIMENT_INTERACTION_GROUP_FALLBACK_USED")
                fallback_group_count += 1

            ui_model = None
            ui_payload = {
                "state_id": state_id,
                "screen_purpose": purpose,
                "presentation_scope": pres,
                "screen_type": canonical,
                "outcome_state_type": outcome,
                "domain": domain,
                "visible_elements": elements,
                "available_actions": actions,
                "visible_feedback": feedbacks,
                "interaction_groups": groups,
            }
            try:
                ui_model = system_readonly_adapter.UIStateExtractionV2Result.model_validate(ui_payload)
            except ValidationError:
                ui_payload["screen_type"] = "other"
                ui_payload["presentation_scope"] = "unknown"
                try:
                    ui_model = system_readonly_adapter.UIStateExtractionV2Result.model_validate(ui_payload)
                except ValidationError:
                    ui_payload["visible_elements"] = []
                    ui_payload["available_actions"] = []
                    ui_payload["visible_feedback"] = []
                    ui_payload["interaction_groups"] = []
                    ui_model = system_readonly_adapter.UIStateExtractionV2Result.model_validate(ui_payload)
                    row_warnings.append("UI_STATE_COERCED_EMPTY_AFTER_VALIDATION_FAILURE")
            system_readonly_adapter.ensure_fallback_interaction_groups(ui_model)
            system_readonly_adapter.prefix_ui_state_ids(state_id, ui_model)

            extraction_status = (
                "success" if (ui_model.visible_elements or ui_model.available_actions) else "partial"
            )
            if not ui_model.screen_purpose or ui_model.screen_purpose == "null":
                extraction_status = "failed"

            state_row: dict[str, Any] = {
                "extraction_status": extraction_status,
                "state_id": state_id,
                "upload_order": idx,
                "source_image_id": source_image_id,
                "page_type": canonical,
                "screen_type": canonical,
                "presentation_scope": str(ui_model.presentation_scope),
                "outcome_state_type": str(ui_model.outcome_state_type),
                "screen_purpose": ui_model.screen_purpose,
                "domain": ui_model.domain,
                "state_summary": ui_model.screen_purpose,
                "visible_texts": [],
                "visible_elements": [e.model_dump() for e in ui_model.visible_elements],
                "available_actions": [a.model_dump() for a in ui_model.available_actions],
                "visible_feedback": [f.model_dump() for f in ui_model.visible_feedback],
                "interaction_groups": [ig.model_dump() for ig in ui_model.interaction_groups],
                "state_quality": {},
            }
            _validate_state_row(state_row, row_warnings)
            all_warnings.extend(row_warnings)
            rows.append(state_row)

        report = {
            "state_count": len(rows),
            "warnings": all_warnings,
            "experiment_fallback_group_count": fallback_group_count,
        }
        return rows, report


__all__ = ["ExperimentStateCatalogBuilder"]
