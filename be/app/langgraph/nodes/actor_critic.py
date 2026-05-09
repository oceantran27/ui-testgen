import logging
import asyncio
from typing import Literal

from langgraph.graph import StateGraph, END, START
from app.langgraph.state import ActorCriticState
from app.services.test_scenario_generator_service import generate_flow_scenarios, evaluate_flow_scenarios

logger = logging.getLogger(__name__)

async def actor_node(state: ActorCriticState):
    """
    Actor node: Generates End-to-End flow scenarios.
    """
    flow = state["flow"]
    nodes_metadata = state["nodes_metadata"]
    openai_model = state["openai_model"]
    current_feedback = state.get("current_feedback", "")
    iterations = state.get("iterations", 0)
    
    flow_id = flow.get("id", "unknown")
    logger.info(f"Generating flow scenarios for {flow_id} (Attempt {iterations + 1})")
    
    scenarios = await asyncio.to_thread(
        generate_flow_scenarios, flow, nodes_metadata, openai_model, current_feedback
    )
    
    return {
        "best_scenarios": scenarios,
        "iterations": iterations + 1
    }

async def critic_node(state: ActorCriticState):
    """
    Critic node: Evaluates the generated scenarios.
    """
    scenarios = state["best_scenarios"]
    nodes_metadata = state["nodes_metadata"]
    openai_model = state["openai_model"]
    
    flow_id = state["flow"].get("id", "unknown")
    logger.info(f"Evaluating flow scenarios for {flow_id} with Critic")
    
    evaluation = await asyncio.to_thread(
        evaluate_flow_scenarios, scenarios, nodes_metadata, openai_model
    )
    
    if evaluation.is_passed:
        logger.info(f"Critic approved flow scenarios for {flow_id}!")
    else:
        logger.warning(f"Critic rejected flow scenarios for {flow_id}: {evaluation.feedback}")
        
    return {
        "is_passed": evaluation.is_passed,
        "current_feedback": evaluation.feedback
    }

def should_continue(state: ActorCriticState) -> Literal["actor", "__end__"]:
    """
    Router determining whether to retry the actor or end the loop.
    """
    if state["is_passed"]:
        return "__end__"
    
    if state["iterations"] >= state["max_iterations"]:
        flow_id = state["flow"].get("id", "unknown")
        logger.error(f"Max iterations reached for flow {flow_id}. Returning best effort.")
        return "__end__"
        
    return "actor"

# Build the subgraph
actor_critic_builder = StateGraph(ActorCriticState)

actor_critic_builder.add_node("actor", actor_node)
actor_critic_builder.add_node("critic", critic_node)

actor_critic_builder.add_edge(START, "actor")
actor_critic_builder.add_edge("actor", "critic")
actor_critic_builder.add_conditional_edges("critic", should_continue)

actor_critic_graph = actor_critic_builder.compile()
