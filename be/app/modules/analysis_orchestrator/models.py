from pydantic import BaseModel

from app.modules.evaluator_rationalizer.models import EvaluationMetadata
from app.modules.vision_extractor.models import VisionExtractionPayload


class AnalyzeOrchestratorResponse(BaseModel):
    module_chain: list[str]
    model: str
    extraction_result: VisionExtractionPayload
    evaluation_result: EvaluationMetadata | None = None
