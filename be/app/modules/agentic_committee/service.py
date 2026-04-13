import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.core.log_context import merge_with_log_context
from app.core.model_selection import normalize_analysis_model_name
from app.modules.agentic_committee.graph import CommitteeGraphState, build_committee_graph
from app.modules.agentic_committee.llm_client import (
    CommitteeLLMClient,
    CommitteeRateLimitError,
    CommitteeTimeoutError,
)
from app.modules.agentic_committee.models import (
    AgentOpinion,
    CommitteeState,
    FinalCommitteePayload,
    JudgeRoundOutput,
)
from app.modules.agentic_committee.prompt_loader import CommitteePromptBundle, load_committee_prompts
from app.modules.agentic_committee.state_manager import CommitteeStateManager
from app.modules.vision_extractor.models import PageOverview, ScenarioSpec

logger = logging.getLogger(__name__)


class AgenticCommitteeService:
    def __init__(
        self,
        llm_client: CommitteeLLMClient | None = None,
        state_manager: CommitteeStateManager | None = None,
        prompts: CommitteePromptBundle | None = None,
    ):
        self._llm_client = llm_client or CommitteeLLMClient()
        self._state_manager = state_manager or CommitteeStateManager()
        self._prompts = prompts or load_committee_prompts()
        self._graph = build_committee_graph(
            blind_initial_generation=self._blind_initial_generation,
            judge_round=self._judge_round,
            debate_round=self._debate_round,
            finalize=self._finalize,
            route_after_judge=self._route_after_judge,
        )

    async def evaluate_scenario_with_debate(
        self,
        *,
        page_overview: PageOverview,
        scenario: ScenarioSpec,
        model_name: str | None = None,
    ) -> FinalCommitteePayload:
        selected_model = normalize_analysis_model_name(model_name)
        self._log_debate_event(
            "scenario_start",
            scenario_id=scenario.id,
            user_goal=self._truncate_text(scenario.user_goal, max_chars=220),
            model_name=selected_model,
            max_failsafe_rounds=settings.COMMITTEE_MAX_FAILSAFE_ROUNDS,
            timeout_seconds=settings.COMMITTEE_LLM_TIMEOUT_SECONDS,
            score_delta_threshold=settings.COMMITTEE_SCORE_DELTA_THRESHOLD,
        )

        initial_state = self._build_initial_state(
            page_overview=page_overview,
            scenario=scenario,
            model_name=selected_model,
        )

        await self._state_manager.save_state(CommitteeState.model_validate(initial_state))

        try:
            final_state = await self._graph.ainvoke(initial_state)
            final_payload = final_state.get("final_payload")

            if not final_payload:
                latest_state = await self._state_manager.get_state(scenario.id)
                if latest_state:
                    self._log_debate_event(
                        "fallback_missing_final_payload",
                        level=logging.WARNING,
                        scenario_id=scenario.id,
                        latest_round=max(latest_state.opinions_history.keys(), default=0),
                        reason="Missing final payload from judge",
                    )
                    return self._build_fallback_payload(
                        latest_state,
                        reason="Missing final payload from judge",
                    )
                raise AIProcessingError("Committee debate finished without a final payload")

            validated_payload = FinalCommitteePayload.model_validate(final_payload)
            self._log_debate_event(
                "scenario_completed",
                scenario_id=scenario.id,
                final_round=int(final_state.get("current_round", 0)),
                is_converged=bool(final_state.get("is_converged", False)),
                convergence_reason=self._truncate_text(
                    final_state.get("convergence_reason", ""),
                    max_chars=280,
                ),
                final_payload=validated_payload.model_dump(mode="json"),
            )
            return validated_payload
        except (CommitteeTimeoutError, CommitteeRateLimitError) as exc:
            self._log_debate_event(
                "scenario_interrupted",
                level=logging.WARNING,
                scenario_id=scenario.id,
                error_type=exc.__class__.__name__,
                reason=str(exc),
            )
            latest_state = await self._state_manager.get_state(scenario.id)
            if latest_state:
                self._log_debate_event(
                    "fallback_latest_successful_round",
                    level=logging.WARNING,
                    scenario_id=scenario.id,
                    latest_round=max(latest_state.opinions_history.keys(), default=0),
                    convergence_reason=self._truncate_text(
                        latest_state.convergence_reason,
                        max_chars=220,
                    ),
                )
                return self._build_fallback_payload(latest_state, reason=str(exc))
            raise AIProcessingError(
                f"Committee debate interrupted before first successful round: {exc}"
            ) from exc
        except AIProcessingError:
            raise
        except Exception as exc:
            self._log_debate_event(
                "scenario_unexpected_error",
                level=logging.ERROR,
                scenario_id=scenario.id,
                error_type=exc.__class__.__name__,
                reason=str(exc),
            )
            raise AIProcessingError(f"Agentic committee debate failed: {exc}") from exc
        finally:
            await self._state_manager.clear_state(scenario.id)
            self._log_debate_event("scenario_state_cleared", scenario_id=scenario.id)

    def _build_initial_state(
        self,
        *,
        page_overview: PageOverview,
        scenario: ScenarioSpec,
        model_name: str | None,
    ) -> CommitteeGraphState:
        selected_model = normalize_analysis_model_name(model_name)
        return {
            "scenario_id": scenario.id,
            "user_goal": scenario.user_goal,
            "page_overview": page_overview.model_dump(mode="json"),
            "scenario": scenario.model_dump(mode="json", exclude={"evaluation"}),
            "model_name": selected_model,
            "current_round": 0,
            "opinions_history": {},
            "compressed_context": "",
            "targeted_critiques": {
                "ba": "",
                "qa": "",
                "ux": "",
            },
            "is_converged": False,
            "convergence_reason": "",
            "final_payload": None,
        }

    async def _blind_initial_generation(self, state: CommitteeGraphState) -> dict[str, Any]:
        scenario_id = str(state.get("scenario_id", ""))
        self._log_debate_event(
            "round_start",
            scenario_id=scenario_id,
            current_round=1,
            mode="blind_initial_generation",
        )

        opinions = await self._evaluate_specialists(
            state=state,
            current_round=1,
            targeted_critiques={
                "ba": "",
                "qa": "",
                "ux": "",
            },
        )

        opinions_history = dict(state.get("opinions_history", {}))
        opinions_history[1] = opinions

        updates = {
            "current_round": 1,
            "opinions_history": opinions_history,
        }
        await self._persist_state(state, updates)
        self._log_debate_event(
            "round_completed",
            scenario_id=scenario_id,
            current_round=1,
            opinions=self._summarize_opinions(opinions),
        )
        return updates

    async def _judge_round(self, state: CommitteeGraphState) -> dict[str, Any]:
        current_round = int(state.get("current_round", 0))
        opinions_history = state.get("opinions_history", {})
        latest_opinions = opinions_history.get(current_round, {})
        scenario_id = str(state.get("scenario_id", ""))

        self._log_debate_event(
            "judge_round_start",
            scenario_id=scenario_id,
            current_round=current_round,
            latest_opinions=self._summarize_opinions(latest_opinions),
            compressed_context=self._truncate_text(state.get("compressed_context", ""), max_chars=260),
        )

        judge_payload = {
            "task": "round_check",
            "scenario_id": state.get("scenario_id"),
            "current_round": current_round,
            "max_failsafe_rounds": settings.COMMITTEE_MAX_FAILSAFE_ROUNDS,
            "score_delta_threshold": settings.COMMITTEE_SCORE_DELTA_THRESHOLD,
            "page_overview": state.get("page_overview", {}),
            "scenario": state.get("scenario", {}),
            "latest_opinions": latest_opinions,
            "compressed_context": state.get("compressed_context", ""),
            "output_schema": {
                "is_converged": "boolean",
                "convergence_reason": "string",
                "compressed_context": "string",
                "targeted_critiques": {
                    "ba": "string",
                    "qa": "string",
                    "ux": "string",
                },
            },
        }

        raw_result = await self._llm_client.invoke_json(
            model_name=str(state.get("model_name", "gemini-2.5-flash")),
            system_prompt=self._prompts.judge_prompt,
            user_payload=judge_payload,
        )
        judge_output = self._parse_judge_round_output(raw_result)
        self._log_debate_event(
            "judge_round_result",
            scenario_id=scenario_id,
            current_round=current_round,
            is_converged=judge_output.is_converged,
            convergence_reason=self._truncate_text(judge_output.convergence_reason, max_chars=260),
            compressed_context=self._truncate_text(judge_output.compressed_context, max_chars=260),
            targeted_critiques=self._summarize_targeted_critiques(
                judge_output.targeted_critiques.model_dump(mode="json")
            ),
        )

        updates = {
            "is_converged": judge_output.is_converged,
            "convergence_reason": judge_output.convergence_reason,
            "compressed_context": judge_output.compressed_context,
            "targeted_critiques": judge_output.targeted_critiques.model_dump(mode="json"),
        }
        await self._persist_state(state, updates)
        return updates

    async def _debate_round(self, state: CommitteeGraphState) -> dict[str, Any]:
        next_round = int(state.get("current_round", 0)) + 1
        targeted_critiques = state.get("targeted_critiques", {})
        scenario_id = str(state.get("scenario_id", ""))

        self._log_debate_event(
            "round_start",
            scenario_id=scenario_id,
            current_round=next_round,
            mode="debate_round",
            targeted_critiques=self._summarize_targeted_critiques(targeted_critiques),
        )

        opinions = await self._evaluate_specialists(
            state=state,
            current_round=next_round,
            targeted_critiques={
                "ba": str(targeted_critiques.get("ba", "")),
                "qa": str(targeted_critiques.get("qa", "")),
                "ux": str(targeted_critiques.get("ux", "")),
            },
        )

        opinions_history = dict(state.get("opinions_history", {}))
        opinions_history[next_round] = opinions

        updates = {
            "current_round": next_round,
            "opinions_history": opinions_history,
        }
        await self._persist_state(state, updates)
        self._log_debate_event(
            "round_completed",
            scenario_id=scenario_id,
            current_round=next_round,
            opinions=self._summarize_opinions(opinions),
        )
        return updates

    async def _finalize(self, state: CommitteeGraphState) -> dict[str, Any]:
        current_round = int(state.get("current_round", 0))
        opinions_history = state.get("opinions_history", {})
        latest_opinions = opinions_history.get(current_round, {})
        scenario_id = str(state.get("scenario_id", ""))

        self._log_debate_event(
            "finalize_start",
            scenario_id=scenario_id,
            current_round=current_round,
            is_converged=bool(state.get("is_converged", False)),
            convergence_reason=self._truncate_text(state.get("convergence_reason", ""), max_chars=260),
            latest_opinions=self._summarize_opinions(latest_opinions),
        )

        final_payload_request = {
            "task": "final_extraction",
            "scenario_id": state.get("scenario_id"),
            "current_round": current_round,
            "is_converged": bool(state.get("is_converged", False)),
            "convergence_reason": state.get("convergence_reason", ""),
            "page_overview": state.get("page_overview", {}),
            "scenario": state.get("scenario", {}),
            "latest_opinions": latest_opinions,
            "compressed_context": state.get("compressed_context", ""),
            "output_schema": {
                "BA_score": "integer 1..10",
                "QA_score": "integer 1..10",
                "UX_score": "integer 1..10",
                "conflict_resolution_summary": "string",
            },
        }

        raw_result = await self._llm_client.invoke_json(
            model_name=str(state.get("model_name", "gemini-2.5-flash")),
            system_prompt=self._prompts.judge_prompt,
            user_payload=final_payload_request,
        )
        final_payload = self._parse_final_payload(raw_result, latest_opinions=latest_opinions)
        self._log_debate_event(
            "finalize_result",
            scenario_id=scenario_id,
            current_round=current_round,
            final_payload=final_payload.model_dump(mode="json"),
        )

        updates = {
            "final_payload": final_payload.model_dump(mode="json"),
        }
        await self._persist_state(state, updates)
        return updates

    def _route_after_judge(self, state: CommitteeGraphState) -> str:
        current_round = int(state.get("current_round", 0))
        is_converged = bool(state.get("is_converged", False))
        scenario_id = str(state.get("scenario_id", ""))

        route = "finalize" if is_converged or current_round >= settings.COMMITTEE_MAX_FAILSAFE_ROUNDS else "debate_round"
        self._log_debate_event(
            "judge_route_decision",
            scenario_id=scenario_id,
            current_round=current_round,
            is_converged=is_converged,
            max_failsafe_rounds=settings.COMMITTEE_MAX_FAILSAFE_ROUNDS,
            route=route,
            convergence_reason=self._truncate_text(state.get("convergence_reason", ""), max_chars=220),
        )
        return route

    async def _evaluate_specialists(
        self,
        *,
        state: CommitteeGraphState,
        current_round: int,
        targeted_critiques: dict[str, str],
    ) -> dict[str, dict[str, Any]]:
        scenario_id = str(state.get("scenario_id", ""))
        self._log_debate_event(
            "specialist_batch_start",
            scenario_id=scenario_id,
            current_round=current_round,
            targeted_critiques=self._summarize_targeted_critiques(targeted_critiques),
        )

        ba_task = self._invoke_specialist(
            role_key="ba",
            criterion="business_value",
            system_prompt=self._prompts.ba_prompt,
            state=state,
            current_round=current_round,
            targeted_critique=targeted_critiques.get("ba", ""),
        )
        qa_task = self._invoke_specialist(
            role_key="qa",
            criterion="security_risk",
            system_prompt=self._prompts.qa_prompt,
            state=state,
            current_round=current_round,
            targeted_critique=targeted_critiques.get("qa", ""),
        )
        ux_task = self._invoke_specialist(
            role_key="ux",
            criterion="ux_accessibility",
            system_prompt=self._prompts.ux_prompt,
            state=state,
            current_round=current_round,
            targeted_critique=targeted_critiques.get("ux", ""),
        )

        ba_opinion, qa_opinion, ux_opinion = await asyncio.gather(ba_task, qa_task, ux_task)

        result = {
            "ba": ba_opinion.model_dump(mode="json"),
            "qa": qa_opinion.model_dump(mode="json"),
            "ux": ux_opinion.model_dump(mode="json"),
        }
        self._log_debate_event(
            "specialist_batch_result",
            scenario_id=scenario_id,
            current_round=current_round,
            opinions=self._summarize_opinions(result),
        )
        return result

    async def _invoke_specialist(
        self,
        *,
        role_key: str,
        criterion: str,
        system_prompt: str,
        state: CommitteeGraphState,
        current_round: int,
        targeted_critique: str,
    ) -> AgentOpinion:
        user_payload = {
            "task": "blind_initial_generation" if current_round == 1 else "debate_round",
            "agent_role": role_key,
            "criterion": criterion,
            "current_round": current_round,
            "page_overview": state.get("page_overview", {}),
            "scenario": state.get("scenario", {}),
            "compressed_context": state.get("compressed_context", ""),
            "targeted_critique": targeted_critique,
            "output_schema": {
                "score": "integer 1..10",
                "rationale": "string",
            },
        }

        self._log_debate_event(
            "specialist_request",
            scenario_id=str(state.get("scenario_id", "")),
            current_round=current_round,
            role=role_key,
            criterion=criterion,
            targeted_critique=self._truncate_text(targeted_critique, max_chars=220),
            compressed_context=self._truncate_text(state.get("compressed_context", ""), max_chars=260),
        )

        raw_result = await self._llm_client.invoke_json(
            model_name=str(state.get("model_name", "gemini-2.5-flash")),
            system_prompt=system_prompt,
            user_payload=user_payload,
        )
        opinion = self._parse_agent_opinion(raw_result)
        self._log_debate_event(
            "specialist_response",
            scenario_id=str(state.get("scenario_id", "")),
            current_round=current_round,
            role=role_key,
            score=opinion.score,
            rationale=self._truncate_text(opinion.rationale, max_chars=320),
        )
        return opinion

    def _parse_agent_opinion(self, payload: dict[str, Any]) -> AgentOpinion:
        raw_score = payload.get("score")
        score = self._coerce_score(raw_score, default=5)

        rationale = str(payload.get("rationale", "")).strip()
        if not rationale:
            rationale = "No rationale provided by specialist."

        return AgentOpinion(score=score, rationale=rationale)

    def _parse_judge_round_output(self, payload: dict[str, Any]) -> JudgeRoundOutput:
        targeted_raw = payload.get("targeted_critiques")
        targeted = targeted_raw if isinstance(targeted_raw, dict) else {}

        normalized = {
            "is_converged": self._to_bool(payload.get("is_converged", False)),
            "convergence_reason": str(payload.get("convergence_reason", "")).strip(),
            "compressed_context": str(payload.get("compressed_context", "")).strip(),
            "targeted_critiques": {
                "ba": str(targeted.get("ba", "")).strip(),
                "qa": str(targeted.get("qa", "")).strip(),
                "ux": str(targeted.get("ux", "")).strip(),
            },
        }
        return JudgeRoundOutput.model_validate(normalized)

    def _parse_final_payload(
        self,
        payload: dict[str, Any],
        *,
        latest_opinions: dict[str, Any],
    ) -> FinalCommitteePayload:
        fallback_ba = self._extract_score_from_opinion(latest_opinions.get("ba"), default=5)
        fallback_qa = self._extract_score_from_opinion(latest_opinions.get("qa"), default=5)
        fallback_ux = self._extract_score_from_opinion(latest_opinions.get("ux"), default=5)

        summary = str(
            payload.get("conflict_resolution_summary")
            or payload.get("summary")
            or ""
        ).strip()
        if not summary:
            summary = "Finalized by judge using latest round evidence."

        normalized = {
            "BA_score": self._coerce_score(payload.get("BA_score", payload.get("ba_score")), default=fallback_ba),
            "QA_score": self._coerce_score(payload.get("QA_score", payload.get("qa_score")), default=fallback_qa),
            "UX_score": self._coerce_score(payload.get("UX_score", payload.get("ux_score")), default=fallback_ux),
            "conflict_resolution_summary": summary,
        }
        return FinalCommitteePayload.model_validate(normalized)

    @staticmethod
    def _extract_score_from_opinion(opinion: Any, *, default: int) -> int:
        if isinstance(opinion, AgentOpinion):
            return opinion.score
        if isinstance(opinion, dict):
            raw = opinion.get("score")
            try:
                score = int(float(raw))
                return max(1, min(10, score))
            except Exception:
                return default
        return default

    @staticmethod
    def _coerce_score(value: Any, *, default: int) -> int:
        try:
            score = int(float(value))
            return max(1, min(10, score))
        except Exception:
            return max(1, min(10, default))

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y"}
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    async def _persist_state(
        self,
        state: CommitteeGraphState,
        updates: dict[str, Any],
    ) -> None:
        merged_state = dict(state)
        merged_state.update(updates)
        await self._state_manager.save_state(CommitteeState.model_validate(merged_state))
        known_rounds = sorted([str(round_id) for round_id in merged_state.get("opinions_history", {}).keys()])
        self._log_debate_event(
            "state_persisted",
            scenario_id=str(merged_state.get("scenario_id", "")),
            current_round=int(merged_state.get("current_round", 0)),
            is_converged=bool(merged_state.get("is_converged", False)),
            has_final_payload=bool(merged_state.get("final_payload")),
            known_rounds=known_rounds,
        )

    def _build_fallback_payload(self, state: CommitteeState, *, reason: str) -> FinalCommitteePayload:
        latest_round = max(state.opinions_history.keys(), default=0)

        if latest_round <= 0:
            self._log_debate_event(
                "fallback_before_first_round",
                level=logging.WARNING,
                scenario_id=state.scenario_id,
                reason=reason,
            )
            return FinalCommitteePayload(
                BA_score=5,
                QA_score=5,
                UX_score=5,
                conflict_resolution_summary=(
                    "Fallback activated before first successful committee round. "
                    f"Reason: {reason}."
                ),
            )

        latest = state.opinions_history.get(latest_round, {})
        ba_score = latest.get("ba").score if latest.get("ba") else 5
        qa_score = latest.get("qa").score if latest.get("qa") else 5
        ux_score = latest.get("ux").score if latest.get("ux") else 5

        self._log_debate_event(
            "fallback_latest_round",
            level=logging.WARNING,
            scenario_id=state.scenario_id,
            latest_round=latest_round,
            ba_score=ba_score,
            qa_score=qa_score,
            ux_score=ux_score,
            reason=reason,
        )

        return FinalCommitteePayload(
            BA_score=ba_score,
            QA_score=qa_score,
            UX_score=ux_score,
            conflict_resolution_summary=(
                f"Fallback to latest successful round {latest_round} due to transient LLM issue: {reason}. "
                "Used latest specialist scores without additional judge extraction."
            ),
        )

    def _log_debate_event(
        self,
        event: str,
        *,
        level: int = logging.INFO,
        **payload: Any,
    ) -> None:
        event_payload = self._build_structured_event(event=event, payload=payload)
        legacy_payload = self._serialize_json(payload)
        structured_payload = self._serialize_json(event_payload)

        if settings.COMMITTEE_LOG_LEGACY_ENABLED:
            logger.log(level, "Committee debate [%s]: %s", event, legacy_payload)
        if settings.COMMITTEE_LOG_STRUCTURED_ENABLED:
            logger.log(level, "Committee debate JSON: %s", structured_payload)

    def _build_structured_event(self, *, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        merged_payload = merge_with_log_context(payload)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "agentic_committee",
            "event_type": event,
            "schema_version": 1,
            **merged_payload,
        }

    @staticmethod
    def _serialize_json(payload: dict[str, Any]) -> str:
        try:
            return json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        except Exception:
            return str(payload)

    def _summarize_opinions(self, opinions: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if not isinstance(opinions, dict):
            opinions = {}

        summary: dict[str, dict[str, Any]] = {}
        for role in ("ba", "qa", "ux"):
            opinion = opinions.get(role)

            if isinstance(opinion, AgentOpinion):
                score = opinion.score
                rationale = opinion.rationale
            elif isinstance(opinion, dict):
                score = self._coerce_score(opinion.get("score"), default=5)
                rationale = str(opinion.get("rationale", ""))
            else:
                score = 5
                rationale = ""

            summary[role] = {
                "score": score,
                "rationale": self._truncate_text(rationale, max_chars=220),
            }

        return summary

    def _summarize_targeted_critiques(self, targeted_critiques: dict[str, Any]) -> dict[str, str]:
        if not isinstance(targeted_critiques, dict):
            targeted_critiques = {}

        return {
            "ba": self._truncate_text(targeted_critiques.get("ba", ""), max_chars=220),
            "qa": self._truncate_text(targeted_critiques.get("qa", ""), max_chars=220),
            "ux": self._truncate_text(targeted_critiques.get("ux", ""), max_chars=220),
        }

    @staticmethod
    def _truncate_text(value: Any, *, max_chars: int | None = None) -> str:
        if max_chars is None or max_chars <= 0:
            max_chars = settings.COMMITTEE_LOG_MAX_TEXT_CHARS

        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars]}...<truncated:{len(text) - max_chars} chars>"


agentic_committee_service = AgenticCommitteeService()
