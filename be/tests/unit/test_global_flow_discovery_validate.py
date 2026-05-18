"""Unit tests for global flow discovery catalogue build + validation / repair."""

from __future__ import annotations

from app.model_providers.schemas import (
    FlowDiscoveryAlternativeOutcome,
    FlowDiscoveryCandidateFlow,
    FlowDiscoverySemanticCluster,
    FlowDiscoveryStep,
    FlowDiscoveryTriggerAction,
    FlowDiscoveryUnassignedState,
    GlobalFlowDiscoveryResult,
    UncertainRelationGlobal,
)
from app.services.global_flow_discovery_catalog import (
    build_llm_discovery_catalog,
    validate_discovery_input,
)
from app.services.global_flow_discovery_service import assemble_flow_discovery_bundle, compute_discovery_report
from app.services.global_flow_discovery_validate import (
    repair_or_filter_discovery_output,
    validate_discovery_output,
)


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
        "visible_signature": {"headings": [], "primary_texts": [], "status_texts": []},
        "navigation_cues": {},
        "continuity_entities": [],
        "state_feedback_summary": [],
        "form_state_summary": {"has_form": False},
        "intent_groups": [
            {
                "intent_id": "intent_login",
                "source_group_id": "g1",
                "intent_kind": "submission",
                "intent_name": "submit",
                "local_user_goal": "login",
                "primary_action": {
                    "action_id": "ac_go",
                    "action_type": "submit",
                    "text": ["Go"],
                    "priority": "primary",
                },
                "secondary_actions": [],
                "evidence_refs": [],
            }
        ],
        "evidence_refs": [],
    }


def _compressed_pkg(*states: dict) -> dict:
    return {
        "catalog_version": "compressed_catalog_v2",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": list(states),
    }


def test_build_llm_discovery_catalog_trims_intent_noise():
    pkg = _compressed_pkg(_screen("s_a"))
    llm = build_llm_discovery_catalog(pkg)
    assert llm["states"][0]["state_id"] == "s_a"
    ig = llm["states"][0]["intent_groups"][0]
    assert "evidence_refs" not in ig
    assert "source_group_id" not in ig
    assert ig["primary_action"]["text"] == ["Go"]


def test_validate_discovery_input_duplicate_state_rejected():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("dup"), _screen("dup")))
    ok, errs = validate_discovery_input(llm)
    assert ok is False
    assert any("DUPLICATE_STATE_ID" in e for e in errs)


def test_validate_drops_unknown_and_duplicate_consecutive_steps():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("a"), _screen("b")))
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f1",
                flow_name="t",
                flow_type="ordered_sequence",
                user_goal="goal",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                    FlowDiscoveryStep(state_id="a", step_role="intermediate"),
                    FlowDiscoveryStep(state_id="bogus"),
                    FlowDiscoveryStep(state_id="b", step_role="terminal_success"),
                ],
            ),
        ],
        unassigned_state_ids=[],
        uncertain_relations=[],
        discovery_warnings=["w"],
    )

    repaired, metrics = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    assert len(repaired.candidate_flows) == 1
    fs = repaired.candidate_flows[0]
    assert [s.state_id for s in fs.ordered_steps] == ["a", "b"]
    assert metrics["post_validation_status"] == "repaired"
    assert "unknown" in " ".join(repaired.discovery_warnings).lower()


def test_repair_ordered_sequence_singleton():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("only")))
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f2",
                flow_name="s",
                flow_type="ordered_sequence",
                ordered_steps=[FlowDiscoveryStep(state_id="only", step_role="entry")],
            ),
        ],
    )

    repaired, _ = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    assert repaired.candidate_flows[0].flow_type == "single_step_outcome"


def test_repair_trigger_text_mismatch_uses_catalog_copy():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("a"), _screen("b")))
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="fx",
                flow_name="x",
                flow_type="ordered_sequence",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Wrong"],
                            intent_id="intent_login",
                        ),
                    ),
                    FlowDiscoveryStep(state_id="b"),
                ],
            ),
        ],
    )

    repaired, _ = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    trig = repaired.candidate_flows[0].ordered_steps[0].next_trigger_action
    assert trig is not None
    assert trig.text == ["Go"]


def test_unassigned_dropped_when_on_spine():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("a"), _screen("b")))
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f",
                flow_name="n",
                flow_type="ordered_sequence",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                    FlowDiscoveryStep(state_id="b"),
                ],
            ),
        ],
        unassigned_state_ids=[
            FlowDiscoveryUnassignedState(state_id="b", reason_code="isolated_informational_screen"),
        ],
    )

    repaired, _ = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    assert repaired.unassigned_state_ids == []


def test_uncertain_dropped_when_matches_spine_edge():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("a"), _screen("b")))
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f",
                flow_name="n",
                flow_type="ordered_sequence",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                    FlowDiscoveryStep(state_id="b"),
                ],
            ),
        ],
        uncertain_relations=[
            UncertainRelationGlobal(from_state_id="a", to_state_id="b", reason_code="ambiguous_target"),
        ],
    )

    repaired, _ = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    assert repaired.uncertain_relations == []


def test_validate_discovery_output_counts_bad_refs():
    llm = build_llm_discovery_catalog(_compressed_pkg(_screen("a")))
    prev = validate_discovery_output(
        GlobalFlowDiscoveryResult(
            candidate_flows=[
                FlowDiscoveryCandidateFlow(
                    flow_id="bad",
                    flow_name="bad",
                    flow_type="ordered_sequence",
                    ordered_steps=[
                        FlowDiscoveryStep(
                            state_id="a",
                            next_trigger_action=FlowDiscoveryTriggerAction(action_id="nope", text=["x"]),
                        ),
                    ],
                ),
            ],
        ),
        llm_catalog=llm,
    )
    assert prev["invalid_action_ref_count"] >= 1


def test_interior_negative_spine_step_removed():
    llm = build_llm_discovery_catalog(
        _compressed_pkg(_screen("s_login", "neutral"), _screen("s_err", "validation_error"), _screen("s_ok", "success"))
    )
    raw = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="trip",
                flow_name="trip",
                flow_type="ordered_sequence",
                ordered_steps=[
                    FlowDiscoveryStep(state_id="s_login", step_role="entry"),
                    FlowDiscoveryStep(state_id="s_err", step_role="outcome_validation"),
                    FlowDiscoveryStep(state_id="s_ok", step_role="terminal_success"),
                ],
            ),
        ],
    )

    repaired, _ = repair_or_filter_discovery_output(raw, llm_catalog=llm)
    ids = [s.state_id for s in repaired.candidate_flows[0].ordered_steps]
    assert ids == ["s_login", "s_ok"]


def test_assemble_bundle_includes_semantic_clusters_and_alt_edges():
    pkg = _compressed_pkg(_screen("a"), _screen("b"))
    llm = build_llm_discovery_catalog(pkg)
    repaired = GlobalFlowDiscoveryResult(
        semantic_clusters=[
            FlowDiscoverySemanticCluster(
                cluster_id="c1",
                cluster_goal="auth",
                domain="authentication",
                state_ids=["a", "b"],
                cluster_evidence=["shared_domain"],
            ),
        ],
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="f",
                flow_name="flow",
                flow_type="branching_flow",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                    FlowDiscoveryStep(state_id="b", step_role="terminal_success"),
                ],
                alternative_outcomes=[
                    FlowDiscoveryAlternativeOutcome(
                        from_state_id="a",
                        to_state_id="b",
                        outcome_role="validation_error",
                        trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                ],
            ),
        ],
    )
    report = compute_discovery_report(llm_catalog=llm, repaired=repaired, prompt_char_len=100, validation_metrics={})
    bundle = assemble_flow_discovery_bundle(pkg, repaired, discovery_report=report)
    assert len(bundle["semantic_clusters"]) == 1
    edges = bundle["report"]["candidate_edges"]
    assert len(edges) >= 2
    kinds = {e.get("edge_kind") for e in edges}
    assert "progress" in kinds
    assert "alternative_outcome" in kinds
    cf0 = bundle["candidate_flows"][0]
    assert cf0["alternative_outcome_edge_ids"]
