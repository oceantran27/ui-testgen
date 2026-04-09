from app.modules.analysis_orchestrator.models import AnalyzeOrchestratorResponse
from app.core.exceptions import AIProcessingError
from app.modules.evaluator_rationalizer.service import EvaluatorRationalizerService
from app.modules.vision_extractor.service import VisionExtractorService


class AnalysisOrchestrator:
    def __init__(
        self,
        vision_extractor_service: VisionExtractorService | None = None,
        evaluator_rationalizer_service: EvaluatorRationalizerService | None = None,
    ):
        self.vision_extractor_service = vision_extractor_service or VisionExtractorService()
        self.evaluator_rationalizer_service = evaluator_rationalizer_service or EvaluatorRationalizerService()

    def analyze_image(
        self,
        image_path: str,
        model_name: str | None = None,
        include_evaluation: bool = True,
    ) -> AnalyzeOrchestratorResponse:
        extraction_result = self.vision_extractor_service.extract(image_path=image_path, model_name=model_name)

        evaluation_result = None
        module_chain = ["module_1_vision_extractor"]

        if include_evaluation:
            evaluation_result = self.evaluator_rationalizer_service.evaluate(
                extraction_payload=extraction_result.extraction_payload,
                model_name=model_name,
            )

            evaluation_by_id = {
                item.id: item.evaluation
                for item in evaluation_result.scenario_evaluations
            }

            for scenario in extraction_result.extraction_payload.scenarios:
                scenario_evaluation = evaluation_by_id.get(scenario.id)
                if scenario_evaluation is None:
                    raise AIProcessingError(
                        f"Missing evaluator output for scenario id '{scenario.id}'"
                    )
                scenario.evaluation = scenario_evaluation

            module_chain.append("module_2_evaluator_rationalizer")

        return AnalyzeOrchestratorResponse(
            module_chain=module_chain,
            model=extraction_result.model,
            extraction_result=extraction_result.extraction_payload,
            evaluation_result=evaluation_result.metadata if evaluation_result else None,
        )


analysis_orchestrator = AnalysisOrchestrator()
