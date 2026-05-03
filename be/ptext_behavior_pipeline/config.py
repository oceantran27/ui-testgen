"""Static configuration for the standalone P-TEXT pipeline."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"

STAGE_B_PROMPT = PROMPTS_DIR / "ui_extraction_ptext_stage1_system_prompt.txt"
STAGE_C_PROMPT = PROMPTS_DIR / "bdd_bundle_ptext_stage2_system_prompt.txt"
STAGE_A_PROMPT = PROMPTS_DIR / "behavior_flow_from_text_bundle_system_prompt.txt"

DEFAULT_MODEL = "gpt-4.1"
