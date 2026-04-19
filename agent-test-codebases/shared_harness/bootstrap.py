from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.schemas.pipeline import BusinessAnalystOutput, RawScenarioList, VisualParserOutput
from app.services.prompt_service import (
    load_business_analyst_prompt,
    load_qa_generator_prompt,
    load_verifier_prompt,
    load_visual_parser_prompt,
)

from .stage_runner import StageRunner


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_visual_parser_live(runner: StageRunner, image_path: str) -> dict[str, Any]:
    result = runner.run_stage(
        stage_name="visual_parser",
        prompt_text=load_visual_parser_prompt(),
        temperature=0.1,
        image_path=image_path,
        context_text=None,
        user_instruction="Input: UI screenshot. Produce the Visual Parser JSON.",
        schema_model=VisualParserOutput,
    )
    return result.validated_json


def run_business_analyst_live(runner: StageRunner, image_path: str, vp_json: dict[str, Any]) -> dict[str, Any]:
    result = runner.run_stage(
        stage_name="business_analyst",
        prompt_text=load_business_analyst_prompt(),
        temperature=0.3,
        image_path=image_path,
        context_text=f"Visual Parser output JSON:\n{json.dumps(vp_json, ensure_ascii=False, separators=(',', ':'))}",
        user_instruction="Input: UI screenshot + parsed elements JSON above. Produce the Business Analyst JSON.",
        schema_model=BusinessAnalystOutput,
    )
    return result.validated_json


def run_qa_generator_live(runner: StageRunner, image_path: str, ba_json: dict[str, Any]) -> dict[str, Any]:
    result = runner.run_stage(
        stage_name="qa_generator",
        prompt_text=load_qa_generator_prompt(),
        temperature=0.7,
        image_path=image_path,
        context_text=f"Business context JSON:\n{json.dumps(ba_json, ensure_ascii=False, separators=(',', ':'))}",
        user_instruction="Input: UI screenshot + business context JSON above. Produce the QA Generator scenarios JSON.",
        schema_model=RawScenarioList,
    )
    return result.validated_json


def run_verifier_live(
    runner: StageRunner,
    image_path: str,
    vp_json: dict[str, Any],
    qa_json: dict[str, Any],
) -> dict[str, Any]:
    result = runner.run_stage(
        stage_name="verifier",
        prompt_text=load_verifier_prompt(),
        temperature=0.0,
        image_path=image_path,
        context_text=(
            f"Visual Parser output JSON:\n{json.dumps(vp_json, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Proposed scenarios JSON:\n{json.dumps(qa_json, ensure_ascii=False, separators=(',', ':'))}"
        ),
        user_instruction=(
            "Input: UI screenshot + visual parser JSON + proposed scenarios JSON above. "
            "Return verified scenarios and include verification metadata for each scenario."
        ),
        schema_model=RawScenarioList,
    )
    return result.validated_json
