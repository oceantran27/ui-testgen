import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


def _resolve_prompt_path(prompt_path: str) -> Path:
    requested_path = Path(prompt_path)
    if requested_path.is_absolute():
        return requested_path

    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / requested_path


@lru_cache(maxsize=1)
def load_vision_extractor_prompt() -> str:
    resolved_path = _resolve_prompt_path(settings.VISION_EXTRACTOR_PROMPT_PATH)

    try:
        return resolved_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to load vision extractor prompt from %s: %s", resolved_path, exc)
        raise AIProcessingError(f"Failed to load vision extractor prompt: {exc}") from exc
