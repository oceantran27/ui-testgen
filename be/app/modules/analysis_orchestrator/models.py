from pydantic import BaseModel, Field

from app.modules.committee_ranker.models import CommitteeRankerMetadata, RankedCommitteeScenarioOutput
from app.modules.vision_extractor.models import VisionExtractionPayload


class AnalyzeOrchestratorResponse(BaseModel):
    module_chain: list[str]
    model: str
    extraction_result: VisionExtractionPayload
    ranker_metadata: CommitteeRankerMetadata | None = None
    ranked_scenarios: list[RankedCommitteeScenarioOutput] = Field(default_factory=list)
