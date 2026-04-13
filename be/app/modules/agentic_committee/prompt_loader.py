import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommitteePromptBundle:
    ba_prompt: str
    qa_prompt: str
    ux_prompt: str
    judge_prompt: str


def _resolve_prompt_path(prompt_path: str) -> Path:
    requested_path = Path(prompt_path)
    if requested_path.is_absolute():
        return requested_path

    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / requested_path


def _read_prompt(prompt_path: str) -> str:
    resolved_path = _resolve_prompt_path(prompt_path)

    try:
        return resolved_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to load committee prompt from %s: %s", resolved_path, exc)
        raise AIProcessingError(f"Failed to load committee prompt: {exc}") from exc


@lru_cache(maxsize=1)
def load_committee_prompts() -> CommitteePromptBundle:
    return CommitteePromptBundle(
        ba_prompt=_read_prompt(settings.COMMITTEE_AGENT_BA_PROMPT_PATH),
        qa_prompt=_read_prompt(settings.COMMITTEE_AGENT_QA_PROMPT_PATH),
        ux_prompt=_read_prompt(settings.COMMITTEE_AGENT_UX_PROMPT_PATH),
        judge_prompt=_read_prompt(settings.COMMITTEE_AGENT_JUDGE_PROMPT_PATH),
    )
