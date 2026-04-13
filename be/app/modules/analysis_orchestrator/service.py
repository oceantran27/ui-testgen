import asyncio
import json
import logging
from time import perf_counter

from app.core.log_context import merge_with_log_context
from app.core.model_selection import normalize_analysis_model_name
from app.modules.analysis_orchestrator.models import AnalyzeOrchestratorResponse
from app.core.config import settings
from app.modules.agentic_committee.service import AgenticCommitteeService
from app.modules.committee_ranker.models import CommitteeScenarioInput
from app.modules.committee_ranker.service import CommitteeRankerService
from app.modules.vision_extractor.service import VisionExtractorService

logger = logging.getLogger(__name__)


def _json_compact(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class AnalysisOrchestrator:
    def __init__(
        self,
        vision_extractor_service: VisionExtractorService | None = None,
        agentic_committee_service: AgenticCommitteeService | None = None,
        committee_ranker_service: CommitteeRankerService | None = None,
    ):
        self.vision_extractor_service = vision_extractor_service or VisionExtractorService()
        self.agentic_committee_service = agentic_committee_service or AgenticCommitteeService()
        self.committee_ranker_service = committee_ranker_service or CommitteeRankerService()

    async def analyze_image(
        self,
        image_path: str,
        model_name: str | None = None,
    ) -> AnalyzeOrchestratorResponse:
        selected_model = normalize_analysis_model_name(model_name)
        orchestrator_started_at = perf_counter()
        self._log_orchestrator_event(
            "analysis_started",
            image_path=image_path,
            model_name=selected_model,
        )

        module_1_started_at = perf_counter()
        extraction_result = self.vision_extractor_service.extract(image_path=image_path, model_name=model_name)
        module_1_output = extraction_result.extraction_payload.model_dump(mode="json", exclude_none=True)
        logger.debug(
            "Module 1 response: %s",
            json.dumps(module_1_output, ensure_ascii=False, separators=(",", ":")),
        )

        scenarios = extraction_result.extraction_payload.scenarios
        self._log_orchestrator_event(
            "module_1_completed",
            model=extraction_result.model,
            scenario_count=len(scenarios),
            duration_ms=round((perf_counter() - module_1_started_at) * 1000, 2),
        )

        module_2_started_at = perf_counter()
        max_concurrency = max(1, settings.COMMITTEE_MAX_CONCURRENCY)
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _evaluate_single_scenario(scenario):
            async with semaphore:
                return await self.agentic_committee_service.evaluate_scenario_with_debate(
                    page_overview=extraction_result.extraction_payload.page_overview,
                    scenario=scenario,
                    model_name=model_name,
                )

        committee_outputs = (
            await asyncio.gather(*[_evaluate_single_scenario(scenario) for scenario in scenarios])
            if scenarios
            else []
        )

        module_2_output = [
            {
                "scenario_id": scenario.id,
                "user_goal": scenario.user_goal,
                **committee_output.model_dump(mode="json", exclude_none=True),
            }
            for scenario, committee_output in zip(scenarios, committee_outputs)
        ]
        logger.debug(
            "Module 2 response: %s",
            json.dumps(module_2_output, ensure_ascii=False, separators=(",", ":")),
        )
        self._log_orchestrator_event(
            "module_2_completed",
            scenario_count=len(module_2_output),
            duration_ms=round((perf_counter() - module_2_started_at) * 1000, 2),
            max_concurrency=max_concurrency,
        )

        module_4_started_at = perf_counter()
        ranker_inputs = [
            CommitteeScenarioInput(
                scenario_id=scenario.id,
                user_goal=scenario.user_goal,
                BA_score=committee_output.BA_score,
                QA_score=committee_output.QA_score,
                UX_score=committee_output.UX_score,
                conflict_resolution_summary=committee_output.conflict_resolution_summary,
            )
            for scenario, committee_output in zip(scenarios, committee_outputs)
        ]
        ranker_result = self.committee_ranker_service.rank(ranker_inputs)

        logger.debug(
            "Module 4 response: %s",
            json.dumps(
                ranker_result.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        self._log_orchestrator_event(
            "module_4_completed",
            ranked_count=len(ranker_result.ranked_scenarios),
            duration_ms=round((perf_counter() - module_4_started_at) * 1000, 2),
        )

        self._log_orchestrator_event(
            "analysis_completed",
            total_duration_ms=round((perf_counter() - orchestrator_started_at) * 1000, 2),
            scenario_count=len(ranker_result.ranked_scenarios),
            model=extraction_result.model,
        )

        return AnalyzeOrchestratorResponse(
            module_chain=[
                "module_1_vision_extractor",
                "module_2_agentic_committee",
                "module_3_memory_state_manager",
                "module_4_committee_ranker",
            ],
            model=extraction_result.model,
            extraction_result=extraction_result.extraction_payload,
            ranker_metadata=ranker_result.metadata,
            ranked_scenarios=ranker_result.ranked_scenarios,
        )

    def _log_orchestrator_event(self, event_type: str, **payload):
        logger.info(
            "Analysis orchestrator event: %s",
            _json_compact(
                merge_with_log_context(
                    {
                        "service": "analysis_orchestrator",
                        "event_type": event_type,
                        **payload,
                    }
                )
            ),
        )


analysis_orchestrator = AnalysisOrchestrator()
