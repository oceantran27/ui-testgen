from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError

from app.api.v1.endpoints.json_utils import extract_and_minify_json
from app.core.exceptions import AIProcessingError
from app.schemas.pipeline import (
    BusinessAnalystOutput,
    RawScenarioList,
    VisualParserOutput,
)
from app.services.llm_provider import LLMProvider
from app.services.prompt_service import (
    load_business_analyst_prompt,
    load_qa_generator_prompt,
    load_verifier_prompt,
    load_visual_parser_prompt,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minified_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_text_preview(value: str, limit: int = 240) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _format_validation_errors(exc: ValidationError, max_items: int = 3) -> str:
    parts: list[str] = []
    for error in exc.errors()[:max_items]:
        loc = ".".join(str(item) for item in error.get("loc", [])) or "root"
        msg = str(error.get("msg", "validation error"))
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts) if parts else str(exc)


def _parse_json_or_raise(raw_text: str, *, stage_name: str) -> Any:
    # The model sometimes returns JSON in fences or with surrounding text; we extract+minify first.
    minified = extract_and_minify_json(raw_text)
    if not minified:
        preview = _safe_text_preview(raw_text)
        raise AIProcessingError(f"Stage {stage_name} output did not contain valid JSON. Preview: {preview}")
    try:
        return json.loads(minified)
    except Exception as exc:
        raise AIProcessingError(f"Stage {stage_name} returned malformed JSON after extraction") from exc


class MultiAgentPipelineService:
    def __init__(self, *, provider: LLMProvider):
        self.provider = provider

        self.visual_parser_prompt = load_visual_parser_prompt()
        self.business_analyst_prompt = load_business_analyst_prompt()
        self.qa_generator_prompt = load_qa_generator_prompt()
        self.verifier_prompt = load_verifier_prompt()

    @staticmethod
    def _normalize_visual_element(element: dict[str, Any], *, fallback_id: str) -> dict[str, Any]:
        normalized = dict(element)

        element_id = str(normalized.get("id") or "").strip()
        normalized["id"] = element_id or fallback_id

        raw_state = normalized.get("state", [])
        if isinstance(raw_state, str):
            state_values = [raw_state.strip()] if raw_state.strip() else []
        elif isinstance(raw_state, list):
            state_values = [str(item).strip() for item in raw_state if str(item).strip()]
        else:
            state_values = []
        normalized["state"] = state_values

        raw_children = normalized.get("children", [])
        normalized["children"] = raw_children if isinstance(raw_children, list) else []

        for key in ("type", "label", "text", "placeholder", "input_value"):
            if key in normalized and normalized[key] is not None:
                normalized[key] = str(normalized[key]).strip()

        return normalized

    def _normalize_visual_parser_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Normalize loose LLM output into a consistent shape before handing it to Business Analyst.
        normalized_payload = dict(payload)

        groups_raw = payload.get("visual_groups", [])
        if not isinstance(groups_raw, list):
            groups_raw = []

        normalized_groups: list[dict[str, Any]] = []
        element_counter = 1

        for group in groups_raw:
            if not isinstance(group, dict):
                continue

            normalized_group = dict(group)
            group_name = str(normalized_group.get("group_name", "")).strip()
            normalized_group["group_name"] = group_name or f"Group {len(normalized_groups) + 1}"

            elements_raw = normalized_group.get("elements", [])
            if not isinstance(elements_raw, list):
                elements_raw = []

            normalized_elements: list[dict[str, Any]] = []
            for element in elements_raw:
                if not isinstance(element, dict):
                    continue

                fallback_id = f"element_{element_counter:03d}"
                normalized_elements.append(
                    self._normalize_visual_element(element, fallback_id=fallback_id)
                )
                element_counter += 1

            normalized_group["elements"] = normalized_elements
            normalized_groups.append(normalized_group)

        normalized_payload["visual_groups"] = normalized_groups
        return normalized_payload

    def _run_stage(
        self,
        *,
        stage_name: str,
        prompt_text: str,
        temperature: float,
        image_path: str,
        context_text: str | None,
        user_instruction: str,
        schema_model: type[BaseModel],
    ) -> dict[str, Any]:
        started_at = _utc_now_iso()
        t0 = time.time()

        def attempt(temp: float, extra_strict: bool) -> tuple[str, Any, float]:
            strict_suffix = (
                "\n\nSTRICT OUTPUT REQUIREMENT: Output ONLY one valid JSON object. "
                "No markdown. No comments. No extra text."
                if extra_strict
                else ""
            )

            raw = self.provider.generate(
                image_path,
                prompt_text=prompt_text,
                temperature=temp,
                context_text=context_text,
                user_instruction=user_instruction + strict_suffix,
            )

            parsed_obj = _parse_json_or_raise(raw, stage_name=stage_name)

            try:
                validated = schema_model.model_validate(parsed_obj)
            except ValidationError as exc:
                details = _format_validation_errors(exc)
                raise AIProcessingError(
                    f"Stage {stage_name} JSON schema validation failed: {details}"
                ) from exc

            return raw, validated.model_dump(mode="json"), temp

        # One retry per stage: if parsing/validation fails, rerun with strict output requirement and temp=0.
        attempts = 1
        retry_reason: str | None = None
        try:
            raw_text, validated_json, used_temp = attempt(temperature, extra_strict=False)
        except Exception as first_exc:
            logger.warning("Stage %s failed on first attempt: %s", stage_name, first_exc)
            attempts = 2
            retry_reason = str(first_exc)
            try:
                raw_text, validated_json, used_temp = attempt(0.0, extra_strict=True)
            except Exception as second_exc:
                logger.error(
                    "Stage %s failed after retry. First error: %s | Retry error: %s",
                    stage_name,
                    first_exc,
                    second_exc,
                )
                raise AIProcessingError(
                    f"Stage {stage_name} failed after retry. First error: {first_exc}. Retry error: {second_exc}"
                ) from second_exc

        elapsed_ms = int((time.time() - t0) * 1000)
        ended_at = _utc_now_iso()

        return {
            "stage": stage_name,
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "temperature": used_temp,
            "requested_temperature": temperature,
            "attempts": attempts,
            "retry_reason": retry_reason,
            "started_at": started_at,
            "ended_at": ended_at,
            "elapsed_ms": elapsed_ms,
            "raw_text": raw_text,
            "json": validated_json,
        }

    def run(self, image_path: str) -> dict[str, Any]:
        # Keep stage metadata for troubleshooting in logs; response remains business-facing.
        pipeline_meta: dict[str, Any] = {
            "version": "multi-agent-v1",
            "provider": self.provider.provider_name,
            "model": self.provider.model_name,
            "created_at": _utc_now_iso(),
            "stages": {},
        }

        stage1 = self._run_stage(
            stage_name="visual_parser",
            prompt_text=self.visual_parser_prompt,
            temperature=0.1,
            image_path=image_path,
            context_text=None,
            user_instruction="Input: UI screenshot. Produce the Visual Parser JSON.",
            schema_model=VisualParserOutput,
        )

        stage1["json"] = self._normalize_visual_parser_payload(stage1["json"])
        if not stage1["json"].get("visual_groups"):
            logger.warning("Visual parser returned no visual groups for image: %s", image_path)

        pipeline_meta["stages"]["visual_parser"] = stage1

        stage1_json_text = _minified_json_dumps(stage1["json"])

        stage2 = self._run_stage(
            stage_name="business_analyst",
            prompt_text=self.business_analyst_prompt,
            temperature=0.3,
            image_path=image_path,
            context_text=f"Visual Parser output JSON:\n{stage1_json_text}",
            user_instruction="Input: UI screenshot + parsed elements JSON above. Produce the Business Analyst JSON.",
            schema_model=BusinessAnalystOutput,
        )
        pipeline_meta["stages"]["business_analyst"] = stage2

        stage2_json_text = _minified_json_dumps(stage2["json"])

        stage3 = self._run_stage(
            stage_name="qa_generator",
            prompt_text=self.qa_generator_prompt,
            temperature=0.7,
            image_path=image_path,
            context_text=f"Business context JSON:\n{stage2_json_text}",
            user_instruction="Input: UI screenshot + business context JSON above. Produce the QA Generator scenarios JSON.",
            schema_model=RawScenarioList,
        )
        pipeline_meta["stages"]["qa_generator"] = stage3

        stage3_json_text = _minified_json_dumps(stage3["json"])

        stage4 = self._run_stage(
            stage_name="verifier",
            prompt_text=self.verifier_prompt,
            temperature=0.0,
            image_path=image_path,
            # Verifier needs VP elements plus proposed scenarios for element-id cross-checking.
            context_text=(
                f"Visual Parser output JSON:\n{stage1_json_text}\n\n"
                f"Proposed scenarios JSON:\n{stage3_json_text}"
            ),
            user_instruction=(
                "Input: UI screenshot + visual parser JSON + proposed scenarios JSON above. "
                "Return verified scenarios and include verification metadata for each scenario."
            ),
            schema_model=RawScenarioList,
        )
        pipeline_meta["stages"]["verifier"] = stage4

        ba_overview = stage2["json"].get("page_overview", {})
        if not isinstance(ba_overview, dict):
            ba_overview = {}

        business_rules = stage2["json"].get("business_rules", {})
        if not isinstance(business_rules, dict):
            business_rules = {}

        # Keep a deterministic empty structure if Stage 2 data is unexpectedly malformed.
        empty_business_rules = {
            "Field_Level_Rules": [],
            "State_Rules": [],
            "Workflow_Rules": [],
            "Validation_Rules": [],
        }
        normalized_business_rules = {
            key: value if isinstance(value, list) else []
            for key, value in {
                **empty_business_rules,
                **business_rules,
            }.items()
        }

        verified_scenarios = stage4["json"].get("scenarios", [])
        if not isinstance(verified_scenarios, list):
            verified_scenarios = []

        final_output: dict[str, Any] = {
            "page_overview": {
                "page_type": str(ba_overview.get("page_type", "unknown")).strip() or "unknown",
                "primary_goal": str(ba_overview.get("primary_goal", "")).strip(),
                "functionality": str(ba_overview.get("functionality", "")).strip(),
                "target_users": str(ba_overview.get("target_users", "")).strip(),
            },
            "business_rules": normalized_business_rules,
            "scenarios": verified_scenarios,
        }

        logger.info("Pipeline completed: %s", _minified_json_dumps(pipeline_meta))
        return final_output
