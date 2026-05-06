"""Parse UI extraction JSON from stage-1 model output."""

from __future__ import annotations

import json

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.ui_extraction import UIExtractionResult, UISemanticGroup


def _non_empty_str(v: object) -> str | None:
    if not isinstance(v, str):
        return None
    s = v.strip()
    return s if s else None


def _normalize_ui_extraction_dict(data: dict) -> None:
    """Coerce legacy ui-flat-v4 shapes; strip obsolete overview keys; fix loose group nests."""
    overview = data.get("overview")
    if isinstance(overview, dict):
        if "viewport_description" not in overview and "page" in overview:
            overview["viewport_description"] = overview["page"]
        overview.pop("page", None)
        overview.pop("control_count", None)

    controls = data.get("controls")
    if isinstance(controls, list):
        for c in controls:
            if not isinstance(c, dict):
                continue
            if "value" not in c and "text" in c:
                c["value"] = c.get("text", "")
            c.pop("text", None)

            if "is_primary_layer" not in c and "scope" in c:
                c["is_primary_layer"] = bool(c.get("scope"))
            c.pop("scope", None)

            legacy_selected = c.pop("selected", None)
            states = c.get("states")
            if not isinstance(states, dict):
                states = {}
                c["states"] = states
            if legacy_selected is not None and "selected" not in states:
                states["selected"] = legacy_selected

    groups = data.get("groups")
    if not isinstance(groups, list):
        return
    for g in groups:
        if not isinstance(g, dict):
            continue

        search = g.get("search")
        if isinstance(search, dict):
            inp = _non_empty_str(search.get("input"))
            trg = _non_empty_str(search.get("trigger"))
            if inp is None or trg is None:
                g.pop("search", None)
            else:
                search["input"] = inp
                search["trigger"] = trg

        content = g.get("content")
        if isinstance(content, dict):
            pat = _non_empty_str(content.get("pattern"))
            sample = _non_empty_str(content.get("sample"))
            if pat is None or sample is None:
                g.pop("content", None)
            else:
                content["pattern"] = pat
                content["sample"] = sample

        destinations = g.get("destinations")
        if isinstance(destinations, list):
            cleaned: list[dict] = []
            for d in destinations:
                if not isinstance(d, dict):
                    continue
                ctl = _non_empty_str(d.get("control"))
                lab = _non_empty_str(d.get("label"))
                if ctl is None or lab is None:
                    continue
                cleaned.append({"control": ctl, "label": lab})
            if cleaned:
                g["destinations"] = cleaned
            else:
                g.pop("destinations", None)


def parse_ui_extraction_payload(raw: str) -> UIExtractionResult:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse UI extraction JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid UI extraction JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("UI extraction output must be a JSON object")
    _normalize_ui_extraction_dict(data)
    try:
        return UIExtractionResult.model_validate(data)
    except Exception as exc:
        raise AIProcessingError(f"Invalid UI extraction payload shape: {exc}") from exc


def ui_extraction_to_minified_json(result: UIExtractionResult) -> str:
    """Stable JSON string for downstream text-only stages (includes ``is_primary_layer`` on controls)."""
    return json.dumps(
        result.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _filter_optional_id_list(ids: list[str] | None, kept_ids: set[str]) -> list[str] | None:
    if not ids:
        return None
    out = [x for x in ids if x in kept_ids]
    return out if out else None


def filter_scoped_ui_extraction(result: UIExtractionResult) -> UIExtractionResult:
    """
    Drop every control with ``is_primary_layer=False`` and prune group references so all ids
    remain valid. Used before the user-intents LLM stage; full extraction should
    still be persisted separately for audit.
    """
    kept_ids = {c.id for c in result.controls if c.is_primary_layer}
    new_controls = [c for c in result.controls if c.is_primary_layer]
    new_groups: list[UISemanticGroup] = []
    for g in result.groups:
        controls = [x for x in g.controls if x in kept_ids]
        primary_actions = _filter_optional_id_list(g.primary_actions, kept_ids)
        filters = _filter_optional_id_list(g.filters, kept_ids)
        sorts = _filter_optional_id_list(g.sorts, kept_ids)
        pagination = _filter_optional_id_list(g.pagination, kept_ids)
        search = g.search
        if search is not None and (
            search.input not in kept_ids or search.trigger not in kept_ids
        ):
            search = None
        destinations = None
        if g.destinations:
            dests = [d for d in g.destinations if d.control in kept_ids]
            destinations = dests if dests else None
        new_groups.append(
            UISemanticGroup(
                id=g.id,
                summary=g.summary,
                controls=controls,
                primary_actions=primary_actions,
                search=search,
                filters=filters,
                sorts=sorts,
                pagination=pagination,
                destinations=destinations,
                content=g.content,
            )
        )
    overview = result.overview
    return UIExtractionResult(
        schema_version=result.schema_version,
        overview=overview,
        controls=new_controls,
        groups=new_groups,
    )


def user_intent_input_to_minified_json(result: UIExtractionResult) -> str:
    """
    JSON for ``generate_user_intents_openai_sync``: caller should pass output of
    ``filter_scoped_ui_extraction``; ``is_primary_layer`` is omitted from each control object.
    """
    data = result.model_dump(mode="json", exclude_none=True)
    for row in data.get("controls", []):
        if isinstance(row, dict):
            row.pop("is_primary_layer", None)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
