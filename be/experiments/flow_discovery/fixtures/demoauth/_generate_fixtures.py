"""One-off helper to regenerate demoauth fixture JSON files. Run from be/: python experiments/flow_discovery/fixtures/demoauth/_generate_fixtures.py"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from experiments.flow_discovery.evaluator.evaluation_runner import run_evaluation
from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
from experiments.flow_discovery.io_utils import write_json_document
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage

PKG_ROOT = Path(__file__).resolve().parent


def joint_login_payload() -> dict:
    """Aligned with JointScreenUnderstandingResult (tests: _login_raw_payload)."""
    return {
        "ui_state": {
            "state_id": "state_exp_auth_login_login_empty",
            "screen_purpose": "User logs in",
            "presentation_scope": "full_screen",
            "screen_type": "auth",
            "outcome_state_type": "neutral",
            "domain": "authentication",
            "visible_elements": [
                {
                    "element_id": "el_001",
                    "element_type": "input",
                    "text": ["Email"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "el_002",
                    "element_type": "input",
                    "text": ["Password"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "el_003",
                    "element_type": "button",
                    "text": ["Login"],
                    "role_hint": "primary_action",
                    "visual_region": "main",
                },
            ],
            "available_actions": [
                {
                    "action_id": "ac_001",
                    "action_type": "type",
                    "text": ["Enter Email"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
                {
                    "action_id": "ac_002",
                    "action_type": "type",
                    "text": ["Enter Password"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
                {
                    "action_id": "ac_003",
                    "action_type": "submit",
                    "text": ["Login"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig_001",
                    "group_type": "form",
                    "group_label": "Login Form",
                    "element_ids": ["el_001", "el_002", "el_003"],
                    "action_ids": ["ac_001", "ac_002", "ac_003"],
                    "feedback_ids": [],
                    "primary_action_id": "ac_003",
                    "group_evidence": [],
                    "group_confidence": "high",
                }
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig_001",
                    "intent_kind": "submission",
                    "intent_name": "Submit login",
                    "local_user_goal": "Sign in",
                    "primary_action_id": "ac_003",
                    "commit_action_id": "ac_003",
                    "secondary_action_ids": ["ac_001", "ac_002"],
                    "selection_options": [],
                    "required_input_element_ids": ["el_001", "el_002"],
                    "evidence_refs": [{"evidence_type": "action_text", "source_id": "ac_003"}],
                    "local_action_sequence_templates": [
                        {
                            "sequence_name": "enter credentials and login",
                            "steps": [
                                {
                                    "step_type": "enter_input",
                                    "source_action_id": "ac_001",
                                    "source_element_id": "el_001",
                                },
                                {
                                    "step_type": "enter_input",
                                    "source_action_id": "ac_002",
                                    "source_element_id": "el_002",
                                },
                                {
                                    "step_type": "invoke_action",
                                    "source_action_id": "ac_003",
                                    "source_element_id": "el_003",
                                },
                            ],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                    "model_confidence": "high",
                }
            ],
            "unresolved_screen_groups": [],
        },
    }


def joint_dashboard_payload() -> dict:
    return {
        "ui_state": {
            "state_id": "dash_raw",
            "screen_purpose": "Dashboard",
            "presentation_scope": "full_screen",
            "screen_type": "dashboard",
            "outcome_state_type": "neutral",
            "domain": "app",
            "visible_elements": [{"element_id": "h1", "element_type": "heading", "text": ["Home"]}],
            "available_actions": [],
            "visible_feedback": [],
            "interaction_groups": [],
        },
        "screen_intents": {"screen_behaviour_intents": [], "unresolved_screen_groups": []},
    }


def splash() -> dict:
    return {
        "state_id": "splash_1",
        "screen_purpose": "splash",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "neutral"},
        "visible_elements": [],
        "available_actions": [{"action_id": "continue_btn", "action_type": "submit", "text": ["Continue"]}],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [],
    }


def login() -> dict:
    return {
        "state_id": "login_1",
        "screen_purpose": "login_page",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "neutral"},
        "visible_elements": [],
        "available_actions": [{"action_id": "login_btn", "action_type": "submit", "text": ["Login"]}],
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


def dash() -> dict:
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


def err() -> dict:
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


def main() -> None:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [splash(), login(), dash(), err()],
        "trace_index": {
            k: {"source_image_id": k, "ui_state_package_ref": "", "screen_intent_package_ref": ""}
            for k in ("splash_1", "login_1", "dash_1", "err_1")
        },
    }

    repaired = {
        "semantic_clusters": [],
        "candidate_flows": [
            {
                "flow_id": "linear_demo",
                "flow_name": "Splash to dashboard",
                "flow_type": "ordered_sequence",
                "ordered_steps": [
                    {
                        "state_id": "splash_1",
                        "next_trigger_action": {"action_id": "continue_btn", "text": ["Continue"]},
                    },
                    {
                        "state_id": "login_1",
                        "next_trigger_action": {"action_id": "login_btn", "text": ["Login"]},
                    },
                    {"state_id": "dash_1"},
                ],
            },
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
                "entry_state_id": "login_1",
                "terminal_outcome": None,
                "rationale": "",
            },
        ],
        "unassigned_state_ids": [],
    }

    env = RawFlowDiscoveryExperimentPackage(
        app_id="demoauth",
        run_id="fixture_demoauth",
        input_refs={"fixture": True},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={
            "catalog_version": "compressed_catalog_v3",
            "catalog_purpose": "global_flow_discovery_input",
            "states": [],
        },
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
        repaired_model_output=None,
    )

    PKG_ROOT.mkdir(parents=True, exist_ok=True)
    write_json_document(PKG_ROOT / "compressed_catalog_package.json", compressed)
    raw_pkg = env.model_dump(mode="json", round_trip=True)
    write_json_document(PKG_ROOT / "raw_model_output.sample.json", raw_pkg)
    # Same payload as canonical name under work_dir (`raw_model_output.json`) for demos / batch skips.
    write_json_document(PKG_ROOT / "raw_model_output.json", raw_pkg)

    gt = convert_raw_package_to_draft(env, app_id_override="demoauth")
    gt_dict = gt.model_dump(mode="json", round_trip=True)
    for rs in gt_dict["states"]:
        rs.setdefault("review", {})["review_status"] = "reviewed"
    for a in gt_dict["actions"]:
        a.setdefault("review", {})["review_status"] = "reviewed"
    for t in gt_dict["transitions"]:
        t.setdefault("review", {})["review_status"] = "reviewed"
        t["eval_include"] = True
    for f in gt_dict["flows"]:
        f.setdefault("review", {})["review_status"] = "reviewed"
        f["eval_include"] = True
    for bg in gt_dict["branch_groups"]:
        bg.setdefault("review", {})["review_status"] = "reviewed"
        bg["eval_include"] = True
    pr = gt_dict.get("package_review") or {}
    pr["review_status"] = "reviewed"
    gt_dict["package_review"] = pr

    reviewed = GroundTruthFlowPackage.model_validate(gt_dict)
    reviewed_dump = reviewed.model_dump(mode="json", round_trip=True)
    write_json_document(PKG_ROOT / "ground_truth.reviewed.sample.json", reviewed_dump)
    write_json_document(PKG_ROOT / "ground_truth.reviewed.json", reviewed_dump)

    with tempfile.TemporaryDirectory() as td:
        raw_path = Path(td) / "raw.json"
        gt_path = Path(td) / "gt.json"
        write_json_document(raw_path, env.model_dump(mode="json", round_trip=True))
        write_json_document(gt_path, reviewed.model_dump(mode="json", round_trip=True))
        out_eval = Path(td) / "e"
        result = run_evaluation(app_id="demoauth", raw_output_path=raw_path, ground_truth_path=gt_path, out_dir=out_eval)

    exp = {
        "schema_version": result.schema_version,
        "app_id": result.app_id,
        "metrics": json.loads(result.metrics.model_dump_json(round_trip=True)),
        "_note": "Compare key floats with tolerance in tests; omit created_at.",
    }
    write_json_document(PKG_ROOT / "expected_evaluation_result.json", exp)
    print("Wrote fixtures to", PKG_ROOT.as_posix())  # noqa: T201

    rj = PKG_ROOT / "raw_joint_outputs"
    rj.mkdir(parents=True, exist_ok=True)
    login_pl = joint_login_payload()
    write_json_document(rj / "AUTH_S01_login_page.raw.json", login_pl)
    write_json_document(
        rj / "AUTH_S02_login_wrapped.raw.json",
        {"status": "success", "parsed_output": login_pl},
    )
    write_json_document(rj / "AUTH_S03_dashboard.raw.json", {"output": joint_dashboard_payload()})
    write_json_document(
        PKG_ROOT / "image_map.sample.json",
        {
            "AUTH_S01_login_page.raw.json": {
                "source_image_id": "AUTH_S01_login_page",
                "original_filename": "login_page.png",
            },
        },
    )
    print("Wrote joint raw fixtures to", rj.as_posix())  # noqa: T201


if __name__ == "__main__":
    main()
