import logging
from collections.abc import Iterable

from app.core.config import settings
from app.modules.deterministic_ranker.models import (
    Module2ScenarioInput,
    RankedScenarioOutput,
    RankerMetadata,
    RankerResult,
)

logger = logging.getLogger(__name__)

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None


class DeterministicRankerService:
    def rank(self, scenarios: Iterable[Module2ScenarioInput | dict]) -> RankerResult:
        normalized_scenarios = [
            scenario if isinstance(scenario, Module2ScenarioInput) else Module2ScenarioInput.model_validate(scenario)
            for scenario in scenarios
        ]

        weights = self._normalized_weights()
        should_use_pandas = bool(settings.RANKER_ENABLE_PANDAS and pd is not None)

        if should_use_pandas:
            ranked_scenarios = self._rank_with_pandas(normalized_scenarios, weights)
        else:
            ranked_scenarios = self._rank_with_stdlib(normalized_scenarios, weights)

        metadata = RankerMetadata(
            version=settings.RANKER_VERSION,
            weights=weights,
            used_pandas=should_use_pandas,
        )

        return RankerResult(
            metadata=metadata,
            ranked_scenarios=ranked_scenarios,
        )

    def _rank_with_pandas(
        self,
        scenarios: list[Module2ScenarioInput],
        weights: dict[str, float],
    ) -> list[RankedScenarioOutput]:
        rows = []
        for original_index, scenario in enumerate(scenarios):
            rows.append(
                {
                    "original_index": original_index,
                    "scenario_id": scenario.scenario_id,
                    "user_goal": scenario.user_goal,
                    "rationale": scenario.rationale,
                    "core_alignment": scenario.scores.core_alignment,
                    "frequency": scenario.scores.frequency,
                    "business_risk": scenario.scores.business_risk,
                }
            )

        frame = pd.DataFrame(rows)
        frame["final_score"] = (
            frame["core_alignment"] * weights["core_alignment"]
            + frame["frequency"] * weights["frequency"]
            + frame["business_risk"] * weights["business_risk"]
        )
        # Use stable sort so equal scores preserve original order.
        frame = frame.sort_values(by="final_score", ascending=False, kind="mergesort")
        frame["rank_position"] = range(1, len(frame) + 1)

        ranked_scenarios: list[RankedScenarioOutput] = []
        for row in frame.to_dict(orient="records"):
            ranked_scenarios.append(
                RankedScenarioOutput(
                    scenario_id=str(row["scenario_id"]),
                    user_goal=str(row["user_goal"]),
                    rationale=str(row["rationale"]),
                    scores={
                        "core_alignment": int(row["core_alignment"]),
                        "frequency": int(row["frequency"]),
                        "business_risk": int(row["business_risk"]),
                    },
                    final_score=round(float(row["final_score"]), 4),
                    rank_position=int(row["rank_position"]),
                )
            )

        return ranked_scenarios

    def _rank_with_stdlib(
        self,
        scenarios: list[Module2ScenarioInput],
        weights: dict[str, float],
    ) -> list[RankedScenarioOutput]:
        enriched_rows: list[dict] = []

        for original_index, scenario in enumerate(scenarios):
            final_score = (
                scenario.scores.core_alignment * weights["core_alignment"]
                + scenario.scores.frequency * weights["frequency"]
                + scenario.scores.business_risk * weights["business_risk"]
            )
            enriched_rows.append(
                {
                    "original_index": original_index,
                    "scenario": scenario,
                    "final_score": round(float(final_score), 4),
                }
            )

        # Python sort is stable by default, preserving original order for equal scores.
        sorted_rows = sorted(enriched_rows, key=lambda item: item["final_score"], reverse=True)

        ranked_scenarios: list[RankedScenarioOutput] = []
        for rank_position, row in enumerate(sorted_rows, start=1):
            scenario = row["scenario"]
            ranked_scenarios.append(
                RankedScenarioOutput(
                    scenario_id=scenario.scenario_id,
                    user_goal=scenario.user_goal,
                    rationale=scenario.rationale,
                    scores=scenario.scores,
                    final_score=row["final_score"],
                    rank_position=rank_position,
                )
            )

        return ranked_scenarios

    def _normalized_weights(self) -> dict[str, float]:
        raw_weights = {
            "core_alignment": max(settings.RANKER_WEIGHT_CORE_ALIGNMENT, 0.0),
            "frequency": max(settings.RANKER_WEIGHT_FREQUENCY, 0.0),
            "business_risk": max(settings.RANKER_WEIGHT_BUSINESS_RISK, 0.0),
        }
        total = sum(raw_weights.values())

        if total <= 0:
            logger.warning("Ranker weights sum to 0. Falling back to default 0.4/0.2/0.4.")
            return {
                "core_alignment": 0.4,
                "frequency": 0.2,
                "business_risk": 0.4,
            }

        return {
            key: round(value / total, 6)
            for key, value in raw_weights.items()
        }


deterministic_ranker_service = DeterministicRankerService()
