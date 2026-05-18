"""Unit tests for joint screen understanding ID prefixing."""

from app.model_providers.schemas import (
    EvidenceRefDraftA2,
    ScreenBehaviourIntentDraftA2,
    ScreenIntentExtractionV2Result,
    UnresolvedScreenGroupA2,
)
from app.services.joint_screen_understanding_ids import prefix_screen_intent_payload, prefix_under


def test_prefix_under_idempotent():
    sid = "st_abc123_login"
    assert prefix_under(sid, "el_1") == "st_abc123_login_el_1"
    assert prefix_under(sid, "st_abc123_login_el_1") == "st_abc123_login_el_1"


def test_prefix_screen_intent_payload_all_refs():
    sid = "st_test_state_x"
    payload = ScreenIntentExtractionV2Result(
        screen_behaviour_intents=[
            ScreenBehaviourIntentDraftA2(
                source_group_id="ig_1",
                intent_kind="submission",
                intent_name="submit",
                local_user_goal="submit form",
                primary_action_id="ac_1",
                commit_action_id="ac_1",
                secondary_action_ids=["ac_2"],
                required_input_element_ids=["el_1"],
                evidence_refs=[
                    EvidenceRefDraftA2(evidence_type="action_text", source_id="ac_1"),
                ],
                model_confidence="high",
            )
        ],
        unresolved_screen_groups=[
            UnresolvedScreenGroupA2(group_id="ig_9", reason_code="no_interaction_group", details="x"),
        ],
    )
    out = prefix_screen_intent_payload(sid, payload)
    assert out.screen_behaviour_intents[0].source_group_id == f"{sid}_ig_1"
    assert out.screen_behaviour_intents[0].primary_action_id == f"{sid}_ac_1"
    assert out.screen_behaviour_intents[0].secondary_action_ids == [f"{sid}_ac_2"]
    assert out.screen_behaviour_intents[0].required_input_element_ids == [f"{sid}_el_1"]
    assert out.screen_behaviour_intents[0].evidence_refs[0].source_id == f"{sid}_ac_1"
    assert out.unresolved_screen_groups[0].group_id == f"{sid}_ig_9"
