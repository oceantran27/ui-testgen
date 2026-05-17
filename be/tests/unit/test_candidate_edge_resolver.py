"""Unit tests for candidate edge taxonomy, classification, gates, scoring v2, and resolver."""

from __future__ import annotations

from app.constants.edge_taxonomy import EDGE_KIND_VALUES, eligible_targets
from app.services.candidate_edge_classification import classify_edge_kind, classify_scenario_role
from app.services.candidate_edge_gates import gate_intent_cross_state_capability, hard_gate_per_transition
from app.services.candidate_edge_resolver_service import resolve_candidate_edges
from app.services.candidate_edge_scoring import score_candidate_edge
from app.services.candidate_edge_thresholds import should_keep_edge


def test_eligible_targets_submission_includes_success() -> None:
    assert "success" in eligible_targets("submission")
    assert eligible_targets("informative") == frozenset()


def test_classify_edge_kind_shapes() -> None:
    assert classify_edge_kind("submission", "neutral", "success") == "success_terminal"
    assert classify_edge_kind("submission", "neutral", "empty") == "empty_result"
    assert classify_edge_kind("submission", "neutral", "validation_error") == "validation_error"
    assert classify_edge_kind("submission", "neutral", "confirmation_required") == "confirmation_required"
    assert classify_edge_kind("navigation", "neutral", "neutral") == "progress"


def test_edge_kind_values_contains_classifier_outputs() -> None:
    assert "success_terminal" in EDGE_KIND_VALUES
    assert "empty_result" in EDGE_KIND_VALUES


def test_classify_scenario_role_core_vs_branch() -> None:
    assert (
        classify_scenario_role("submission", "neutral", "success", target_screen="detail") == "core"
    )
    assert classify_scenario_role("selection", "neutral", "success", target_screen="detail") == "branch"


def test_classify_scenario_role_post_success_optional() -> None:
    assert (
        classify_scenario_role("submission", "success", "neutral", target_screen="landing")
        == "optional"
    )


def test_score_candidate_edge_scale_0_to_100() -> None:
    sr = score_candidate_edge(
        intent_kind="submission",
        intent_confidence="high",
        validation_confidence="high",
        source_outcome="neutral",
        target_outcome="success",
        edge_kind="success_terminal",
        source_screen="form",
        target_screen="detail",
        source_upload_order=1,
        target_upload_order=2,
        source_corpus="book now",
        target_corpus="confirm your booking at 14:30 done",
        source_visible_texts=["book"],
        target_visible_texts=["confirm", "booking", "done"],
        source_screen_purpose="pick slot",
        target_screen_purpose="review booking",
        source_domain="travel",
        target_domain="travel",
        source_presentation_scope="full_screen",
        target_presentation_scope="full_screen",
        uses_template_sequence=False,
        action_steps=[
            {
                "action_role": "commit",
                "action_text": ["confirm booking"],
                "source_group_id": "g1",
                "source_screen_intent_id": "i1",
            }
        ],
        source_group_id="g1",
        source_screen_intent_id="i1",
        main_action_texts=["confirm booking"],
        specific_value_matched=True,
        target_has_extracted_specific_values=True,
        ambiguous_selection=False,
        unresolved_selection=False,
        intent_has_evidence=True,
        unordered_images_allowed=False,
    )
    assert 40 <= sr.value <= 100
    assert sr.reasons


def test_should_keep_edge_weak_band() -> None:
    ok, reason = should_keep_edge(
        71,
        "submission_success",
        [],
        prune_threshold=60,
        weak_threshold=60,
        allow_weak_band=True,
    )
    assert ok and reason == "accepted_weak_band"


def test_should_keep_edge_pruned_below_global() -> None:
    ok, reason = should_keep_edge(
        55,
        "submission_success",
        [],
        prune_threshold=60,
        weak_threshold=60,
        allow_weak_band=True,
    )
    assert not ok


def test_gate_selection_requires_commit_or_select_template() -> None:
    intent = {
        "intent_kind": "selection",
        "selection_options": [{"option_text": ["a"], "option_ref_type": "element"}],
        "local_action_sequence_templates": [],
    }
    assert not gate_intent_cross_state_capability(intent).ok


def test_gate_source_terminal_blocks_submission() -> None:
    src = {"state_id": "s1", "visible_text": ["x"], "outcome_state_type": "success"}
    tgt = {
        "state_id": "s2",
        "visible_text": ["y"],
        "outcome_state_type": "neutral",
        "screen_type": "detail",
        "presentation_scope": "full_screen",
    }
    r = hard_gate_per_transition(
        intent_kind="submission",
        source_outcome="success",
        source_card=src,
        target_card=tgt,
        source_screen="form",
        target_screen="detail",
    )
    assert not r.ok


def test_resolve_merges_alternate_sequences_same_transition() -> None:
    """Two eligible_actions → same target produce merged alternatives."""
    cards = [
        {
            "state_id": "s_a",
            "screen_type": "form",
            "outcome_state_type": "neutral",
            "upload_order": 0,
            "visible_text": ["Book"],
            "feedback_texts": [],
            "presentation_scope": "full_screen",
            "screen_behaviour_intents": [
                {
                    "screen_intent_id": "int_1",
                    "source_group_id": "g1",
                    "intent_kind": "submission",
                    "confidence": "high",
                    "validation_confidence": "high",
                    "commit_action": {
                        "action_id": "act_submit",
                        "action_type": "button",
                        "text": ["Submit"],
                    },
                    "secondary_actions": [
                        {"action_id": "act_cancel", "action_type": "button", "text": ["Cancel"]},
                    ],
                }
            ],
        },
        {
            "state_id": "s_b",
            "screen_type": "detail",
            "outcome_state_type": "success",
            "upload_order": 1,
            "visible_text": ["Done"],
            "feedback_texts": [],
            "presentation_scope": "full_screen",
            "screen_behaviour_intents": [],
        },
    ]
    edges = resolve_candidate_edges("run1234567890", cards)
    by_pair = {(e["from_state"], e["to_state"]) for e in edges}
    assert ("s_a", "s_b") in by_pair
    primary = next(e for e in edges if e["from_state"] == "s_a" and e["to_state"] == "s_b")
    assert "alternative_action_sequences" in primary
    assert len(primary["alternative_action_sequences"]) >= 1
    all_seqs = [primary["action_sequence"]] + (primary.get("alternative_action_sequences") or [])
    roles = {tuple(s["action_role"] for s in seq) for seq in all_seqs}
    assert ("commit",) in roles
    assert ("cancel",) in roles
