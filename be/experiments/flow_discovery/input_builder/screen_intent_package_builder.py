"""Assemble screen_intent_package from normalized joint outputs."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError

from experiments.flow_discovery import config
from experiments.flow_discovery.adapters import system_readonly_adapter
from experiments.flow_discovery.input_builder.experiment_id_factory import ExperimentIdFactory
from experiments.flow_discovery.schemas.input_builder_schema import NormalizedJointOutput


def _first_group_id(state: dict[str, Any]) -> str:
    grps = state.get("interaction_groups") or []
    if grps and isinstance(grps[0], dict):
        return str(grps[0].get("group_id") or "")
    return ""


def _first_submit_action(state: dict[str, Any]) -> dict[str, Any] | None:
    for a in state.get("available_actions") or []:
        if isinstance(a, dict) and str(a.get("action_type") or "") == "submit":
            return a
    for a in state.get("available_actions") or []:
        if isinstance(a, dict) and a.get("action_id"):
            return a
    return None


def _synthetic_intent_row(
    state_row: dict[str, Any],
    id_factory: ExperimentIdFactory,
) -> dict[str, Any]:
    gid = _first_group_id(state_row)
    act = _first_submit_action(state_row)
    action_id = str(act.get("action_id") or "") if act else ""
    action_type = str(act.get("action_type") or "submit") if act else "submit"
    text = act.get("text") if act and isinstance(act.get("text"), list) else (["Submit"] if act else [])
    primary = (
        {"action_id": action_id, "action_type": action_type, "text": text}
        if action_id
        else None
    )
    purpose = str(state_row.get("screen_purpose") or "screen")
    commit = (
        {"action_id": action_id, "action_type": action_type, "text": text}
        if action_id
        else None
    )
    return {
        "screen_intent_id": id_factory.screen_intent_id(),
        "source_state_id": str(state_row["state_id"]),
        "source_group_id": gid,
        "intent_kind": "submission",
        "intent_name": f"Interact with {purpose}",
        "local_user_goal": f"Complete the flow on {purpose}",
        "primary_action": primary,
        "selection_options": [],
        "commit_action": commit,
        "secondary_actions": [],
        "local_action_sequence_templates": [],
        "required_input_element_ids": [],
        "evidence_refs": [],
        "confidence": "medium",
        "model_confidence": "medium",
        "validation_confidence": "low",
    }


class ExperimentScreenIntentPackageBuilder:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    def build_screen_intent_package(
        self,
        state_catalog: list[dict[str, Any]],
        normalized_outputs: list[NormalizedJointOutput],
        id_factory: ExperimentIdFactory,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        catalog_all: list[dict[str, Any]] = []
        unresolved_all: list[dict[str, Any]] = []
        per_state_summaries: list[dict[str, Any]] = []
        warnings: list[str] = []
        skipped_states: list[str] = []

        normalized_by_src = {n.source_image_id: n for n in normalized_outputs}

        for state_row in state_catalog:
            src = str(state_row.get("source_image_id") or "")
            norm = normalized_by_src.get(src)
            if not norm:
                skipped_states.append(src)
                continue
            state_id = str(state_row["state_id"])
            si_dict = dict(norm.screen_intents)

            try:
                intents_raw = system_readonly_adapter.ScreenIntentExtractionV2Result.model_validate(si_dict)
            except ValidationError:
                warnings.append("SCREEN_INTENT_SCHEMA_FALLBACK_USED")
                catalog_all.append(_synthetic_intent_row(state_row, id_factory))
                per_state_summaries.append(
                    {
                        "state_id": state_id,
                        "validated_intents": 1,
                        "rejected_intents": 0,
                        "intent_kind_counts": {"submission": 1},
                        "unresolved_reason_counts": {},
                        "per_intent_reports": [],
                        "mode": "schema_fallback",
                    },
                )
                continue

            intents_prefixed = system_readonly_adapter.prefix_screen_intent_payload(state_id, intents_raw)
            draft_dump = intents_prefixed.model_dump(mode="python")
            system_readonly_adapter.validate_joint_screen_understanding_structured(state_row, draft_dump)
            cat, unst, summary, _stats = system_readonly_adapter.process_screen_intents_for_state(
                state_row,
                intents_prefixed,
                id_factory.screen_intent_id,
            )
            catalog_all.extend(cat)
            unresolved_all.extend(unst)
            per_state_summaries.append(summary)

        total_val = sum(int(s.get("validated_intents") or 0) for s in per_state_summaries)
        agg_unres: dict[str, int] = {}
        for s in per_state_summaries:
            for k, v in (s.get("unresolved_reason_counts") or {}).items():
                agg_unres[k] = agg_unres.get(k, 0) + int(v)

        sip_pkg_id = f"sbi_pkg_exp_{self._app_id}_{uuid.uuid4().hex[:10]}"
        pkg: dict[str, Any] = {
            "schema_version": "2.1",
            "agent_name": config.INPUT_BUILDER_AGENT_NAME,
            "extraction_mode": "offline_from_raw_joint_outputs",
            "screen_intent_package_id": sip_pkg_id,
            "screen_intent_catalog": catalog_all,
            "unresolved_screen_groups": unresolved_all,
            "skipped_states": skipped_states,
            "intent_validation_summary": {
                "per_state": per_state_summaries,
                "aggregate_validated_intents": total_val,
                "aggregate_unresolved_reason_codes": agg_unres,
                "skipped_state_count": len(skipped_states),
            },
            "report": {
                "app_id": self._app_id,
                "total_states_processed": len(state_catalog),
                "total_intents_extracted": len(catalog_all),
                "warnings": warnings,
            },
        }
        report = {
            "screen_intent_warning_count": len(warnings),
            "warnings": warnings,
            "resolved_state_count": len(state_catalog) - len(skipped_states),
        }
        return pkg, report


__all__ = ["ExperimentScreenIntentPackageBuilder"]
