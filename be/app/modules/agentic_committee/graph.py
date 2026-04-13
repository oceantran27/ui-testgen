from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph


class CommitteeGraphState(TypedDict, total=False):
    scenario_id: str
    user_goal: str
    page_overview: dict[str, Any]
    scenario: dict[str, Any]
    model_name: str
    current_round: int
    opinions_history: dict[int, dict[str, dict[str, Any]]]
    compressed_context: str
    targeted_critiques: dict[str, str]
    is_converged: bool
    convergence_reason: str
    final_payload: dict[str, Any] | None


NodeHandler = Callable[[CommitteeGraphState], Awaitable[dict[str, Any]]]
RouteHandler = Callable[[CommitteeGraphState], str]


def build_committee_graph(
    *,
    blind_initial_generation: NodeHandler,
    judge_round: NodeHandler,
    debate_round: NodeHandler,
    finalize: NodeHandler,
    route_after_judge: RouteHandler,
):
    workflow = StateGraph(CommitteeGraphState)

    workflow.add_node("blind_initial_generation", blind_initial_generation)
    workflow.add_node("judge_round", judge_round)
    workflow.add_node("debate_round", debate_round)
    workflow.add_node("finalize", finalize)

    workflow.set_entry_point("blind_initial_generation")
    workflow.add_edge("blind_initial_generation", "judge_round")
    workflow.add_conditional_edges(
        "judge_round",
        route_after_judge,
        {
            "debate_round": "debate_round",
            "finalize": "finalize",
        },
    )
    workflow.add_edge("debate_round", "judge_round")
    workflow.add_edge("finalize", END)

    return workflow.compile()
