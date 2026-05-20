"""Tests for Sprint 3 gt_converter (no model calls)."""

from __future__ import annotations

import json

from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
from experiments.flow_discovery.io_utils import utc_now_iso
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def _dash_screen() -> dict:
    return {
        "state_id": "dash_1",
        "screen_purpose": "dashboard",
        "taxonomy": {"screen_type": "dashboard", "outcome_state_type": "positive"},
        "visible_elements": [{"element_type": "heading", "text": ["Dashboard"]}],
        "available_actions": [],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [],
    }


def _err_screen() -> dict:
    return {
        "state_id": "err_1",
        "screen_purpose": "validation_error_page",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "validation_error"},
        "visible_elements": [{"element_type": "text", "text": ["Fix password"]}],
        "available_actions": [],
        "visible_feedback": [{"text": ["Required"]}],
        "interaction_groups": [],
        "screen_intents": [],
    }


def _login_screen() -> dict:
    return {
        "state_id": "login_1",
        "screen_purpose": "login_page",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "neutral"},
        "visible_elements": [],
        "available_actions": [
            {"action_id": "login_btn", "action_type": "submit", "text": ["Login"]},
        ],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [
            {
                "intent_id": "intent_login",
                "source_group_id": "g1",
                "intent_kind": "submission",
                "intent_name": "submit",
                "local_user_goal": "login",
                "primary_action": {"action_id": "login_btn", "action_type": "submit", "text": ["Login"]},
                "secondary_actions": [],
                "evidence_refs": [],
            }
        ],
    }


def test_gt_convert_branching_alternatives_and_branch_groups() -> None:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [_login_screen(), _dash_screen(), _err_screen()],
        "trace_index": {
            "login_1": {"source_image_id": "img_login.png", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "dash_1": {"source_image_id": "img_d.png", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "err_1": {"source_image_id": "img_e.png", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
        },
    }

    repaired = {
        "semantic_clusters": [],
        "candidate_flows": [
            {
                "flow_id": "branch_login",
                "flow_name": "Login branches",
                "flow_type": "branching_flow",
                "ordered_steps": [],
                "alternative_outcomes": [
                    {
                        "from_state_id": "login_1",
                        "to_state_id": "dash_1",
                        "outcome_role": "success",
                        "trigger_action": {
                            "action_id": "login_btn",
                            "action_type": "submit",
                            "text": ["Login"],
                            "intent_id": "intent_login",
                        },
                        "evidence_summary": "",
                    },
                    {
                        "from_state_id": "login_1",
                        "to_state_id": "err_1",
                        "outcome_role": "validation_error",
                        "trigger_action": {
                            "action_id": "login_btn",
                            "action_type": "submit",
                            "text": ["Login"],
                            "intent_id": "intent_login",
                        },
                        "evidence_summary": "",
                    },
                ],
                "flow_evidence": [],
                "entry_state_id": "login_1",
                "terminal_outcome": None,
                "rationale": "",
            }
        ],
        "unassigned_state_ids": [],
        "uncertain_relations": [],
        "discovery_warnings": [],
    }

    envelope = RawFlowDiscoveryExperimentPackage(
        app_id="demoauth",
        run_id="synthetic_gt",
        input_refs={"test": True},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={
            "catalog_version": "compressed_catalog_v3",
            "catalog_purpose": "global_flow_discovery_input",
            "states": [],
        },
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
        repaired_model_output=repaired,
        validation_metrics={"pre_scan": {}},
        discovery_warnings=[],
        created_at=utc_now_iso(),
    )

    gt = convert_raw_package_to_draft(envelope)

    assert len(gt.states) == 3
    assert gt.actions

    txs = gt.transitions
    assert len(txs) >= 2
    assert all(bool(tx.proposal_source) for tx in txs)

    dash_pick = None
    for t in txs:
        if any("dashboard" in e.lower() for e in (t.expected_visible_evidence or [])):
            dash_pick = t
            break
    assert dash_pick is not None

    grouped_ge2 = sum(1 for bg in gt.branch_groups if len(bg.alternative_transition_ids) >= 2)
    assert grouped_ge2 >= 1

    json.loads(json.dumps(gt.model_dump(mode="json", round_trip=True)))
