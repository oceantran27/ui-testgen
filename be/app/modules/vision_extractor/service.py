import json
import logging

from app.core.model_selection import normalize_analysis_model_name
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.modules.vision_extractor.models import VisionExtractionPayload, VisionExtractionResult
from app.modules.vision_extractor.prompt_loader import load_vision_extractor_prompt
from app.modules.vision_extractor.providers.factory import VisionProviderFactory

logger = logging.getLogger(__name__)


class VisionExtractorService:
    def __init__(self, provider_factory: VisionProviderFactory | None = None):
        self.provider_factory = provider_factory or VisionProviderFactory()

    def extract(
        self,
        image_path: str,
        model_name: str | None = None,
    ) -> VisionExtractionResult:
        selected_model = normalize_analysis_model_name(model_name)
        system_prompt = load_vision_extractor_prompt()

        provider = self.provider_factory.create_provider(selected_model, system_prompt)
        raw_output = provider.analyze_image(image_path)

        normalized_output = extract_and_minify_json(raw_output)
        if not normalized_output:
            raise AIProcessingError("Vision extractor returned invalid JSON output")

        try:
            payload = VisionExtractionPayload.model_validate(json.loads(normalized_output))
        except Exception as exc:
            logger.error("Vision extractor output schema mismatch: %s", exc)
            raise AIProcessingError(f"Vision extractor output schema mismatch: {exc}") from exc

        return VisionExtractionResult(
            model=selected_model,
            raw_output=raw_output,
            normalized_output=normalized_output,
            extraction_payload=payload,
        )
