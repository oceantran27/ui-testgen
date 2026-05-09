import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.test_scenario_generation import (
    FlowScenariosOutput,
    CriticEvaluationResult,
)
from app.services.prompt_service import (
    load_flow_scenarios_prompt,
    load_critic_scenarios_prompt,
)

logger = logging.getLogger(__name__)


def generate_flow_scenarios(
    flow: Dict[str, Any],
    nodes_metadata: List[Dict[str, Any]],
    openai_model: str = "gpt-5-mini",
    previous_feedback: str = "",
) -> FlowScenariosOutput:
    """Generate End-to-End flow scenarios (Actor)."""
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")

    system_prompt = load_flow_scenarios_prompt()
    user_text = (
        f"Generate End-to-End flow scenarios for the following journey.\n\n"
        f"Input Data:\n"
        f"- flow: {json.dumps(flow)}\n"
        f"- nodes_metadata: {json.dumps(nodes_metadata)}\n"
    )

    if previous_feedback:
        user_text += (
            f"\n\nIMPORTANT FEEDBACK FROM PREVIOUS ATTEMPT:\n"
            f"Your previous attempt was rejected by the Reviewer. Please fix the following issues:\n"
            f"{previous_feedback}\n"
        )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI flow scenario generation failed: %s", exc)
        raise AIProcessingError(f"Flow scenario generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise AIProcessingError("Received empty response from OpenAI")

    try:
        parsed = FlowScenariosOutput.model_validate_json(content)
    except Exception as exc:
        raise AIProcessingError(f"Invalid flow scenarios payload: {exc}") from exc

    flow_id = flow.get("id", "not_provided")
    if parsed.flow_id != flow_id:
        parsed.flow_id = flow_id

    return parsed


def evaluate_flow_scenarios(
    scenarios: FlowScenariosOutput,
    nodes_metadata: List[Dict[str, Any]],
    openai_model: str = "gpt-5-mini",
) -> CriticEvaluationResult:
    """Evaluate End-to-End flow scenarios (Critic)."""
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")

    system_prompt = load_critic_scenarios_prompt()
    user_text = (
        f"Evaluate the following Gherkin scenarios against the provided UI controls.\n\n"
        f"Input Data:\n"
        f"- nodes_metadata (Ground Truth UI): {json.dumps(nodes_metadata)}\n"
        f"- scenarios_output: {scenarios.model_dump_json()}\n"
    )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI critic evaluation failed: %s", exc)
        raise AIProcessingError(f"Critic evaluation failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise AIProcessingError("Received empty response from OpenAI Critic")

    try:
        parsed = CriticEvaluationResult.model_validate_json(content)
    except Exception as exc:
        raise AIProcessingError(f"Invalid critic evaluation payload: {exc}") from exc

    return parsed
