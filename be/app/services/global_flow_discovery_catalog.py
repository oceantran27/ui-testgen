"""Build trimmed `llm_discovery_catalog` for global flow discovery LLM input."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _serialize_action_rows(raw: Any) -> List[List[str]]:
    out: List[List[str]] = []
    for row in raw or []:
        if isinstance(row, (list, tuple)) and len(row) >= 5:
            out.append([str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4])])
    return out


def build_llm_discovery_catalog(compressed_catalog_package: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strip audit-heavy fields from compressed_catalog — only behavioural signals for composition.

    Omits trace_index, compression_stats, evidence-heavy intent fields, form_state_summary, etc.
    """
    raw_cards = compressed_catalog_package.get("compressed_catalog") or []
    states: List[Dict[str, Any]] = []

    for c in raw_cards:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("state_id") or "").strip()
        if not sid:
            continue

        igroups: List[Dict[str, Any]] = []
        for g in c.get("intent_groups") or []:
            if not isinstance(g, dict):
                continue
            pa_raw = g.get("primary_action") or g.get("commit_action")
            primary: Dict[str, Any] | None = None
            if isinstance(pa_raw, dict):
                primary = {
                    "action_id": str(pa_raw.get("action_id") or ""),
                    "action_type": str(pa_raw.get("action_type") or ""),
                    "text": [str(x) for x in (pa_raw.get("text") or []) if x is not None],
                }
            primary_id = ""
            if isinstance(pa_raw, dict):
                primary_id = str(pa_raw.get("action_id") or "")

            igroups.append(
                {
                    "intent_id": str(g.get("intent_id") or ""),
                    "iid": str(g.get("intent_id") or ""),
                    "intent_kind": str(g.get("intent_kind") or ""),
                    "kind": str(g.get("intent_kind") or ""),
                    "local_user_goal": str(g.get("local_user_goal") or ""),
                    "goal": str(g.get("local_user_goal") or ""),
                    "primary": primary_id,
                    "primary_action": primary,
                    "actions": _serialize_action_rows(g.get("actions")),
                    "required_input_element_ids": [
                        str(x) for x in (g.get("required_input_element_ids") or []) if x is not None
                    ],
                }
            )

        states.append(
            {
                "state_id": sid,
                "screen_purpose": str(c.get("screen_purpose") or ""),
                "taxonomy": dict(c.get("taxonomy") or {}),
                "visible_signature": dict(c.get("visible_signature") or {}),
                "navigation_cues": dict(c.get("navigation_cues") or {}),
                "continuity_entities": list(c.get("continuity_entities") or []),
                "state_feedback_summary": list(c.get("state_feedback_summary") or []),
                "intent_groups": igroups,
            }
        )

    return {
        "catalog_version": compressed_catalog_package.get("catalog_version") or "compressed_catalog_v2",
        "catalog_purpose": compressed_catalog_package.get("catalog_purpose") or "global_flow_discovery_input",
        "states": states,
    }


def validate_discovery_input(llm_catalog: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Structural checks before calling the LLM."""
    errs: List[str] = []
    if not isinstance(llm_catalog, dict):
        return False, ["INVALID_LLM_CATALOG"]

    states = llm_catalog.get("states")
    if not isinstance(states, list) or not states:
        return False, ["EMPTY_STATES"]

    seen: set[str] = set()
    for i, s in enumerate(states):
        if not isinstance(s, dict):
            errs.append(f"INVALID_STATE_ROW:{i}")
            continue
        sid = str(s.get("state_id") or "").strip()
        if not sid:
            errs.append(f"MISSING_STATE_ID_AT:{i}")
            continue
        if sid in seen:
            errs.append(f"DUPLICATE_STATE_ID:{sid}")
            continue
        seen.add(sid)

    return (len(errs) == 0, errs)


def catalog_state_ids_from_llm_catalog(llm_catalog: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for s in llm_catalog.get("states") or []:
        if isinstance(s, dict) and s.get("state_id"):
            out.add(str(s.get("state_id")))
    return out


def catalog_state_ids_from_compressed_pkg(pkg: Dict[str, Any]) -> set[str]:
    """Derive valid state ids from the raw compressed package (same as LLM catalogue states)."""

    return catalog_state_ids_from_llm_catalog(build_llm_discovery_catalog(pkg))
