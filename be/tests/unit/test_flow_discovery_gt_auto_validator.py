"""Sprint 4 auto-validation tests for flow_discovery gt_converter."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.flow_discovery.cli import main as cli_main
from experiments.flow_discovery.gt_converter.ground_truth_auto_validator import annotate_package_issues
from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
from experiments.flow_discovery.io_utils import write_json_document
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage, GroundTruthTransition
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


def _validation_screen_no_feedback() -> dict:
    return {
        "state_id": "val_1",
        "screen_purpose": "validation_error_page",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "validation_error"},
        "visible_elements": [{"element_type": "text", "text": ["Bad"]}],
        "available_actions": [],
        "visible_feedback": [],
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
        "screen_intents": [],
    }


def test_gt_convert_populates_transition_auto_validation() -> None:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [_login_screen(), _dash_screen()],
        "trace_index": {
            "login_1": {"source_image_id": "img_login.png", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "dash_1": {"source_image_id": "img_d.png", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
        },
    }

    repaired = {
        "semantic_clusters": [],
        "candidate_flows": [
            {
                "flow_id": "f1",
                "flow_name": "login_ok",
                "flow_type": "ordered_sequence",
                "ordered_steps": [
                    {"state_id": "login_1", "next_trigger_action": {"action_id": "login_btn", "text": ["Login"]}},
                    {"state_id": "dash_1"},
                ],
            }
        ],
    }

    env = RawFlowDiscoveryExperimentPackage(
        app_id="testapp",
        run_id="r1",
        input_refs={},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={},
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
        repaired_model_output=None,
    )
    pkg = convert_raw_package_to_draft(env)
    assert pkg.transitions
    for tx in pkg.transitions:
        assert "checks" in tx.auto_validation
        assert "warnings" in tx.auto_validation

    summary = pkg.package_auto_validation.extras.get("warning_summary_by_code") or {}
    assert isinstance(summary, dict)
    assert "transition_warning_count" in pkg.package_auto_validation.extras


def test_trigger_not_visible_warning() -> None:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [_login_screen(), _dash_screen()],
        "trace_index": {
            "login_1": {"source_image_id": "i1", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "dash_1": {"source_image_id": "i2", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
        },
    }
    repaired = {
        "candidate_flows": [
            {
                "flow_id": "f1",
                "flow_type": "ordered_sequence",
                "ordered_steps": [
                    {"state_id": "login_1", "next_trigger_action": {"action_id": "login_btn", "text": ["Wrong Label"]}},
                    {"state_id": "dash_1"},
                ],
            }
        ],
    }
    env = RawFlowDiscoveryExperimentPackage(
        app_id="testapp",
        run_id="r1",
        input_refs={},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={},
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
    )
    pkg = convert_raw_package_to_draft(env)
    codes = [w["warning_code"] for tx in pkg.transitions for w in (tx.auto_validation.get("warnings") or [])]
    assert "TRIGGER_NOT_VISIBLE_ON_SOURCE" in codes


def test_validation_target_without_feedback_warning() -> None:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [_login_screen(), _validation_screen_no_feedback()],
        "trace_index": {
            "login_1": {"source_image_id": "i1", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "val_1": {"source_image_id": "i2", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
        },
    }
    repaired = {
        "candidate_flows": [
            {
                "flow_id": "f_val",
                "flow_type": "ordered_sequence",
                "ordered_steps": [
                    {"state_id": "login_1", "next_trigger_action": {"action_id": "login_btn", "text": ["Login"]}},
                    {"state_id": "val_1"},
                ],
            }
        ],
    }
    env = RawFlowDiscoveryExperimentPackage(
        app_id="testapp",
        run_id="r1",
        input_refs={},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={},
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
    )
    pkg = convert_raw_package_to_draft(env)
    codes = [w["warning_code"] for tx in pkg.transitions for w in (tx.auto_validation.get("warnings") or [])]
    assert "VALIDATION_TARGET_WITHOUT_FEEDBACK" in codes


def test_flow_chain_not_continuous_manual() -> None:
    from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlow, GroundTruthState

    pkg = GroundTruthFlowPackage(
        app_id="x",
        states=[
            GroundTruthState(gt_state_id="a", catalog_state_id="c1"),
            GroundTruthState(gt_state_id="b", catalog_state_id="c2"),
            GroundTruthState(gt_state_id="c", catalog_state_id="c3"),
        ],
        transitions=[
            GroundTruthTransition(
                gt_transition_id="t_ab",
                from_state_id="a",
                to_state_id="b",
                trigger_action_text="Go",
                outcome_type="success",
                proposal_source="test",
                proposal_flow_id="f_raw",
            ),
        ],
        flows=[
            GroundTruthFlow(
                gt_flow_id="gf1",
                source_flow_id="f_raw",
                ordered_state_ids=["a", "b", "c"],
                transition_ids=["t_ab"],
            ),
        ],
        branch_groups=[],
    )
    annotate_package_issues(pkg)
    codes = [w["warning_code"] for tx in pkg.transitions for w in (tx.auto_validation.get("warnings") or [])]
    assert "FLOW_CHAIN_NOT_CONTINUOUS" in codes


def test_duplicate_transition_detected() -> None:
    s1 = GroundTruthFlowPackage.model_validate_json(
        json.dumps(
            {
                "schema_version": "ground_truth_flow_package_v2",
                "app_id": "x",
                "states": [
                    {
                        "gt_state_id": "a",
                        "catalog_state_id": "c1",
                        "visible_evidence": {"actions": ["Go"]},
                    },
                    {"gt_state_id": "b", "catalog_state_id": "c2"},
                ],
                "actions": [],
                "transitions": [
                    {
                        "gt_transition_id": "t1",
                        "from_state_id": "a",
                        "to_state_id": "b",
                        "trigger_action_text": "Go",
                        "outcome_type": "success",
                        "proposal_source": "test",
                    },
                    {
                        "gt_transition_id": "t2",
                        "from_state_id": "a",
                        "to_state_id": "b",
                        "trigger_action_text": "Go",
                        "outcome_type": "success",
                        "proposal_source": "test",
                    },
                ],
                "flows": [],
                "branch_groups": [],
            },
        ),
    )
    annotate_package_issues(s1)
    assert s1.transitions[0].auto_validation["checks"]["duplicate_transition_detected"] is True
    warn_codes = [w["warning_code"] for w in (s1.transitions[0].auto_validation.get("warnings") or [])]
    assert "DUPLICATE_TRANSITION_DETECTED" in warn_codes


def test_gt_validate_cli_inplace(tmp_path: Path) -> None:
    pkg = GroundTruthFlowPackage(
        app_id="demoauth",
        states=[
            {"gt_state_id": "a", "catalog_state_id": "c1"},
            {"gt_state_id": "b", "catalog_state_id": "c2"},
        ],
        transitions=[
            GroundTruthTransition(
                gt_transition_id="t1",
                from_state_id="a",
                to_state_id="b",
                trigger_action_text="Go",
                outcome_type="success",
                proposal_source="test",
            ),
        ],
        flows=[],
        branch_groups=[],
    )
    pth = tmp_path / "gt.json"
    write_json_document(pth, pkg.model_dump(mode="json", round_trip=True))
    code = cli_main(["gt-validate", "--input", str(pth)])
    assert code == 0
    again = GroundTruthFlowPackage.model_validate_json(pth.read_text(encoding="utf-8"))
    assert again.transitions[0].auto_validation.get("checks")
