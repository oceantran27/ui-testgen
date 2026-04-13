from app.core.model_selection import normalize_analysis_model_name, resolve_gemini_model_name
from app.modules.vision_extractor.providers.base_provider import BaseVisionProvider
from app.modules.vision_extractor.providers.gemini_provider import GeminiVisionProvider
from app.modules.vision_extractor.providers.openai_provider import OpenAIVisionProvider


class VisionProviderFactory:
    def create_provider(self, model_name: str, system_prompt: str) -> BaseVisionProvider:
        selected_model = normalize_analysis_model_name(model_name)

        if selected_model == "openai":
            return OpenAIVisionProvider(system_prompt=system_prompt)
        if selected_model in {"gemini", "gemini-2.5-flash", "gemini-1.5-flash"}:
            actual_model = resolve_gemini_model_name(selected_model)
            return GeminiVisionProvider(system_prompt=system_prompt, model_name=actual_model)

        return GeminiVisionProvider(system_prompt=system_prompt, model_name="gemini-2.5-flash")
