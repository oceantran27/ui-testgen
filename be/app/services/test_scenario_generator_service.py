import asyncio
import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.test_scenario_generation import (
    FinalTestOutput,
    FlowScenariosOutput,
    IsolatedScenariosOutput,
    GherkinTestScenario,
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

async def generate_and_refine_flow(
    flow: Dict[str, Any],
    nodes_metadata: List[Dict[str, Any]],
    openai_model: str = "gpt-5-mini",
    max_iterations: int = 3,
) -> FlowScenariosOutput:
    """Actor-Critic Loop for a single flow."""
    flow_id = flow.get("id", "unknown")
    current_feedback = ""
    best_scenarios = None

    for attempt in range(max_iterations):
        logger.info("Generating flow scenarios for %s (Attempt %d/%d)", flow_id, attempt + 1, max_iterations)
        
        # 1. Actor generates
        scenarios = await asyncio.to_thread(
            generate_flow_scenarios, flow, nodes_metadata, openai_model, current_feedback
        )
        best_scenarios = scenarios
        
        # 2. Critic evaluates
        logger.info("Evaluating flow scenarios for %s with Critic", flow_id)
        evaluation = await asyncio.to_thread(
            evaluate_flow_scenarios, scenarios, nodes_metadata, openai_model
        )
        
        # 3. Decision
        if evaluation.is_passed:
            logger.info("Critic approved flow scenarios for %s!", flow_id)
            return scenarios
            
        logger.warning("Critic rejected flow scenarios for %s (Iter %d): %s", flow_id, attempt + 1, evaluation.feedback)
        current_feedback = evaluation.feedback
    
    logger.error("Max iterations reached for flow %s. Returning best effort.", flow_id)
    return best_scenarios

async def generate_all_test_scenarios_async(
    ui_extractions: Dict[str, Dict[str, Any]],
    user_intents: Dict[str, List[Dict[str, Any]]],
    state_graph: Dict[str, Any],
    openai_model: str = "gpt-5-mini",
) -> FinalTestOutput:
    """Orchestrate the generation of flow scenarios concurrently with Self-Reflection."""
    
    # 1. Extract Isolated Scenarios directly from user_intents
    isolated_scenarios: List[IsolatedScenariosOutput] = []
    for image_id, intents in user_intents.items():
        if intents:
            scenarios = []
            for intent_dict in intents:
                scenario_text = intent_dict.get("intent", "Unknown Scenario")
                gherkin_text = intent_dict.get("gherkin", "")
                if gherkin_text:
                    scenarios.append(
                        GherkinTestScenario(scenario=scenario_text, gherkin=gherkin_text)
                    )
            
            if scenarios:
                isolated_scenarios.append(
                    IsolatedScenariosOutput(image_id=image_id, scenarios=scenarios)
                )

    # 2. Generate Flow Scenarios concurrently with Actor-Critic loop
    flows = state_graph.get("flows", [])
    
    async def process_flow(flow: Dict[str, Any]) -> FlowScenariosOutput:
        nodes = flow.get("nodes", [])
        
        # Build metadata for nodes in this flow
        nodes_metadata = []
        for node_id in nodes:
            nodes_metadata.append({
                "image_id": node_id,
                "ui_extraction": ui_extractions.get(node_id, {}),
                "user_intents": user_intents.get(node_id, []),
            })
            
        return await generate_and_refine_flow(flow, nodes_metadata, openai_model)

    tasks = [process_flow(flow) for flow in flows]
    flow_scenarios = list(await asyncio.gather(*tasks))

    return FinalTestOutput(
        isolated_scenarios=isolated_scenarios,
        flow_scenarios=flow_scenarios,
    )

def generate_all_test_scenarios(
    ui_extractions: Dict[str, Dict[str, Any]],
    user_intents: Dict[str, List[Dict[str, Any]]],
    state_graph: Dict[str, Any],
    openai_model: str = "gpt-5-mini",
) -> FinalTestOutput:
    """Synchronous wrapper for generate_all_test_scenarios_async."""
    return asyncio.run(
        generate_all_test_scenarios_async(
            ui_extractions, user_intents, state_graph, openai_model
        )
    )
