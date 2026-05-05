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


def load_single_stage_test_scenario_prompt() -> str:
    root = _backend_root()
    return _read_prompt_file(
        str(root / settings.SINGLE_STAGE_TEST_SCENARIO_PROMPT_PATH),
        "single-stage test scenario prompt",
    )


def load_two_stage_ui_hierarchy_prompt() -> str:
    root = _backend_root()
    return _read_prompt_file(
        str(root / settings.TWO_STAGE_UI_HIERARCHY_PROMPT_PATH),
        "two-stage UI hierarchy extraction prompt",
    )


def load_two_stage_test_scenario_prompt() -> str:
    root = _backend_root()
    return _read_prompt_file(
        str(root / settings.TWO_STAGE_TEST_SCENARIO_PROMPT_PATH),
        "two-stage test scenario-from-hierarchy prompt",
    )


def load_behavior_flow_cluster_prompt() -> str:
    resolved = _backend_root() / settings.BEHAVIOR_FLOW_CLUSTER_PROMPT_PATH
    return _read_prompt_file(str(resolved), "behavior flow cluster prompt")
