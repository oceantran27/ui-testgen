"""Unit tests for DemoBooking regression eval helpers (no live pipeline)."""

from fixtures.demobooking.eval import (
    evaluate_discovery_flows,
    evaluate_final_output_keywords,
    evaluate_global_discovery_on_compressed_catalog,
    evaluate_verified_transitions,
    load_ground_truth_flows,
)


def test_load_ground_truth_has_five_flows():
    flows = load_ground_truth_flows()
    assert len(flows) == 5
    ids = {f["flow_id"] for f in flows}
    assert ids == {"BOOK_F01", "BOOK_F02", "BOOK_F03", "BOOK_F04", "BOOK_F05"}


def test_evaluate_verified_transitions_happy_path_pairs():
    """Two states map to BOOK_S01/BOOK_S02; one verified edge covers F01 first hop."""
    cards = [
        {
            "state_id": "st_a",
            "visible_text": ["Book a Service", "DemoBooking", "Dental checkup"],
            "outcome_state_type": "neutral",
            "presentation_scope": "main",
        },
        {
            "state_id": "st_b",
            "visible_text": ["Dental checkup", "Duration", "Price"],
            "outcome_state_type": "neutral",
            "presentation_scope": "main",
        },
    ]
    verified = [{"from_state": "st_a", "to_state": "st_b", "proposal_status": "vlm_verified"}]
    m = evaluate_verified_transitions(verified, cards)
    assert m["transition_recall_hit"] >= 1
    f01 = next(x for x in m["flow_results"] if x["flow_id"] == "BOOK_F01")
    assert f01["matched_edges"] >= 1


def test_evaluate_discovery_flows_subsequence():
    cards = [
        {
            "state_id": "s1",
            "visible_text": ["Book a Service", "DemoBooking"],
            "outcome_state_type": "neutral",
            "presentation_scope": "main",
        },
        {
            "state_id": "s2",
            "visible_text": ["Dental checkup", "Duration"],
            "outcome_state_type": "neutral",
            "presentation_scope": "main",
        },
    ]
    discovery = {
        "candidate_flows": [
            {
                "flow_id": "cf_test",
                "ordered_states": ["s1", "s2"],
            }
        ]
    }
    m = evaluate_discovery_flows(discovery, cards)
    f01 = next(x for x in m["flow_subsequence_checks"] if x["flow_id"] == "BOOK_F01")
    assert f01["best_subsequence_hit"] >= 2


def test_evaluate_global_discovery_on_compressed_catalog_smoke():
    compressed_catalog = [
        {
            "state_id": "s1",
            "presentation_scope": "main",
            "outcome_state_type": "neutral",
            "screen_purpose": "Book a Service",
            "intent_groups": [
                {
                    "user_intent": "start booking",
                    "primary_actions": ["Dental"],
                    "feedback_signals": [],
                }
            ],
        },
        {
            "state_id": "s2",
            "presentation_scope": "main",
            "outcome_state_type": "neutral",
            "screen_purpose": "Dental checkup",
            "intent_groups": [],
        },
    ]
    bundle = {"candidate_flows": [{"flow_id": "demo", "ordered_states": ["s1", "s2"]}]}
    _ = evaluate_global_discovery_on_compressed_catalog(bundle, compressed_catalog)


def test_evaluate_final_output_keywords_smoke():
    final = {
        "behaviour_scenarios": [
            {"title": "Book Dental appointment and confirm"},
            {"title": "Cancel appointment from my list"},
        ]
    }
    m = evaluate_final_output_keywords(final)
    assert m["exported_scenario_count"] == 2
    assert any(h["flow_id"] == "BOOK_F01" and h["hit"] for h in m["keyword_hits"])
