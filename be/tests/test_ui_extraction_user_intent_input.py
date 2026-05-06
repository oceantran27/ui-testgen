"""filter_scoped_ui_extraction + user_intent_input_to_minified_json for user-intents stage."""

import json

from app.schemas.ui_extraction import (
    GroupSearchPair,
    NavDestination,
    UIExtractedControl,
    UIExtractionOverview,
    UIExtractionResult,
    UISemanticGroup,
)
from app.services.ui_extraction_payload import (
    filter_scoped_ui_extraction,
    parse_ui_extraction_payload,
    user_intent_input_to_minified_json,
)


def test_filter_drops_non_primary_layer_and_prunes_groups():
    raw = UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="Modal"),
        controls=[
            UIExtractedControl(
                id="bg_btn",
                role="button",
                label="Behind",
                value="Behind",
                associated_context="",
                is_primary_layer=False,
            ),
            UIExtractedControl(
                id="ok_btn",
                role="button",
                label="OK",
                value="OK",
                associated_context="",
                is_primary_layer=True,
            ),
            UIExtractedControl(
                id="q_inp",
                role="textbox",
                label="Query",
                value="",
                associated_context="",
                is_primary_layer=True,
            ),
            UIExtractedControl(
                id="go_btn",
                role="button",
                label="Go",
                value="Go",
                associated_context="",
                is_primary_layer=True,
            ),
        ],
        groups=[
            UISemanticGroup(
                id="dm1",
                summary="search row",
                controls=["bg_btn", "q_inp", "go_btn"],
                search=GroupSearchPair(input="q_inp", trigger="bg_btn"),
                filters=["go_btn", "bg_btn"],
            ),
            UISemanticGroup(
                id="nav1",
                summary="links",
                controls=["ok_btn"],
                destinations=[
                    NavDestination(control="bg_btn", label="Behind"),
                    NavDestination(control="ok_btn", label="OK"),
                ],
            ),
        ],
    )
    out = filter_scoped_ui_extraction(raw)
    assert len(out.controls) == 3
    assert {c.id for c in out.controls} == {"ok_btn", "q_inp", "go_btn"}
    dm = next(g for g in out.groups if g.id == "dm1")
    assert dm.search is None
    assert dm.controls == ["q_inp", "go_btn"]
    assert dm.filters == ["go_btn"]
    nav = next(g for g in out.groups if g.id == "nav1")
    assert len(nav.destinations or []) == 1
    assert nav.destinations[0].control == "ok_btn"


def test_user_intent_minified_json_has_no_is_primary_layer_key():
    raw = UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="p"),
        controls=[
            UIExtractedControl(
                id="a",
                role="button",
                label="A",
                value="A",
                associated_context="",
                is_primary_layer=True,
            ),
        ],
        groups=[],
    )
    scoped = filter_scoped_ui_extraction(raw)
    s = user_intent_input_to_minified_json(scoped)
    data = json.loads(s)
    assert len(data["controls"]) == 1
    assert "is_primary_layer" not in data["controls"][0]


def test_filter_empty_controls_valid():
    raw = UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="empty"),
        controls=[],
        groups=[],
    )
    out = filter_scoped_ui_extraction(raw)
    assert len(out.controls) == 0
    s = user_intent_input_to_minified_json(out)
    assert json.loads(s)["controls"] == []


def test_parse_ui_extraction_migrates_legacy_v4_fields():
    raw = """{
      "schema_version": "ui-flat-v4",
      "overview": {"page": "Test", "control_count": 999},
      "controls": [
        {"id": "a", "role": "button", "text": "A", "label": "A", "scope": true}
      ],
      "groups": []
    }"""
    result = parse_ui_extraction_payload(raw)
    assert result.overview.viewport_description == "Test"
    assert len(result.controls) == 1
    assert result.controls[0].value == "A"
    assert result.controls[0].is_primary_layer is True


def test_parse_ui_extraction_accepts_ui_flat_v5():
    raw = """{
      "schema_version": "ui-flat-v5",
      "overview": {"viewport_description": "Grid view"},
      "controls": [
        {
          "id": "btn_x",
          "role": "button",
          "label": "X",
          "value": "X",
          "associated_context": "",
          "is_primary_layer": true,
          "states": {"disabled": false}
        }
      ],
      "groups": []
    }"""
    result = parse_ui_extraction_payload(raw)
    assert result.schema_version == "ui-flat-v5"
    assert result.controls[0].states.disabled is False


def test_parse_drops_search_when_input_or_trigger_null():
    raw = """{
      "schema_version": "ui-flat-v5",
      "overview": {"viewport_description": "Shop"},
      "controls": [
        {"id": "q", "role": "textbox", "label": "Search", "value": "", "associated_context": "", "is_primary_layer": true},
        {"id": "go", "role": "button", "label": "Go", "value": "Go", "associated_context": "", "is_primary_layer": true}
      ],
      "groups": [
        {
          "id": "g1",
          "summary": "search",
          "controls": ["q", "go"],
          "search": {"input": null, "trigger": "go"}
        }
      ]
    }"""
    result = parse_ui_extraction_payload(raw)
    assert len(result.groups) == 1
    assert result.groups[0].search is None
