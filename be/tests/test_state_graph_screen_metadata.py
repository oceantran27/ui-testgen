"""state_graph_screen_metadata helpers."""

from app.schemas.ui_extraction import (
    NavDestination,
    UIExtractedControl,
    UIExtractionOverview,
    UIExtractionResult,
    UISemanticGroup,
)
from app.schemas.state_graph import StateGraphInputScreen
from app.services.state_graph_screen_metadata import (
    build_state_graph_screen_dict,
    navigational_destinations_from_extraction,
    primary_heading_from_extraction,
)


def _sample_extraction() -> UIExtractionResult:
    return UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="Checkout flow"),
        controls=[
            UIExtractedControl(
                id="h1",
                role="heading",
                label="Payment",
                value="Payment",
                associated_context="",
                is_primary_layer=True,
            ),
            UIExtractedControl(
                id="lnk_help",
                role="link",
                label="",
                value="Help center",
                associated_context="",
                is_primary_layer=True,
            ),
            UIExtractedControl(
                id="lnk_terms",
                role="link",
                label="Terms",
                value="Terms",
                associated_context="",
                is_primary_layer=True,
            ),
            UIExtractedControl(
                id="lnk_privacy",
                role="link",
                label="Privacy",
                value="Privacy",
                associated_context="",
                is_primary_layer=True,
            ),
        ],
        groups=[
            UISemanticGroup(
                id="nav",
                summary="footer",
                controls=["lnk_terms", "lnk_privacy"],
                destinations=[
                    NavDestination(control="lnk_terms", label="Terms"),
                    NavDestination(control="lnk_privacy", label="Privacy"),
                ],
            ),
        ],
    )


def test_navigational_destinations_prefers_groups_then_links():
    ex = _sample_extraction()
    out = navigational_destinations_from_extraction(ex)
    assert "Terms" in out
    assert "Privacy" in out
    assert "Help center" in out


def test_primary_heading_prefers_heading_role():
    ex = _sample_extraction()
    assert primary_heading_from_extraction(ex) == "Payment"


def test_primary_heading_fallback_to_page_summary():
    ex = UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="Only summary"),
        controls=[
            UIExtractedControl(
                id="b",
                role="button",
                label="OK",
                value="OK",
                associated_context="",
                is_primary_layer=True,
            ),
        ],
        groups=[],
    )
    assert primary_heading_from_extraction(ex) == "Only summary"


def test_build_state_graph_screen_validates_as_state_graph_input_screen():
    ex = _sample_extraction()
    intents = [{"intent": "Pay", "control_ids": ["h1"]}]
    d = build_state_graph_screen_dict(image_id="abc123", extraction=ex, user_intents=intents)
    m = StateGraphInputScreen.model_validate(d)
    assert m.image_id == "abc123"
    assert m.ui_state_type == "full_page"
    assert m.primary_heading == "Payment"
    assert m.page_summary == "Checkout flow"
    assert m.navigational_destinations
    assert m.user_intents == intents
