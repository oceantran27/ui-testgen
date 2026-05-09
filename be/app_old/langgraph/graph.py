import json
import os
import logging

from langgraph.graph import StateGraph, END, START
from langgraph.pregel import RetryPolicy
from langgraph.types import Send

from app.schemas.test_scenario_generation import FinalTestOutput, IsolatedScenariosOutput, GherkinTestScenario
from app.langgraph.state import PipelineGraphState, ActorCriticState
from app.langgraph.nodes.dedupe import dedupe_node
from app.langgraph.nodes.screen_analysis import process_screen_node
from app.langgraph.nodes.state_graph import state_graph_node
from app.langgraph.nodes.actor_critic import actor_critic_graph

logger = logging.getLogger(__name__)


def continue_to_screen_analysis(state: PipelineGraphState):
    """Map over canonical paths and send to screen analysis node."""
    extract_model = state["extract_model"]
    intent_model = state["intent_model"]
    out_dir = state["out_dir"]
    
    sends = []
    for path in state["canonical_paths"]:
        image_id = state["input_path_to_image_id"][path]
        sends.append(
            Send(
                "process_screen", 
                {
                    "path": path,
                    "image_id": image_id,
                    "extract_model": extract_model,
                    "intent_model": intent_model,
                    "out_dir": out_dir
                }
            )
        )
    return sends


def continue_to_actor_critic(state: PipelineGraphState):
    """Map over flows and send to actor-critic subgraph."""
    ui_extractions = state["ui_extractions"]
    user_intents_by_image = state["user_intents_by_image"]
    openai_model = state["e2e_model"]
    
    sends = []
    for flow in state["flows"]:
        # Handle Pydantic objects if necessary
        nodes = flow.nodes if hasattr(flow, 'nodes') else flow.get("nodes", [])
        flow_dict = flow.model_dump(mode="json") if hasattr(flow, 'model_dump') else flow
        
        nodes_metadata = []
        for node_id in nodes:
            nodes_metadata.append({
                "image_id": node_id,
                "ui_extraction": ui_extractions.get(node_id, {}),
                "user_intents": user_intents_by_image.get(node_id, []),
            })
            
        sends.append(
            Send(
                "actor_critic_wrapper",
                {
                    "flow": flow_dict,
                    "nodes_metadata": nodes_metadata,
                    "openai_model": openai_model,
                    "iterations": 0,
                    "max_iterations": 3,
                    "current_feedback": "",
                    "best_scenarios": None,
                    "is_passed": False
                }
            )
        )
    return sends


async def actor_critic_wrapper(state: ActorCriticState):
    """Wrapper to invoke the subgraph and return the output shaped for the main state."""
    result = await actor_critic_graph.ainvoke(state)
    return {"flow_scenarios": [result["best_scenarios"]]}


def aggregate_results_node(state: PipelineGraphState):
    """Aggregates isolated scenarios and flow scenarios into FinalTestOutput."""
    out_dir = state["out_dir"]
    user_intents = state["user_intents_by_image"]
    flow_scenarios = state.get("flow_scenarios", [])
    
    # 1. Extract Isolated Scenarios directly from user_intents
    isolated_scenarios = []
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
                
    final_test_output = FinalTestOutput(
        isolated_scenarios=isolated_scenarios,
        flow_scenarios=flow_scenarios,
    )
    
    try:
        with open(os.path.join(out_dir, "final_test_output.json"), "w", encoding="utf-8") as f:
            json.dump(final_test_output.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning(f"Could not write artifact final_test_output.json: {exc}")

    return {
        "final_test_output": final_test_output
    }


# Build the main pipeline graph
builder = StateGraph(PipelineGraphState)

builder.add_node("dedupe", dedupe_node)
builder.add_node("process_screen", process_screen_node, retry=RetryPolicy(max_attempts=2)) # 1 attempt + 1 retry
builder.add_node("state_graph", state_graph_node)
builder.add_node("actor_critic_wrapper", actor_critic_wrapper)
builder.add_node("aggregate_results", aggregate_results_node)

builder.add_edge(START, "dedupe")
builder.add_conditional_edges("dedupe", continue_to_screen_analysis, ["process_screen"])
builder.add_edge("process_screen", "state_graph")
builder.add_conditional_edges("state_graph", continue_to_actor_critic, ["actor_critic_wrapper"])
builder.add_edge("actor_critic_wrapper", "aggregate_results")
builder.add_edge("aggregate_results", END)
