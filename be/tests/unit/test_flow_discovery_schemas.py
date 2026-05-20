"""Unit tests for flow_discovery experiment schemas and import hygiene."""

from __future__ import annotations

import ast
from pathlib import Path

from app.model_providers.schemas import (
    FlowDiscoveryCandidateFlow,
    FlowDiscoveryStep,
    FlowDiscoveryTriggerAction,
    GlobalFlowDiscoveryResult,
)
from app.services.global_flow_discovery_catalog import build_llm_discovery_catalog

from experiments.flow_discovery import config as fd_config
from experiments.flow_discovery.adapters import system_readonly_adapter
from experiments.flow_discovery.config import PACKAGE_ROOT as FD_PACKAGE_ROOT
from experiments.flow_discovery.io_utils import utc_now_iso
from experiments.flow_discovery.schemas.evaluation_schema import (
    BranchMetrics,
    ErrorMetrics,
    EvaluationMetricsNested,
    EvaluationResult,
    FlowMetrics,
    TransitionMetrics,
)
from experiments.flow_discovery.schemas.ground_truth_schema import (
    GroundTruthFlow,
    GroundTruthFlowPackage,
    GroundTruthState,
    GroundTruthTransition,
)
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def _screen(state_id: str, outcome: str = "neutral") -> dict:
    return {
        "state_id": state_id,
        "screen_purpose": "login",
        "taxonomy": {
            "domain": "authentication",
            "screen_type": "auth",
            "presentation_scope": "full_screen",
            "outcome_state_type": outcome,
        },
        "visible_elements": [],
        "available_actions": [
            {"action_id": "ac_go", "action_type": "submit", "text": ["Go"], "action_priority": "primary"},
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
                "primary_action": {"action_id": "ac_go", "action_type": "submit", "text": ["Go"]},
                "secondary_actions": [],
                "evidence_refs": [],
            }
        ],
    }


def _compressed_pkg(*states: dict) -> dict:
    return {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": list(states),
    }


def _non_adapter_python_files(flow_root: Path) -> list[Path]:
    adapters_dir = flow_root / "adapters"
    paths: list[Path] = []
    for py_path in sorted(flow_root.rglob("*.py")):
        try:
            py_path.relative_to(adapters_dir)
        except ValueError:
            paths.append(py_path)
    return paths


def test_import_policy_only_adapters_touch_app_namespace() -> None:
    """Fail if experiments.flow_discovery (outside adapters/) imports app.*."""

    pkg_dir = FD_PACKAGE_ROOT
    offending: list[tuple[str, int]] = []
    for py_path in _non_adapter_python_files(pkg_dir):
        rel = py_path.relative_to(pkg_dir)
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "app":
                offending.append((str(rel), node.lineno))
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] == "app":
                        offending.append((str(rel), node.lineno))
    assert offending == [], f"illegal app imports outside adapters/: {offending}"


def test_raw_flow_discovery_experiment_package_round_trip_json() -> None:
    compressed = _compressed_pkg(_screen("s_a"))
    llm_catalog = build_llm_discovery_catalog(compressed)
    raw_model = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f1",
                flow_name="t",
                flow_type="ordered_sequence",
                user_goal="goal",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="s_a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                ],
            )
        ]
    ).model_dump(mode="json")

    repaired_dict, warnings, metrics = system_readonly_adapter.build_validation_snapshot(
        raw_model, llm_catalog=llm_catalog
    )

    doc = RawFlowDiscoveryExperimentPackage(
        app_id="demoauth",
        run_id="run_test",
        input_refs={"source": "unit_test"},
        compressed_catalog_package=compressed,
        llm_discovery_catalog=llm_catalog,
        prompt_snapshot={"prompt_name": fd_config.PROMPT_NAME},
        model_config_snapshot={"stub": True},
        raw_model_output=raw_model,
        repaired_model_output=repaired_dict,
        validation_metrics=metrics,
        discovery_warnings=warnings,
        created_at=utc_now_iso(),
    )

    raw_json = doc.model_dump_json(round_trip=True)
    rebuilt = RawFlowDiscoveryExperimentPackage.model_validate_json(raw_json)
    assert rebuilt.app_id == "demoauth"
    assert rebuilt.repaired_model_output is not None


def test_ground_truth_flow_package_minimal_round_trip() -> None:
    pkg = GroundTruthFlowPackage(
        app_id="demoauth",
        source_raw_run_id="run_test",
        states=[
            GroundTruthState(
                gt_state_id="gt_s_demoauth_login_page_001",
                catalog_state_id="s_a",
                screen_name="login",
                screen_type="auth",
                outcome_state_type="neutral",
            ),
            GroundTruthState(
                gt_state_id="gt_s_demoauth_dashboard_002",
                catalog_state_id="s_b",
                screen_name="dashboard",
                outcome_state_type="positive",
            ),
        ],
        transitions=[
            GroundTruthTransition(
                gt_transition_id="tx_demoauth_001",
                from_state_id="gt_s_demoauth_login_page_001",
                to_state_id="gt_s_demoauth_dashboard_002",
                trigger_action_id="ac_go",
                trigger_action_text="Login",
                outcome_type="success",
                expected_visible_evidence=["Dashboard"],
                proposal_source="raw_model_output.alternative_outcomes",
                proposal_flow_id="branch_login",
            ),
        ],
        flows=[
            GroundTruthFlow(
                gt_flow_id="gt_f_demoauth_branch_001",
                source_flow_id="branch_login",
                flow_type="branching_flow",
                semantic_flow_kind="navigation_branch",
                ordered_state_ids=["gt_s_demoauth_login_page_001"],
                entry_state_id="gt_s_demoauth_login_page_001",
                terminal_state_id="gt_s_demoauth_dashboard_002",
                transition_ids=["tx_demoauth_001"],
            ),
        ],
        branch_groups=[],
    )
    data = pkg.model_dump(mode="json", round_trip=True)
    again = GroundTruthFlowPackage.model_validate(data)
    assert len(again.transitions) == 1


def test_evaluation_result_minimal_round_trip() -> None:
    result = EvaluationResult(
        app_id="demoauth",
        run_id="run_test",
        metrics=EvaluationMetricsNested(
            transition_metrics=TransitionMetrics(
                strict_precision=1.0,
                strict_recall=0.5,
                strict_f1=0.67,
                relaxed_precision=0.9,
                relaxed_recall=0.6,
                relaxed_f1=0.72,
            ),
            flow_metrics=FlowMetrics(
                membership_macro_f1=0.8,
                ordering_accuracy=0.75,
            ),
            branch_metrics=BranchMetrics(
                branch_precision=0.9,
                branch_recall=0.7,
                branch_f1=0.79,
            ),
            error_metrics=ErrorMetrics(
                invalid_flow_rate=0.0,
                invalid_transition_count=2,
            ),
        ),
        error_breakdown={"extra_transition": 1},
    )
    again = EvaluationResult.model_validate_json(result.model_dump_json(round_trip=True))
    assert again.metrics.error_metrics.invalid_transition_count == 2
    assert again.error_breakdown.get("extra_transition") == 1
