import logging
from functools import lru_cache
from pathlib import Path

from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
# Small allowlist to prevent accidental arbitrary file reads.
_ALLOWED_PROMPTS = {
    "visual_parser_prompt.txt",
    "business_analyst_prompt.txt",
    "qa_generator_prompt.txt",
    "verifier_prompt.txt",
}


def _read_prompt_file(file_name: str) -> str:
    safe_name = (file_name or "").strip()
    if safe_name not in _ALLOWED_PROMPTS:
        raise AIProcessingError(f"Unknown prompt file: {safe_name}")

    prompt_path = _PROMPTS_DIR / safe_name

    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to load prompt %s: %s", safe_name, exc)
        raise AIProcessingError(f"Failed to load prompt: {safe_name}") from exc


@lru_cache(maxsize=32)
def load_prompt(file_name: str) -> str:
    """Load a prompt file from `app/prompts` with caching."""
    return _read_prompt_file(file_name)


def load_visual_parser_prompt() -> str:
    return load_prompt("visual_parser_prompt.txt")


def load_business_analyst_prompt() -> str:
    return load_prompt("business_analyst_prompt.txt")


def load_qa_generator_prompt() -> str:
    return load_prompt("qa_generator_prompt.txt")


def load_verifier_prompt() -> str:
    return load_prompt("verifier_prompt.txt")
