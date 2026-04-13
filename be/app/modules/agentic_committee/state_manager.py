import asyncio

from app.modules.agentic_committee.models import CommitteeState


class CommitteeStateManager:
    def __init__(self):
        self._states: dict[str, CommitteeState] = {}
        self._lock = asyncio.Lock()

    async def save_state(self, state: CommitteeState) -> None:
        async with self._lock:
            self._states[state.scenario_id] = state.model_copy(deep=False)

    async def get_state(self, scenario_id: str) -> CommitteeState | None:
        async with self._lock:
            state = self._states.get(scenario_id)
            return state.model_copy(deep=True) if state else None

    async def clear_state(self, scenario_id: str) -> None:
        async with self._lock:
            self._states.pop(scenario_id, None)
