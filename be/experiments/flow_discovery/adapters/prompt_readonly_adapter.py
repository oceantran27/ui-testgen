"""Read-only access to production prompts for global flow discovery."""

from __future__ import annotations

import json
from typing import Any, Dict

from app.core.prompt_manager import prompt_manager

from experiments.flow_discovery import config


def get_global_flow_discovery_prompt() -> str:
    return prompt_manager.get_prompt(config.PROMPT_NAME).strip()


def build_flow_discovery_user_instruction(llm_catalog: dict[str, Any]) -> str:
    body_json = json.dumps(llm_catalog, ensure_ascii=False)
    return (
        "Compose behavioural flow candidates from the llm_discovery_catalog JSON below "
        "(states only — unordered set). Use state_id / action_id values verbatim from input.\n\n"
        f"{body_json}\n"
    )


def prompt_snapshot(*, preview_chars: int = 200) -> Dict[str, Any]:
    system_instruction = get_global_flow_discovery_prompt()
    preview = system_instruction[: max(0, preview_chars)] if preview_chars else ""
    return {
        "prompt_name": config.PROMPT_NAME,
        "prompt_version": config.PROMPT_VERSION,
        "system_instruction_preview": preview,
        "system_instruction_chars": len(system_instruction),
    }
