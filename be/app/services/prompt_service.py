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


def load_system_prompt() -> str:
    resolved = _backend_root() / settings.VISION_EXTRACTOR_PROMPT_PATH
    return _read_prompt_file(str(resolved), "system prompt")


def load_bdd_happy_path_prompt() -> str:
    root = _backend_root()
    return _read_prompt_file(str(root / settings.BDD_HAPPY_PATH_PROMPT_PATH), "BDD happy path prompt")


def load_bdd_scenario_ranking_prompt() -> str:
    resolved = _backend_root() / settings.BDD_SCENARIO_RANKING_PROMPT_PATH
    return _read_prompt_file(str(resolved), "BDD scenario ranking prompt")


def load_behavior_flow_cluster_prompt() -> str:
    resolved = _backend_root() / settings.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH
    return _read_prompt_file(str(resolved), "behavior flow cluster prompt")
