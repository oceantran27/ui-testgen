import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AIProcessingError

logger = logging.getLogger(__name__)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=32)
def _read_prompt_file(path_str: str, label: str) -> str:
    try:
        with open(path_str, "r", encoding="utf-8") as prompt_file:
            return prompt_file.read()
    except Exception as exc:
        logger.error("Failed to load %s: %s", label, exc)
        raise AIProcessingError(f"Failed to load {label}: {str(exc)}") from exc


def load_ui_extraction_prompt() -> str:
    root = _backend_root()
    return _read_prompt_file(str(root / settings.UI_EXTRACTION_PROMPT_PATH), "UI extraction prompt")


def load_state_graph_from_intents_prompt() -> str:
    resolved = _backend_root() / settings.STATE_GRAPH_FROM_INTENTS_PROMPT_PATH
    return _read_prompt_file(str(resolved), "state graph from intents prompt")


def load_isolated_scenarios_prompt() -> str:
    resolved = _backend_root() / settings.STATE_GRAPH_ISOLATED_SCENARIOS_PROMPT_PATH
    return _read_prompt_file(str(resolved), "state graph isolated scenarios prompt")


def load_flow_scenarios_prompt() -> str:
    resolved = _backend_root() / settings.STATE_GRAPH_FLOW_SCENARIOS_PROMPT_PATH
    return _read_prompt_file(str(resolved), "state graph flow scenarios prompt")


def load_critic_scenarios_prompt() -> str:
    resolved = _backend_root() / settings.STATE_GRAPH_CRITIC_PROMPT_PATH
    return _read_prompt_file(str(resolved), "state graph critic prompt")
