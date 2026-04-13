import logging
from collections.abc import Iterable

from app.core.config import settings
from app.modules.committee_ranker.models import (
    CommitteeRankerMetadata,
    CommitteeRankerResult,
    CommitteeScenarioInput,
    RankedCommitteeScenarioOutput,
)

logger = logging.getLogger(__name__)


class CommitteeRankerService:
    def rank(self, scenarios: Iterable[CommitteeScenarioInput | dict]) -> CommitteeRankerResult:
        normalized_scenarios = [
            scenario if isinstance(scenario, CommitteeScenarioInput) else CommitteeScenarioInput.model_validate(scenario)
            for scenario in scenarios
        ]

        weights = self._normalized_weights()
        enriched_rows: list[dict] = []

        for original_index, scenario in enumerate(normalized_scenarios):
            final_score = (
                scenario.BA_score * weights["BA_score"]
                + scenario.QA_score * weights["QA_score"]
                + scenario.UX_score * weights["UX_score"]
            )
            enriched_rows.append(
                {
                    "original_index": original_index,
                    "scenario": scenario,
                    "final_score": round(float(final_score), 4),
                }
            )

        sorted_rows = sorted(enriched_rows, key=lambda item: item["final_score"], reverse=True)

        ranked_scenarios: list[RankedCommitteeScenarioOutput] = []
        for rank_position, row in enumerate(sorted_rows, start=1):
            scenario = row["scenario"]
            ranked_scenarios.append(
                RankedCommitteeScenarioOutput(
                    scenario_id=scenario.scenario_id,
                    user_goal=scenario.user_goal,
                    conflict_resolution_summary=scenario.conflict_resolution_summary,
                    BA_score=scenario.BA_score,
                    QA_score=scenario.QA_score,
                    UX_score=scenario.UX_score,
                    final_score=row["final_score"],
                    rank_position=rank_position,
                )
            )

        metadata = CommitteeRankerMetadata(
            version=settings.COMMITTEE_RANKER_VERSION,
            weights=weights,
        )

        return CommitteeRankerResult(
            metadata=metadata,
            ranked_scenarios=ranked_scenarios,
        )

    def _normalized_weights(self) -> dict[str, float]:
        raw_weights = {
            "BA_score": max(settings.COMMITTEE_WEIGHT_BA, 0.0),
            "QA_score": max(settings.COMMITTEE_WEIGHT_QA, 0.0),
            "UX_score": max(settings.COMMITTEE_WEIGHT_UX, 0.0),
        }
        total = sum(raw_weights.values())

        if total <= 0:
            logger.warning("Committee weights sum to 0. Falling back to default 0.4/0.3/0.3.")
            return {
                "BA_score": 0.4,
                "QA_score": 0.3,
                "UX_score": 0.3,
            }

        return {
            key: round(value / total, 6)
            for key, value in raw_weights.items()
        }


committee_ranker_service = CommitteeRankerService()
