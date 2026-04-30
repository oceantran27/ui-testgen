"""Parse and normalize BDD happy-path JSON from model output."""

from __future__ import annotations

import json

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.bdd_happy_path import (
    BddFeatureBlock,
    BddHappyPathResult,
    BddScenarioItem,
    BddScenarioPriority,
)

PRIORITY_SORT_ORDER: dict[BddScenarioPriority, int] = {
    "primary": 0,
    "secondary": 1,
    "utility": 2,
}


def sort_scenarios_by_priority(scenarios: list[BddScenarioItem]) -> list[BddScenarioItem]:
    """Stable relative order: primary, then secondary, then utility; ties broken by id."""
    return sorted(scenarios, key=lambda s: (PRIORITY_SORT_ORDER[s.priority], s.id))


def build_combined_gherkin(feature: BddFeatureBlock, scenarios: list[BddScenarioItem]) -> str:
    lines: list[str] = [
        f"Feature: {feature.name}",
    ]
    if feature.description.strip():
        lines.append(feature.description.strip())
    lines.append("")
    for sc in scenarios:
        lines.append(sc.gherkin.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_bdd_payload(raw: str, *, result_model: str) -> BddHappyPathResult:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse BDD JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid BDD JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("BDD output must be a JSON object")
    feature_raw = data.get("feature") or data.get("Feature")
    if not isinstance(feature_raw, dict):
        raise AIProcessingError("BDD output must include object 'feature'")
    if "scenarios" in data:
        scenarios_data = data["scenarios"]
    elif "Scenarios" in data:
        scenarios_data = data["Scenarios"]
    else:
        scenarios_data = None
    if scenarios_data is None:
        scenarios_data = []
    try:
        feature = BddFeatureBlock.model_validate(feature_raw)
        if not isinstance(scenarios_data, list):
            raise ValueError("scenarios must be an array (may be empty)")
        scenarios = [BddScenarioItem.model_validate(s) for s in scenarios_data]
    except Exception as exc:
        raise AIProcessingError(f"Invalid BDD payload shape: {exc}") from exc

    scenarios = sort_scenarios_by_priority(scenarios)
    return BddHappyPathResult(
        model=result_model,
        feature=feature,
        scenarios=scenarios,
        combined_gherkin=build_combined_gherkin(feature, scenarios),
    )
