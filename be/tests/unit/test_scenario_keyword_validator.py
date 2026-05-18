"""Tests for blueprint-scenario deterministic anchor validation."""

from app.services.scenario_keyword_validator import validate_scenario_against_blueprint


def test_keyword_validator_given_when_then_sections() -> None:
    blueprint = {
        "allowed_test_data_placeholders": [],
        "mandatory_anchors": {
            "given": [{"anchor_id": "g1", "text": "Booking", "match_type": "exact_or_contained"}],
            "when": [{"anchor_id": "w1", "text": "Continue", "match_type": "exact_or_contained"}],
            "then": [{"anchor_id": "t1", "text": "Done", "match_type": "exact_or_contained"}],
        },
        "traceability": {"source_transition_ids": [], "expected_feedback_ids": []},
        "source_intent_id": "intent_x",
        "source_flow_id": "flow_y",
    }
    scenario_ok = {
        "start_state": "sA",
        "end_state": "sB",
        "steps": [
            {"keyword": "Given", "text": "the user sees Booking"},
            {"keyword": "When", "text": "clicks Continue"},
            {"keyword": "Then", "text": "the Done state is reached"},
        ],
    }
    r = validate_scenario_against_blueprint(scenario_ok, blueprint)
    assert r["grounding_passed"] is True
    assert r["readability_passed"] is True
    assert r["full_pre_audit_passed"] is True


def test_keyword_validator_forbidden_pipeline_terms() -> None:
    blueprint = {
        "allowed_test_data_placeholders": [],
        "mandatory_anchors": {
            "given": [{"anchor_id": "g1", "text": "Booking", "match_type": "exact_or_contained"}],
            "when": [{"anchor_id": "w1", "text": "Continue", "match_type": "exact_or_contained"}],
            "then": [{"anchor_id": "t1", "text": "Done", "match_type": "exact_or_contained"}],
        },
        "traceability": {"source_transition_ids": [], "expected_feedback_ids": []},
        "source_intent_id": "intent_x",
        "source_flow_id": "flow_y",
    }
    scenario_bad = {
        "start_state": "sA",
        "end_state": "sB",
        "steps": [
            {"keyword": "Given", "text": "the user sees Booking"},
            {"keyword": "When", "text": "clicks Continue"},
            {"keyword": "Then", "text": 'Done — the flow does not remain on the destination state'},
        ],
    }
    r = validate_scenario_against_blueprint(scenario_bad, blueprint)
    assert r["grounding_passed"] is True
    assert r["readability_passed"] is False
    assert "flow does not" in r["forbidden_pipeline_terms"]
    assert r["full_pre_audit_passed"] is False


def test_keyword_validator_overlong_step() -> None:
    long_then = "Done" + ("x" * 200)
    blueprint = {
        "allowed_test_data_placeholders": [],
        "mandatory_anchors": {
            "given": [{"anchor_id": "g1", "text": "Booking", "match_type": "exact_or_contained"}],
            "when": [{"anchor_id": "w1", "text": "Continue", "match_type": "exact_or_contained"}],
            "then": [{"anchor_id": "t1", "text": "Done", "match_type": "exact_or_contained"}],
        },
        "traceability": {},
        "source_intent_id": "intent_x",
        "source_flow_id": "flow_y",
    }
    scenario = {
        "start_state": "sA",
        "end_state": "sB",
        "steps": [
            {"keyword": "Given", "text": "Booking", "step_number": 1},
            {"keyword": "When", "text": "Continue", "step_number": 2},
            {"keyword": "Then", "text": long_then, "step_number": 3},
        ],
    }
    r = validate_scenario_against_blueprint(scenario, blueprint)
    assert r["grounding_passed"] is True
    assert r["readability_passed"] is False
    assert 3 in r["overlong_step_numbers"]


def test_keyword_validator_placeholder_allowlist() -> None:
    blueprint = {
        "allowed_test_data_placeholders": ["<email>"],
        "mandatory_anchors": {"given": [], "when": [], "then": []},
        "traceability": {},
        "source_intent_id": "intent_x",
        "source_flow_id": "flow_y",
    }
    bad = {"steps": [{"keyword": "When", "text": "enters <oops>"}], "start_state": "", "end_state": ""}
    r = validate_scenario_against_blueprint(bad, blueprint)
    assert r["unexpected_placeholders"]
