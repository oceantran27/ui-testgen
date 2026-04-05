import logging
from functools import lru_cache

from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    try:
        prompt_path = "app/prompts/system_prompt.txt"
        with open(prompt_path, "r", encoding="utf-8") as prompt_file:
            return prompt_file.read()
    except Exception as exc:
        logger.error("Failed to load system prompt: %s", exc)
        raise AIProcessingError(f"Failed to load system prompt: {str(exc)}")
