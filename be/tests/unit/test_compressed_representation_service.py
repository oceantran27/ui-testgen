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
    assert g0["actions"]
    assert g0["actions"][0] == ("act_dent", "click", "Dental", "Dental", "unknown")

    stats = pkg.get("compression_stats") or {}
    assert stats.get("screen_count") == 1
    assert stats.get("char_count", 0) > 0
    assert "dropped_fields" in stats

    ok, err = validate_compressed_catalog_size(pkg, max_screens=10)
    assert ok and err is None


def test_run_build_compressed_catalog_selection_action_rows():
    catalog = [
        {
            "state_id": "st_559c031df702_BOOK_S03.png",
            "source_image_id": "img_1",
            "upload_order": 1,
            "domain": "booking",
            "screen_type": "form",
            "screen_purpose": "Choose time",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_feedback": [],
            "visible_elements": [],
            "interaction_groups": [],
            "available_actions": [
                {"action_id": "st_559c031df702_BOOK_S03.png_ac_004", "action_type": "select", "text": ["Select 09:00", "09:00"]},
                {"action_id": "st_559c031df702_BOOK_S03.png_ac_005", "action_type": "select", "text": ["Select 10:00", "10:00"]},
                {"action_id": "st_559c031df702_BOOK_S03.png_ac_006", "action_type": "select", "text": ["Select 14:00", "14:00"]},
            ],
        }
    ]
    sipkg = {
        "screen_intent_package_id": "sbi_pkg_x",
        "screen_intent_catalog": [
            {
                "source_state_id": "st_559c031df702_BOOK_S03.png",
                "screen_intent_id": "sbi_7bc0fa64ddf9",
                "source_group_id": "g_slot",
                "intent_kind": "selection",
                "intent_name": "time",
                "local_user_goal": "choose appointment time slot",
                "primary_action": {
                    "action_id": "st_559c031df702_BOOK_S03.png_ac_005",
                    "action_type": "select",
                    "text": ["Select 10:00", "10:00"],
                },
                "commit_action": None,
                "secondary_actions": [],
                "selection_options": [
                    {
                        "option_ref_type": "action",
                        "option_action_id": "st_559c031df702_BOOK_S03.png_ac_004",
                        "option_text": ["Select 09:00", "09:00"],
                        "visible_status": "unselected",
                    },
                    {
                        "option_ref_type": "action",
                        "option_action_id": "st_559c031df702_BOOK_S03.png_ac_005",
                        "option_text": ["Select 10:00", "10:00"],
                        "visible_status": "selected",
                    },
                    {
                        "option_ref_type": "action",
                        "option_action_id": "st_559c031df702_BOOK_S03.png_ac_006",
                        "option_text": ["Select 14:00", "14:00"],
                        "visible_status": "disabled",
                    },
                ],
                "local_action_sequence_templates": [],
                "required_input_element_ids": [],
                "evidence_refs": [],
            }
        ],
    }
    pkg = run_build_compressed_catalog(
        run_id="run_x",
        state_catalog=catalog,
        screen_intent_pkg=sipkg,
        ui_state_package=None,
    )
    g0 = pkg["compressed_catalog"][0]["intent_groups"][0]
    rows = [list(r) for r in g0["actions"]]
    assert len(rows) == 3
    assert rows[0] == [
        "st_559c031df702_BOOK_S03.png_ac_004",
        "select",
        "Select 09:00 09:00",
        "09:00",
        "unselected",
    ]
    assert rows[1] == [
        "st_559c031df702_BOOK_S03.png_ac_005",
        "select",
        "Select 10:00 10:00",
        "10:00",
        "selected",
    ]
    assert rows[2] == [
        "st_559c031df702_BOOK_S03.png_ac_006",
        "select",
        "Select 14:00 14:00",
        "14:00",
        "disabled",
    ]


def test_continuity_entities_from_date_time_and_order():
    catalog = [
        {
            "state_id": "st_x",
            "source_image_id": "img_1",
            "upload_order": 1,
            "domain": "booking",
            "screen_type": "form",
            "screen_purpose": "Review",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_feedback": [
                {"feedback_id": "f1", "feedback_type": "success", "text": ["Confirmed booking #BOOK12345"]},
            ],
            "visible_elements": [
                {"element_id": "eh", "element_type": "heading", "text": ["Appointment on 2026-05-18"]},
                {"element_id": "ein", "element_type": "input", "role_hint": "required_input", "text": ["10:30"]},
            ],
            "interaction_groups": [],
            "available_actions": [],
        }
    ]
    sipkg = {"screen_intent_package_id": "p1", "screen_intent_catalog": []}
    pkg = run_build_compressed_catalog(
        run_id="run_x",
        state_catalog=catalog,
        screen_intent_pkg=sipkg,
    )
    cont = pkg["compressed_catalog"][0]["continuity_entities"]
    types = {e["entity_type"] for e in cont}
    assert "date" in types
    assert "time" in types
    assert "order" in types
    texts_flat = " ".join(t for e in cont for t in (e.get("text") or []))
    assert "2026-05-18" in texts_flat
    assert "10:30" in texts_flat
    assert "BOOK12345" in texts_flat


def test_continuity_entities_empty_without_signals():
    catalog = [
        {
            "state_id": "st_plain",
            "source_image_id": "img_1",
            "upload_order": 1,
            "domain": "generic",
            "screen_type": "landing",
            "screen_purpose": "Welcome",
            "presentation_scope": "full_screen",
            "outcome_state_type": "neutral",
            "visible_feedback": [],
            "visible_elements": [
                {"element_id": "h1", "element_type": "heading", "text": ["Welcome"]},
            ],
            "interaction_groups": [],
            "available_actions": [],
        }
    ]
    sipkg = {"screen_intent_package_id": "p1", "screen_intent_catalog": []}
    pkg = run_build_compressed_catalog(
        run_id="run_x",
        state_catalog=catalog,
        screen_intent_pkg=sipkg,
    )
    assert pkg["compressed_catalog"][0]["continuity_entities"] == []
