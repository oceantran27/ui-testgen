from typing import Annotated, Any, TypedDict
import operator

from app.schemas.state_graph import StateGraphFlowItem
from app.schemas.test_scenario_generation import FinalTestOutput, FlowScenariosOutput


def dict_reducer(a: dict, b: dict) -> dict:
    """Merge two dictionaries. If a key exists in both, b overwrites a."""
    if a is None:
        a = {}
    if b is None:
        b = {}
    # Use dictionary unpacking to merge
    return {**a, **b}


def list_reducer(a: list, b: list) -> list:
    """Concatenate two lists."""
    if a is None:
        a = []
    if b is None:
        b = []
    return a + b


class PipelineGraphState(TypedDict):
    """Global state for the multi-agent UI test generation pipeline."""
    input_id: str
    extract_model: str
    intent_model: str
    flow_model: str
    e2e_model: str
    saved_paths: list[str]
    out_dir: str
    
    # Deduplication phase
    canonical_paths: list[str]
    canonical_image_ids: list[str]
    input_path_to_image_id: dict[str, str]
    
    # Screen Analysis phase (Map-Reduce)
    # Using reducers since these are updated by parallel branches
    ui_extractions: Annotated[dict[str, dict[str, Any]], dict_reducer]
    user_intents_by_image: Annotated[dict[str, list[dict[str, Any]]], dict_reducer]
    screen_docs: Annotated[dict[str, dict[str, Any]], dict_reducer]
    
    # State Graph phase
    flows: list[StateGraphFlowItem]
    
    # Final Scenario Generation phase
    flow_scenarios: Annotated[list[FlowScenariosOutput], list_reducer]
    final_test_output: FinalTestOutput | None
    
    # Error handling
    error: str | None


class ActorCriticState(TypedDict):
    """State for the Actor-Critic subgraph working on a single flow."""
    flow: dict[str, Any]
    nodes_metadata: list[dict[str, Any]]
    openai_model: str
    
    # Iteration tracking
    iterations: int
    max_iterations: int
    
    # Feedback loop
    current_feedback: str
    best_scenarios: FlowScenariosOutput | None
    is_passed: bool
