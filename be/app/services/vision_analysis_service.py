import asyncio
import json
import logging

from pydantic import BaseModel, Field

from app.core.model_selection import normalize_analysis_model_name
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.models import VisionExtractionPayload
from app.modules.vision_extractor.service import VisionExtractorService

logger = logging.getLogger(__name__)


class VisionOnlyAnalysisResult(BaseModel):
    """Vision extractor output for API/DB (no committee/orchestrator)."""

    model: str
    extraction_result: VisionExtractionPayload
    module_name: str = "module_1_vision_extractor"


class VisionOnlyAnalysisService:
    def __init__(self, vision_extractor_service: VisionExtractorService | None = None):
        self._vision = vision_extractor_service or VisionExtractorService()

    async def analyze_image(
        self,
        image_path: str,
        model_name: str | None = None,
    ) -> VisionOnlyAnalysisResult:
        selected_model = normalize_analysis_model_name(model_name)

        def _run_extract() -> VisionOnlyAnalysisResult:
            extraction = self._vision.extract(image_path=image_path, model_name=model_name)
            return VisionOnlyAnalysisResult(
                model=extraction.model,
                extraction_result=extraction.extraction_payload,
            )

        try:
            return await asyncio.to_thread(_run_extract)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Vision analysis failed: %s", exc)
            raise AIProcessingError(f"Vision analysis failed: {exc}") from exc

    @staticmethod
    def serialize_for_storage(result: VisionOnlyAnalysisResult) -> str:
        return json.dumps(
            result.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            separators=(",", ":"),
        )


vision_only_analysis_service = VisionOnlyAnalysisService()
