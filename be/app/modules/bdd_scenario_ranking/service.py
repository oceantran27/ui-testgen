"""LLM-based ordering of BDD scenarios by business_intent."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from google.genai import types

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.bdd_scenario_ranking.schemas import BddScenarioRankingLLMResponse
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.bdd_happy_path import BddScenarioItem
from app.services.gemini_genai_client import default_generate_config, get_gemini_client
from app.services.prompt_service import load_bdd_scenario_ranking_prompt

logger = logging.getLogger(__name__)

DEFAULT_RANKING_MODEL = "gemini-2.5-flash"


def _resolve_ranking_route(model: str | None) -> tuple[str, Literal["gemini", "openai"]]:
    effective = (model or DEFAULT_RANKING_MODEL).strip().lower()
    if effective.startswith("gpt-"):
        return effective, "openai"
    return effective, "gemini"


def _build_ranking_user_payload(business_intent: str, scenarios: list[BddScenarioItem]) -> str:
    payload = {
        "business_intent": business_intent,
        "scenarios": [{"id": s.id, "title": s.title, "test_scenario": s.test_scenario} for s in scenarios],
    }
    return (
        "Rank these scenarios per the system instructions. Return ONLY the JSON object with "
        '"ordered_scenario_ids". Input JSON:\n'
        + json.dumps(payload, ensure_ascii=False)
    )


def _apply_ordered_ids(scenarios: list[BddScenarioItem], ordered_ids: list[str]) -> list[BddScenarioItem]:
    by_id = {s.id: s for s in scenarios}
    expected = set(by_id.keys())
    out: list[BddScenarioItem] = []
    seen: set[str] = set()
    for sid in ordered_ids:
        if sid in expected and sid not in seen:
            out.append(by_id[sid])
            seen.add(sid)
    if seen != expected:
        return []
    return out


def _parse_ranking_output(raw: str, scenarios: list[BddScenarioItem]) -> list[BddScenarioItem] | None:
    minified = extract_and_minify_json(raw)
    if not minified:
        return None
    try:
        data = json.loads(minified)
    except json.JSONDecodeError:
        return None
    try:
        parsed = BddScenarioRankingLLMResponse.model_validate(data)
    except Exception:
        return None
    ordered = _apply_ordered_ids(scenarios, parsed.ordered_scenario_ids)
    return ordered if ordered else None


def _run_gemini_rank_sync(user_text: str, model_name: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system_prompt = load_bdd_scenario_ranking_prompt()
    client = get_gemini_client()
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[types.Part.from_text(text=user_text)],
            config=default_generate_config(system_instruction=system_prompt),
        )
    except Exception as exc:
        logger.error("Gemini BDD ranking failed: %s", exc)
        raise AIProcessingError(f"BDD scenario ranking failed: {exc}") from exc
    content = response.text
    if not content:
        raise AIProcessingError("Received empty response from Gemini for BDD ranking")
    return content


def _run_openai_rank_sync(user_text: str, model_name: str) -> str:
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    system_prompt = load_bdd_scenario_ranking_prompt()
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
            max_tokens=4096,
            temperature=0,
        )
    except Exception as exc:
        logger.error("OpenAI BDD ranking failed: %s", exc)
        raise AIProcessingError(f"BDD scenario ranking failed: {exc}") from exc
    content = response.choices[0].message.content
    if not content:
        raise AIProcessingError("Received empty response from OpenAI for BDD ranking")
    return content


def rank_scenarios_sync(
    *,
    business_intent: str,
    scenarios: list[BddScenarioItem],
    model: str | None = None,
) -> list[BddScenarioItem]:
    if not scenarios:
        return []
    if len(scenarios) == 1:
        return list(scenarios)
    api_model, route = _resolve_ranking_route(model)
    user_text = _build_ranking_user_payload(business_intent, scenarios)
    if route == "openai":
        raw = _run_openai_rank_sync(user_text, api_model)
    else:
        raw = _run_gemini_rank_sync(user_text, api_model)
    ordered = _parse_ranking_output(raw, scenarios)
    if ordered is None:
        logger.warning("BDD ranking LLM output invalid or incomplete; keeping generation order")
        return list(scenarios)
    return ordered


class BddScenarioRankingService:
    async def rank_scenarios(
        self,
        *,
        business_intent: str,
        scenarios: list[BddScenarioItem],
        model: str | None = None,
    ) -> list[BddScenarioItem]:
        if not scenarios:
            return []
        if len(scenarios) == 1:
            return list(scenarios)

        def _work() -> list[BddScenarioItem]:
            return rank_scenarios_sync(business_intent=business_intent, scenarios=scenarios, model=model)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("BDD scenario ranking service failed: %s", exc)
            raise AIProcessingError(f"BDD scenario ranking service failed: {exc}") from exc


bdd_scenario_ranking_service = BddScenarioRankingService()
