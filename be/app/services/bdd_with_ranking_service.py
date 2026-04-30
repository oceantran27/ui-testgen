"""Bundle shape for /happy-path-ranked: BDD generation plus LLM ranking by business_intent."""

from __future__ import annotations

from app.modules.bdd_scenario_ranking import bdd_scenario_ranking_service
from app.schemas.bdd_happy_path_ranked import BddHappyPathRankedResponse, VisionExtractionSummary
from app.services.bdd_happy_path_service import bdd_happy_path_service
from app.services.bdd_payload import build_combined_gherkin


class BddWithRankingService:
    async def generate_ranked_response(self, image_path: str) -> BddHappyPathRankedResponse:
        bdd = await bdd_happy_path_service.generate(image_path)
        reordered = await bdd_scenario_ranking_service.rank_scenarios(
            business_intent=bdd.feature.business_intent,
            scenarios=bdd.scenarios,
        )
        bdd = bdd.model_copy(
            update={
                "scenarios": reordered,
                "combined_gherkin": build_combined_gherkin(bdd.feature, reordered),
            }
        )
        return BddHappyPathRankedResponse(
            bdd=bdd,
            vision_model="none",
            vision=VisionExtractionSummary(),
        )


bdd_with_ranking_service = BddWithRankingService()
