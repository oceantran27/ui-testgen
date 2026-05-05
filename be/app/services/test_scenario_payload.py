"""Parse and normalize test-scenario suite JSON from model output."""

from __future__ import annotations

import json

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.test_scenario_generation import (
    ScreenFeatureSummary,
    TestScenarioItem,
    TestScenarioSuite,
)


def build_combined_test_scenario(feature: ScreenFeatureSummary, scenarios: list[TestScenarioItem]) -> str:
    lines: list[str] = [
        f"Feature: {feature.name}",
    ]
    if feature.description.strip():
        lines.append(feature.description.strip())
    lines.append("")
    for sc in scenarios:
        lines.append(sc.test_scenario.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_test_scenario_suite_payload(raw: str, *, result_model: str) -> TestScenarioSuite:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse test scenario JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid test scenario JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("Test scenario output must be a JSON object")
    feature_raw = data.get("feature") or data.get("Feature")
    if not isinstance(feature_raw, dict):
        raise AIProcessingError("Test scenario output must include object 'feature'")
    if "scenarios" in data:
        scenarios_data = data["scenarios"]
    elif "Scenarios" in data:
        scenarios_data = data["Scenarios"]
    else:
        scenarios_data = None
    if scenarios_data is None:
        scenarios_data = []
    try:
        feature = ScreenFeatureSummary.model_validate(feature_raw)
        if not isinstance(scenarios_data, list):
            raise ValueError("scenarios must be an array (may be empty)")
        scenarios = [TestScenarioItem.model_validate(s) for s in scenarios_data]
    except Exception as exc:
        raise AIProcessingError(f"Invalid test scenario payload shape: {exc}") from exc

    return TestScenarioSuite(
        model=result_model,
        feature=feature,
        scenarios=scenarios,
        combined_test_scenario=build_combined_test_scenario(feature, scenarios),
    )
