"""OpenAI text-only judge: maps generated intents to ground-truth intents."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError

from experiments.intent_coverage_judge.schemas import (
    EvaluationResult,
    GeneratedIntent,
    GroundTruthIntent,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "judge_system_prompt.txt"


def load_judge_system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise AIProcessingError(f"Failed to load judge prompt: {exc}") from exc


def evaluate_single_screen_sync(
    image_id: str,
    ground_truth_intents: list[GroundTruthIntent],
    generated_intents: list[GeneratedIntent],
    *,
    model: str,
    client: OpenAI | None = None,
) -> tuple[EvaluationResult, float]:
    """
    Call OpenAI judge; return (parsed EvaluationResult, elapsed seconds).
    """
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")
    oclient = client or OpenAI(api_key=settings.OPENAI_API_KEY)
    system_prompt = load_judge_system_prompt()
    gt_payload = [x.model_dump(mode="json") for x in ground_truth_intents]
    gen_payload = [x.model_dump(mode="json") for x in generated_intents]
    user_text = (
        f"Data for Image ID: {image_id}\n\n"
        "=== GROUND TRUTH INTENTS ===\n"
        f"{json.dumps(gt_payload, ensure_ascii=False, indent=2)}\n\n"
        "=== GENERATED INTENTS ===\n"
        f"{json.dumps(gen_payload, ensure_ascii=False, indent=2)}\n\n"
        "Analyze the intents and return a single JSON object per the system instructions."
    )
    t0 = time.perf_counter()
    try:
        response = oclient.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI intent judge failed for %s: %s", image_id, exc)
        raise AIProcessingError(f"Intent judge failed: {exc}") from exc
    content = response.choices[0].message.content
    if not content:
        raise AIProcessingError("Received empty response from OpenAI (intent judge)")
    elapsed = time.perf_counter() - t0
    try:
        parsed = EvaluationResult.model_validate_json(content)
    except Exception as exc:
        raise AIProcessingError(f"Invalid judge JSON: {exc}") from exc
    return parsed, elapsed
