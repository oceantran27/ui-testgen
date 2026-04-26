"""Legacy bundle shape for /happy-path-ranked; layout-based priority in `bdd` only."""

from __future__ import annotations

from app.schemas.bdd_happy_path_ranked import BddHappyPathRankedResponse, VisionExtractionSummary
from app.services.bdd_happy_path_service import bdd_happy_path_service


class BddWithRankingService:
    async def generate_ranked_response(self, image_path: str) -> BddHappyPathRankedResponse:
        bdd = await bdd_happy_path_service.generate(image_path)
        return BddHappyPathRankedResponse(
            bdd=bdd,
            vision_model="none",
            vision=VisionExtractionSummary(),
        )


bdd_with_ranking_service = BddWithRankingService()
