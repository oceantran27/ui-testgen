from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import settings
from app.core.exceptions import AIProcessingError


class LLMProvider(ABC):
    provider_name: str
    model_name: str

    @abstractmethod
    def generate(
        self,
        image_path: str,
        *,
        prompt_text: str,
        temperature: float,
        context_text: str | None = None,
        user_instruction: str | None = None,
    ) -> str:
        raise NotImplementedError


class LLMProviderFactory:
    @staticmethod
    def create_from_settings() -> LLMProvider:
        provider = settings.LLM_PROVIDER
        model_name = settings.LLM_MODEL
        return LLMProviderFactory.create(provider_name=provider, model_name=model_name)

    @staticmethod
    def create(*, provider_name: str, model_name: str) -> LLMProvider:
        normalized_provider = (provider_name or "").strip().lower()
        normalized_model = (model_name or "").strip()

        if normalized_provider != "gemini":
            raise AIProcessingError(f"Unsupported provider: {provider_name}")

        if normalized_model not in {"gemini-2.5-flash", "gemini-1.5-flash"}:
            raise AIProcessingError(f"Unsupported Gemini model: {model_name}")

        from app.services.gemini_service import GeminiService

        return GeminiService(model_name=normalized_model)