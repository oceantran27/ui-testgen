import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    backend_root = Path(__file__).resolve().parents[2]
    resolved_path = backend_root / settings.VISION_EXTRACTOR_PROMPT_PATH

    try:
        with open(resolved_path, "r", encoding="utf-8") as prompt_file:
            return prompt_file.read()
    except Exception as exc:
        logger.error("Failed to load system prompt: %s", exc)
        raise AIProcessingError(f"Failed to load system prompt: {str(exc)}")
