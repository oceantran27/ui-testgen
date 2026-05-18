"""Unit tests for deterministic compressed_catalog builder."""

from app.services.compressed_representation_service import (
    run_build_compressed_catalog,
    validate_compressed_catalog_size,
)


def test_run_build_compressed_catalog_shape():
    catalog = [
        {
            "state_id": "st_1",
            "source_image_id": "img_1",
            "upload_order": 1,
            "domain": "booking",
            "screen_type": "form",
            "screen_purpose": "Select service",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_feedback": [{"feedback_id": "fb_1", "feedback_type": "error", "text": ["Error"]}],
            "visible_elements": [{"element_id": "h1", "element_type": "heading", "text": ["Services"]}],
            "interaction_groups": [{"group_id": "ig_1", "group_type": "form"}],
            "available_actions": [
                {
                    "action_id": "act_dent",
                    "action_type": "click",
                    "text": ["Dental"],
                    "action_priority": "primary",
                }
            ],
        }
    ]
    sipkg = {
        "screen_intent_package_id": "sbi_pkg_x",
        "screen_intent_catalog": [
            {
                "source_state_id": "st_1",
                "screen_intent_id": "sbi_1",
                "source_group_id": "g_a",
                "intent_kind": "selection",
                "intent_name": "pick",
                "local_user_goal": "Choose dental",
                "primary_action": {"action_id": "act_dent", "action_type": "click", "text": ["Dental"]},
                "commit_action": {"action_id": "act_cont", "action_type": "click", "text": ["Continue"]},
                "secondary_actions": [],
                "selection_options": [],
                "local_action_sequence_templates": [],
                "required_input_element_ids": [],
                "evidence_refs": [{"evidence_type": "feedback_text", "source_id": "fb_1"}],
                "confidence": "high",
                "model_confidence": "high",
                "validation_confidence": "high",
            }
        ],
    }
    ui_pkg = {"ui_state_package_id": "ui_pkg_y"}
    pkg = run_build_compressed_catalog(
        run_id="run_x",
        state_catalog=catalog,
        screen_intent_pkg=sipkg,
        ui_state_package=ui_pkg,
    )
    assert pkg.get("compressed_catalog")
    assert pkg.get("catalog_version") == "compressed_catalog_v2"
    assert pkg.get("catalog_purpose") == "global_flow_discovery_input"
    assert "trace_index" in pkg and pkg["trace_index"].get("st_1")
    assert pkg["trace_index"]["st_1"]["ui_state_package_ref"] == "ui_pkg_y"
    assert pkg["trace_index"]["st_1"]["screen_intent_package_ref"] == "sbi_pkg_x"

    c0 = pkg["compressed_catalog"][0]
    assert c0["state_id"] == "st_1"
    assert "upload_order" not in c0
    assert c0["taxonomy"]["domain"] == "booking"
    assert c0["taxonomy"]["screen_type"] == "form"
    assert c0["visible_signature"]["headings"] == ["Services"]
    assert c0["intent_groups"]
    g0 = c0["intent_groups"][0]
    assert g0["intent_id"] == "sbi_1"
    assert g0["source_group_id"] == "g_a"
    pa = g0["primary_action"]
    assert pa["action_id"] == "act_dent"
    assert "Dental" in pa["text"]
    assert "fb_1" in g0["feedback_refs"]

    stats = pkg.get("compression_stats") or {}
    assert stats.get("screen_count") == 1
    assert stats.get("char_count", 0) > 0
    assert "dropped_fields" in stats

    ok, err = validate_compressed_catalog_size(pkg, max_screens=10)
    assert ok and err is None
