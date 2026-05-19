"""Unit tests for noise-stripped compressed_catalog_v3 builder."""

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
    assert pkg.get("catalog_version") == "compressed_catalog_v3"
    assert pkg.get("catalog_purpose") == "global_flow_discovery_input"
    assert "trace_index" in pkg and pkg["trace_index"].get("st_1")
    assert pkg["trace_index"]["st_1"]["ui_state_package_ref"] == "ui_pkg_y"
    assert pkg["trace_index"]["st_1"]["screen_intent_package_ref"] == "sbi_pkg_x"

    c0 = pkg["compressed_catalog"][0]
    assert c0["state_id"] == "st_1"
    assert "upload_order" not in c0
    assert c0["taxonomy"]["domain"] == "booking"
    assert c0["taxonomy"]["screen_type"] == "form"
    assert c0["visible_elements"][0]["text"] == ["Services"]
    assert c0["visible_feedback"][0]["feedback_id"] == "fb_1"
    assert c0["screen_intents"]
    g0 = c0["screen_intents"][0]
    assert g0["screen_intent_id"] == "sbi_1"
    assert g0["primary_action"]["action_id"] == "act_dent"
    assert "Dental" in g0["primary_action"]["text"]

    acts = {a["action_id"]: a for a in c0["available_actions"]}
    assert acts["act_dent"]["text"] == ["Dental"]

    stats = pkg.get("compression_stats") or {}
    assert stats.get("screen_count") == 1
    assert stats.get("char_count", 0) > 0
    assert "dropped_fields" in stats

    ok, err = validate_compressed_catalog_size(pkg, max_screens=10)
    assert ok and err is None


def test_compression_strips_visual_region_and_keeps_action_ids():
    catalog = [
        {
            "state_id": "st_x",
            "source_image_id": "img_x",
            "domain": "ecommerce",
            "screen_type": "listing",
            "screen_purpose": "Browse",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_elements": [
                {
                    "element_id": "el_1",
                    "element_type": "button",
                    "text": ["Buy"],
                    "role_hint": "primary_action",
                    "visual_region": "main",
                }
            ],
            "available_actions": [
                {
                    "action_id": "ac_1",
                    "action_type": "click",
                    "text": ["Buy"],
                    "visual_region": "main",
                }
            ],
            "visible_feedback": [],
            "interaction_groups": [],
        }
    ]
    pkg = run_build_compressed_catalog(
        run_id="run_z",
        state_catalog=catalog,
        screen_intent_pkg={"screen_intent_catalog": []},
        ui_state_package=None,
    )
    c0 = pkg["compressed_catalog"][0]
    assert "visual_region" not in c0["visible_elements"][0]
    assert "visual_region" not in c0["available_actions"][0]
    assert c0["available_actions"][0]["action_id"] == "ac_1"


def test_interaction_groups_drop_evidence_heavy_fields():
    catalog = [
        {
            "state_id": "st_g",
            "source_image_id": "img_g",
            "domain": "unknown",
            "screen_type": "form",
            "screen_purpose": "Form",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_elements": [],
            "available_actions": [],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig_1",
                    "group_type": "form",
                    "element_ids": ["el_1"],
                    "group_evidence": [{"evidence_type": "intent_anchor", "description": "long"}],
                    "group_confidence": "high",
                }
            ],
        }
    ]
    pkg = run_build_compressed_catalog(
        run_id="run_g",
        state_catalog=catalog,
        screen_intent_pkg={"screen_intent_catalog": []},
        ui_state_package=None,
    )
    g = pkg["compressed_catalog"][0]["interaction_groups"][0]
    assert g["group_id"] == "ig_1"
    assert "group_evidence" not in g
    assert "group_confidence" not in g
