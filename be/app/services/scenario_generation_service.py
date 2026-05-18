"""
BDD Scenario Generation Service — Agent 6.
Deterministic and optional LLM-grounded Gherkin scenarios via scenario blueprints + anchor validation.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.schemas import (
    AssertionA6,
    BDDScenarioGenerationResult,
    BehaviourIntentA5,
    CoverageMatrixItemA6,
    GroundingContractA6,
    PreGenerationGroundingA6,
    ScenarioBlueprintBatchInput,
    ScenarioGenerationMetricsA6,
    ScenarioGenerationSummaryA6,
    ScenarioWritingBlueprint,
    TestDataA6,
    TestScenarioA6,
    TestScenarioStepA6,
    UnresolvedScenarioItemA6,
)
from app.services.test_path_utils import map_test_path
from app.services.scenario_blueprint_builder_service import build_scenario_blueprints
from app.services.scenario_keyword_validator import validate_scenario_against_blueprint
from app.services.ui_text_normalize import normalize_ui_text


def _scenario_assumptions_with_seed(intent: BehaviourIntentA5) -> List[str]:
    """Optional fixed context lines (demo copy); prepended once when configured."""
    out = list(intent.assumptions or [])
    block = str(getattr(settings, "SCENARIO_CONTEXT_SEED_BLOCK", "") or "").strip()
    if block and block not in out:
        return [block, *out]
    return out


def _generate_behaviour_scenario_id() -> str:
    """behaviour_scenarios.id is a global PK — never persist LLM ids like scn_001."""
    return f"bs_{uuid.uuid4().hex[:12]}"


def _precheck_behaviour_intent_for_scenarios(intent: BehaviourIntentA5) -> Optional[UnresolvedScenarioItemA6]:
    """Fail fast unresolved items when generation would produce unusable drafts."""
    if not (intent.start_state or "").strip() or not (intent.end_state or "").strip():
        return UnresolvedScenarioItemA6(
            item_type="missing_critical_field",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="Missing start_state or end_state",
        )

    ta = intent.trigger_action
    trigger_fragments = (ta.text or []) if ta else []
    trigger_text_nonempty = any(str(t).strip() for t in trigger_fragments)
    if not ta or not trigger_text_nonempty:
        return UnresolvedScenarioItemA6(
            item_type="missing_critical_field",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="trigger_action missing non-empty text",
        )

    if not (intent.expected_result or "").strip():
        return UnresolvedScenarioItemA6(
            item_type="insufficient_expected_result",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="expected_result missing or whitespace-only",
        )

    ft = intent.source_flow_type or ""
    if ft in ("ordered_sequence", "branching_flow") and not (intent.source_transition_ids or []):
        return UnresolvedScenarioItemA6(
            item_type="insufficient_traceability",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="source_transition_ids required for ordered_sequence / branching_flow",
        )

    if intent.start_state != intent.end_state and not intent.user_actions:
        return UnresolvedScenarioItemA6(
            item_type="invalid_intent",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="Cross-state intent requires user_actions steps",
        )

    itype = (intent.intent_type or "").lower()
    if itype == "positive" and not intent.expected_ui_evidence:
        return UnresolvedScenarioItemA6(
            item_type="insufficient_evidence",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="intent_type positive requires expected_ui_evidence",
        )

    if itype in ("negative", "validation"):
        has_evidence = bool(intent.expected_ui_evidence)
        has_neg = bool(intent.negative_expectations)
        has_result = bool((intent.expected_result or "").strip())
        if not (has_evidence or has_neg or has_result):
            return UnresolvedScenarioItemA6(
                item_type="insufficient_evidence",
                source_intent_id=intent.intent_id,
                source_flow_id=intent.source_flow_id,
                reason=(
                    "intent_type negative or validation requires at least one of "
                    "expected_ui_evidence, negative_expectations, or non-empty expected_result"
                ),
            )

    if settings.SCENARIO_GENERATION_PRODUCTION_GUARDS:
        if intent.flow_validation_status is not None:
            if str(intent.flow_validation_status).lower() != "valid":
                return UnresolvedScenarioItemA6(
                    item_type="invalid_intent",
                    source_intent_id=intent.intent_id,
                    source_flow_id=intent.source_flow_id,
                    reason=f"flow_validation_status is {intent.flow_validation_status!r} (production requires valid)",
                )
        if intent.scenario_worthy_path is False:
            return UnresolvedScenarioItemA6(
                item_type="invalid_intent",
                source_intent_id=intent.intent_id,
                source_flow_id=intent.source_flow_id,
                reason="scenario_worthy_path is false for this behaviour intent",
            )
        thr = int(settings.CANDIDATE_EDGE_SCENARIO_WORTHINESS_MIN_FOR_AGENT4)
        if intent.min_scenario_worthiness is not None and int(intent.min_scenario_worthiness) < thr:
            return UnresolvedScenarioItemA6(
                item_type="invalid_intent",
                source_intent_id=intent.intent_id,
                source_flow_id=intent.source_flow_id,
                reason=f"min_scenario_worthiness {intent.min_scenario_worthiness} below threshold {thr}",
            )

    return None


def build_deterministic_test_scenario_from_intent(intent: BehaviourIntentA5) -> TestScenarioA6:
    """Synthetic BDD shapes from deterministic intent mapping (baseline / fallback)."""
    scenario_id = f"scn_{intent.intent_id[-8:]}"
    scenario_name = intent.behaviour_name.strip().capitalize()

    steps: List[TestScenarioStepA6] = []
    step_counter = 1

    for i, pre in enumerate(intent.preconditions):
        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="Given" if i == 0 else "And",
                text=pre,
                source="precondition",
            )
        )
        step_counter += 1

    if not intent.preconditions:
        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="Given",
                text=f"User is on {intent.start_state}",
                source="precondition",
            )
        )
        step_counter += 1

    test_data_list: List[TestDataA6] = []
    for td in intent.test_data_requirements:
        placeholder = f"<{td.value_type}>"
        test_data_list.append(
            TestDataA6(
                data_name=td.field_or_input,
                value_placeholder=placeholder,
                source_requirement=td.reason,
                required=td.required,
                reason=td.reason,
            )
        )
        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="And",
                text=f"The user has {td.field_or_input} as {placeholder}",
                source="test_data",
            )
        )
        step_counter += 1

    for i, act in enumerate(intent.user_actions):
        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="When" if i == 0 else "And",
                text=act,
                source="user_action",
            )
        )
        step_counter += 1

    steps.append(
        TestScenarioStepA6(
            step_number=step_counter,
            keyword="Then",
            text=intent.expected_result,
            source="expected_result",
        )
    )
    step_counter += 1

    assertions: List[AssertionA6] = [
        AssertionA6(
            assertion_type="state_transition",
            expected=intent.end_state,
            source="expected_result",
            ui_text_grounding_required=False,
        )
    ]

    for ev in intent.expected_ui_evidence:
        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="And",
                text=f"The UI shows: {ev}",
                source="expected_ui_evidence",
            )
        )
        step_counter += 1

        a_type = "ui_evidence_present"
        if "feedback" in ev.lower():
            a_type = "feedback_visible"
        elif "purpose" in ev.lower():
            a_type = "screen_purpose_matched"

        assertions.append(
            AssertionA6(
                assertion_type=a_type,
                expected=ev,
                source="expected_ui_evidence",
            )
        )

    for neg in intent.negative_expectations:
        assertions.append(
            AssertionA6(
                assertion_type=(
                    "feedback_not_visible" if "feedback" in neg.lower() else "state_not_reached"
                ),
                expected=neg,
                source="negative_expectation",
                ui_text_grounding_required=False,
                render_in_gherkin=False,
            )
        )

    return TestScenarioA6(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        scenario_type=map_test_path(intent.intent_type),
        source_intent_id=intent.intent_id,
        source_flow_id=intent.source_flow_id,
        source_flow_name=intent.source_flow_name,
        source_flow_type=intent.source_flow_type,
        source_screen_intent_id=intent.source_screen_intent_id,
        source_group_id=intent.source_group_id,
        source_transition_ids=intent.source_transition_ids,
        source_transition_indexes=intent.source_transition_indexes,
        user_actions=list(intent.user_actions or []),
        start_state=intent.start_state,
        end_state=intent.end_state,
        trigger_action=intent.trigger_action,
        test_objective=f"Verify {intent.user_intent}",
        preconditions=intent.preconditions,
        test_data=test_data_list,
        steps=steps,
        expected_results=[intent.expected_result],
        assertions=assertions,
        assumptions=_scenario_assumptions_with_seed(intent),
        warnings=intent.warnings,
        confidence=intent.confidence,
    )


def _required_anchor_ids_from_blueprint(blueprint: ScenarioWritingBlueprint) -> List[str]:
    ma = blueprint.mandatory_anchors
    out: List[str] = []
    for sec in (ma.given, ma.when, ma.then):
        for a in sec:
            if a.anchor_id:
                out.append(a.anchor_id)
    return out


def _apply_intent_overlay(scn: TestScenarioA6, intent: BehaviourIntentA5) -> None:
    scn.source_intent_id = str(intent.intent_id)
    scn.source_flow_id = str(intent.source_flow_id)
    scn.source_flow_name = str(intent.source_flow_name)
    scn.source_flow_type = str(intent.source_flow_type)
    scn.source_screen_intent_id = intent.source_screen_intent_id
    scn.source_group_id = intent.source_group_id
    scn.source_transition_ids = intent.source_transition_ids
    scn.source_transition_indexes = intent.source_transition_indexes
    scn.start_state = str(intent.start_state)
    scn.end_state = str(intent.end_state)
    scn.scenario_type = map_test_path(intent.intent_type)
    scn.trigger_action = intent.trigger_action
    scn.confidence = intent.confidence
    scn.user_actions = list(intent.user_actions or [])
    scn.assumptions = _scenario_assumptions_with_seed(intent)


def _attach_grounding(
    scn: TestScenarioA6, blueprint: ScenarioWritingBlueprint, grounding_raw: Dict[str, Any]
) -> None:
    req = _required_anchor_ids_from_blueprint(blueprint)
    used = list(grounding_raw.get("matched_anchor_ids") or [])
    fields = set(PreGenerationGroundingA6.model_fields.keys())
    filt = {k: v for k, v in grounding_raw.items() if k in fields}
    filt["matched_anchor_ids"] = used
    scn.pre_generation_grounding = PreGenerationGroundingA6(**filt)
    scn.grounding_contract = GroundingContractA6(required_anchor_ids=req, used_anchor_ids=used)


def _merge_test_data_from_intent(scn: TestScenarioA6, intent: BehaviourIntentA5) -> None:
    if scn.test_data:
        return
    for td in intent.test_data_requirements:
        scn.test_data.append(
            TestDataA6(
                data_name=td.field_or_input,
                value_placeholder=f"<{td.value_type}>",
                source_requirement=td.reason,
                required=td.required,
                reason=td.reason,
            )
        )


def _merge_hidden_assertions_into_scenario(scn: TestScenarioA6, blueprint: ScenarioWritingBlueprint) -> None:
    """Append blueprint internal assertions (not for Gherkin) without duplicating intent-backed rows."""
    existing = {(a.assertion_type, normalize_ui_text(a.expected)) for a in scn.assertions}
    for h in blueprint.hidden_assertions:
        key = (h.assertion_type, normalize_ui_text(h.expected))
        if key in existing:
            continue
        existing.add(key)
        scn.assertions.append(
            AssertionA6(
                assertion_type=h.assertion_type,
                expected=h.expected,
                source="hidden_assertion",
                ui_text_grounding_required=h.ui_text_grounding_required,
                render_in_gherkin=h.render_in_gherkin,
            )
        )


async def _llm_write_from_blueprint(
    run_id: str,
    blueprint: ScenarioWritingBlueprint,
    *,
    repair_context: Optional[Dict[str, Any]] = None,
    prompt_version: str = "v2",
) -> Optional[BDDScenarioGenerationResult]:
    system_instruction = prompt_manager.get_prompt("scenario_generation").strip()
    if repair_context is None:
        batch = ScenarioBlueprintBatchInput(scenario_writing_blueprints=[blueprint])
        user_instruction = (
            "Rewrite each scenario blueprint into one readable BDD scenario. "
            "Preserve mandatory anchors in the correct Gherkin sections.\n"
            f"{json.dumps(batch.model_dump(mode='python'), indent=2)}\n"
        )
    else:
        mode = str(repair_context.get("repair_mode") or "anchor_fix")
        if mode == "readability":
            user_instruction = (
                "Rewrite the scenario using shorter, user-facing BDD language while preserving "
                "all mandatory anchor texts in the correct Given / When / Then sections.\n"
                "Return JSON only.\n"
                f"{json.dumps(repair_context, indent=2)}\n"
            )
        else:
            user_instruction = (
                "Repair the draft scenario so every missing or misplaced mandatory anchor appears "
                "in the correct section. Return JSON only.\n"
                f"{json.dumps(repair_context, indent=2)}\n"
            )

    response = await model_adapter.call_text_structured(
        task_name="scenario_generation",
        run_id=run_id,
        node_name="scenario_generation_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=BDDScenarioGenerationResult,
        prompt_name="scenario_generation",
        prompt_version=prompt_version,
        provider_override=settings.BDD_SCENARIO_GENERATION_MODEL_PROVIDER,
        model_name_override=settings.BDD_SCENARIO_GENERATION_MODEL_NAME,
    )
    if response.status.value == "success" and response.parsed_output:
        return response.parsed_output
    logger.error("LLM scenario generation failed: %s", response.error)
    return None


def _pick_scenario_for_intent(
    result: BDDScenarioGenerationResult, intent_id: str
) -> Optional[TestScenarioA6]:
    for sc in result.test_scenarios:
        if str(sc.source_intent_id) == str(intent_id):
            return sc
    if result.test_scenarios:
        return result.test_scenarios[0]
    return None


async def _generate_one_scenario_llm(
    run_id: str,
    intent: BehaviourIntentA5,
    blueprint: ScenarioWritingBlueprint,
    metrics: ScenarioGenerationMetricsA6,
) -> Tuple[TestScenarioA6, Dict[str, Any]]:
    written = await _llm_write_from_blueprint(run_id, blueprint)
    gen_method = "llm_anchor_grounded"
    repaired = False
    readability_repaired = False

    if not written:
        det = build_deterministic_test_scenario_from_intent(intent)
        _apply_intent_overlay(det, intent)
        det.source_blueprint_id = blueprint.blueprint_id
        det.generation_method = "deterministic_fallback_after_llm_anchor_failure"
        det.status = "draft"
        raw = validate_scenario_against_blueprint(det.model_dump(mode="python"), blueprint.model_dump(mode="python"))
        _attach_grounding(det, blueprint, raw)
        metrics.deterministic_fallback_count += 1
        metrics.llm_generated_count += 0
        return det, raw

    scn = _pick_scenario_for_intent(written, intent.intent_id)
    if not scn:
        det = build_deterministic_test_scenario_from_intent(intent)
        _apply_intent_overlay(det, intent)
        det.source_blueprint_id = blueprint.blueprint_id
        det.generation_method = "deterministic_fallback_after_llm_anchor_failure"
        det.status = "draft"
        raw = validate_scenario_against_blueprint(det.model_dump(mode="python"), blueprint.model_dump(mode="python"))
        _attach_grounding(det, blueprint, raw)
        metrics.deterministic_fallback_count += 1
        return det, raw

    _apply_intent_overlay(scn, intent)
    _merge_test_data_from_intent(scn, intent)
    scn.source_blueprint_id = blueprint.blueprint_id
    scn.status = "draft"

    raw = validate_scenario_against_blueprint(scn.model_dump(mode="python"), blueprint.model_dump(mode="python"))
    if not raw["grounding_passed"]:
        repair_ctx = {
            "repair_mode": "anchor_fix",
            "blueprint": blueprint.model_dump(mode="python"),
            "missing_anchor_ids": raw.get("missing_anchor_ids", []),
            "wrong_section_anchor_ids": raw.get("wrong_section_anchor_ids", []),
            "draft_scenario": scn.model_dump(mode="python"),
        }
        repaired_out = await _llm_write_from_blueprint(
            run_id, blueprint, repair_context=repair_ctx, prompt_version="v2_repair"
        )
        if repaired_out:
            scn2 = _pick_scenario_for_intent(repaired_out, intent.intent_id)
            if scn2:
                scn = scn2
                _apply_intent_overlay(scn, intent)
                _merge_test_data_from_intent(scn, intent)
                scn.source_blueprint_id = blueprint.blueprint_id
                scn.status = "draft"
                repaired = True
                metrics.llm_repaired_count += 1
        raw = validate_scenario_against_blueprint(scn.model_dump(mode="python"), blueprint.model_dump(mode="python"))

    if not raw["grounding_passed"]:
        det = build_deterministic_test_scenario_from_intent(intent)
        _apply_intent_overlay(det, intent)
        det.source_blueprint_id = blueprint.blueprint_id
        det.generation_method = "deterministic_fallback_after_llm_anchor_failure"
        det.status = "draft"
        raw = validate_scenario_against_blueprint(det.model_dump(mode="python"), blueprint.model_dump(mode="python"))
        _attach_grounding(det, blueprint, raw)
        metrics.deterministic_fallback_count += 1
        return det, raw

    if raw["grounding_passed"] and not raw.get("readability_passed", True):
        repair_ctx = {
            "repair_mode": "readability",
            "blueprint": blueprint.model_dump(mode="python"),
            "draft_scenario": scn.model_dump(mode="python"),
            "forbidden_pipeline_terms": raw.get("forbidden_pipeline_terms", []),
            "overlong_step_numbers": raw.get("overlong_step_numbers", []),
            "readability_hint": (
                "Rewrite the scenario using shorter, user-facing BDD language while preserving all anchors."
            ),
        }
        repaired_read = await _llm_write_from_blueprint(
            run_id, blueprint, repair_context=repair_ctx, prompt_version="v2_repair_readability"
        )
        if repaired_read:
            scn_r = _pick_scenario_for_intent(repaired_read, intent.intent_id)
            if scn_r:
                cand = scn_r
                _apply_intent_overlay(cand, intent)
                _merge_test_data_from_intent(cand, intent)
                cand.source_blueprint_id = blueprint.blueprint_id
                cand.status = "draft"
                raw_try = validate_scenario_against_blueprint(
                    cand.model_dump(mode="python"), blueprint.model_dump(mode="python")
                )
                if raw_try["grounding_passed"]:
                    scn = cand
                    raw = raw_try
                    readability_repaired = True
                    metrics.llm_readability_repair_count += 1

    _merge_hidden_assertions_into_scenario(scn, blueprint)

    if repaired and readability_repaired:
        scn.generation_method = "llm_anchor_grounded_repaired_readability"
    elif repaired:
        scn.generation_method = "llm_anchor_grounded_repaired"
    elif readability_repaired:
        scn.generation_method = "llm_anchor_grounded_readability_repaired"
    else:
        scn.generation_method = gen_method
    _attach_grounding(scn, blueprint, raw)
    metrics.llm_generated_count += 1
    return scn, raw


def _accumulate_metrics(metrics: ScenarioGenerationMetricsA6, grounding_raw: Dict[str, Any]) -> None:
    metrics.required_anchor_count += int(grounding_raw.get("required_anchor_count") or 0)
    metrics.matched_anchor_count += int(grounding_raw.get("matched_anchor_count") or 0)
    metrics.unexpected_placeholder_count += len(grounding_raw.get("unexpected_placeholders") or [])
    metrics.invalid_trace_ref_count += len(grounding_raw.get("invalid_trace_refs") or [])
    g = float(grounding_raw.get("section_coverage_given") or 0.0)
    w = float(grounding_raw.get("section_coverage_when") or 0.0)
    t = float(grounding_raw.get("section_coverage_then") or 0.0)
    # Running mean — approximate by count of scenarios via external finalize; store sums in custom attrs
    metrics._section_count += 1
    metrics._given_sum += g
    metrics._when_sum += w
    metrics._then_sum += t


def _finalize_metrics(metrics: ScenarioGenerationMetricsA6) -> None:
    if metrics.required_anchor_count:
        metrics.anchor_coverage_rate = metrics.matched_anchor_count / metrics.required_anchor_count
    n = metrics._section_count
    if n:
        metrics.given_anchor_coverage = metrics._given_sum / n
        metrics.when_anchor_coverage = metrics._when_sum / n
        metrics.then_anchor_coverage = metrics._then_sum / n


def _persist_scenario_row(
    db: AsyncSession,
    run_id: str,
    scn: TestScenarioA6,
    *,
    db_scenario_id: str,
) -> None:
    gherkin_lines = [f"Scenario: {scn.scenario_name}"]
    for s in scn.steps:
        gherkin_lines.append(f"  {s.keyword} {s.text}")

    pg = scn.pre_generation_grounding.model_dump(mode="python") if scn.pre_generation_grounding else {}
    kw_cov = float(pg.get("keyword_anchor_coverage") or 0.0)
    grounding_score = kw_cov * 100.0

    test_data_dicts = [td.model_dump() for td in scn.test_data]

    scores = {
        "intent_alignment_score": 0.0,
        "screen_intent_grounding_score": 0.0,
        "flow_grounding_score": 0.0,
        "evidence_grounding_score": 0.0,
        "bdd_structure_score": 0.0,
        "data_and_assertion_quality_score": 0.0,
        "hallucination_penalty": 0.0,
        "keyword_anchor_coverage": kw_cov,
        "evidence_precheck_deferred": True,
    }

    bs = BehaviourScenario(
        id=db_scenario_id,
        run_id=run_id,
        flow_id=scn.source_flow_id,
        intent_id=scn.source_intent_id,
        feature=scn.source_flow_name,
        scenario_title=scn.scenario_name,
        scenario_type=scn.scenario_type,
        gherkin_text="\n".join(gherkin_lines),
        bdd_steps_json={"steps": [s.model_dump() for s in scn.steps]},
        evidence_json={
            "assertions": [a.model_dump() for a in scn.assertions],
            "test_data": test_data_dicts,
            "preconditions": scn.preconditions,
            "test_objective": scn.test_objective,
            "pre_generation_grounding": pg,
            "source_blueprint_id": scn.source_blueprint_id,
            "generation_method": scn.generation_method or "deterministic_python",
            "grounding_contract": scn.grounding_contract.model_dump(mode="python") if scn.grounding_contract else {},
        },
        assumptions_json={"items": getattr(scn, "assumptions", []) or []},
        warnings_json={"items": getattr(scn, "warnings", []) or []},
        initial_confidence=1.0 if scn.confidence == "high" else 0.5 if scn.confidence == "medium" else 0.2,
        confidence_label=scn.confidence,
        status="draft",
        grounding_mode="anchor_grounded",
        validation_status="pending_audit",
        grounding_score=grounding_score,
        evidence_coverage_score=0.0,
        final_reliability=0.0,
        scores_json=scores,
        step_audits_json={"audits": []},
        hallucination_flags_json={"flags": []},
        acceptance_decision_json={
            "include_in_final_output": False,
            "reason": "Pending scenario_evidence_audit",
        },
        validated_at=None,
    )
    db.add(bs)


async def run_bdd_scenario_generation(
    db: AsyncSession,
    run_id: str,
    intent_package: Dict[str, Any],
    compressed_catalog_package: Optional[Dict[str, Any]] = None,
    screen_intent_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Agent 6 — BDD Scenario Generation.

    BehaviourIntentA5 → blueprints → (optional LLM) → keyword validation → BehaviourScenario draft rows.
    """
    start_time = time.time()
    log_event("bdd_scenario_generation_started", run_id=run_id)

    compressed_catalog_package = compressed_catalog_package or {}
    screen_intent_package = screen_intent_package or {}

    behaviour_intents_raw = intent_package.get("behaviour_intents", [])
    empty_summary = ScenarioGenerationSummaryA6(
        total_behaviour_intents=0,
        total_test_scenarios=0,
        total_unresolved_scenario_items=0,
        coverage_rate=0.0,
    )
    empty_metrics = ScenarioGenerationMetricsA6()

    if not behaviour_intents_raw:
        out = BDDScenarioGenerationResult(
            test_scenarios=[],
            unresolved_scenario_items=[],
            coverage_matrix=[],
            generation_summary=empty_summary,
            scenario_writing_blueprints=[],
            scenario_generation_metrics=empty_metrics,
        ).model_dump()
        out["report"] = {
            "generated_scenario_count": 0,
            "unresolved_count": 0,
            "coverage_rate": 0.0,
            "mode": "none",
            "auto_revision_retry": False,
            "scenario_generation_metrics": empty_metrics.model_dump(mode="python"),
        }
        return out

    behaviour_intents = [BehaviourIntentA5.model_validate(i) for i in behaviour_intents_raw]
    blueprints = build_scenario_blueprints(
        behaviour_intents=behaviour_intents,
        compressed_catalog_package=compressed_catalog_package,
    )
    blueprint_by_intent = {b.source_intent_id: b for b in blueprints}

    metrics = ScenarioGenerationMetricsA6(blueprint_count=len(blueprints))

    test_scenarios: List[TestScenarioA6] = []
    unresolved_items: List[UnresolvedScenarioItemA6] = []
    coverage_matrix: List[CoverageMatrixItemA6] = []

    use_llm = settings.USE_LLM_FOR_SCENARIO_GENERATION

    for intent in behaviour_intents:
        pre_issue = _precheck_behaviour_intent_for_scenarios(intent)
        if pre_issue:
            unresolved_items.append(pre_issue)
            coverage_matrix.append(
                CoverageMatrixItemA6(
                    intent_id=intent.intent_id,
                    coverage_status="unresolved",
                    reason=pre_issue.reason,
                )
            )
            metrics.unresolved_count += 1
            continue

        bp = blueprint_by_intent[intent.intent_id]
        grounding_raw: Dict[str, Any]

        if use_llm:
            scn_llm, grounding_raw = await _generate_one_scenario_llm(run_id, intent, bp, metrics)
            test_scenarios.append(scn_llm)
        else:
            scn_det = build_deterministic_test_scenario_from_intent(intent)
            _apply_intent_overlay(scn_det, intent)
            scn_det.source_blueprint_id = bp.blueprint_id
            scn_det.generation_method = "deterministic_python"
            scn_det.status = "draft"
            grounding_raw = validate_scenario_against_blueprint(
                scn_det.model_dump(mode="python"), bp.model_dump(mode="python")
            )
            _attach_grounding(scn_det, bp, grounding_raw)
            test_scenarios.append(scn_det)

        _accumulate_metrics(metrics, grounding_raw)
        coverage_matrix.append(
            CoverageMatrixItemA6(
                intent_id=intent.intent_id,
                scenario_id=test_scenarios[-1].scenario_id,
                coverage_status="covered",
                reason="Generated with keyword anchor pre-check",
            )
        )

    _finalize_metrics(metrics)

    result = BDDScenarioGenerationResult(
        test_scenarios=test_scenarios,
        unresolved_scenario_items=unresolved_items,
        coverage_matrix=coverage_matrix,
        generation_summary=ScenarioGenerationSummaryA6(
            total_behaviour_intents=len(behaviour_intents),
            total_test_scenarios=len(test_scenarios),
            total_unresolved_scenario_items=len(unresolved_items),
            coverage_rate=len(test_scenarios) / len(behaviour_intents) if behaviour_intents else 0.0,
        ),
        scenario_writing_blueprints=blueprints,
        scenario_generation_metrics=metrics,
    )

    scenario_db_id_map: Dict[str, str] = {}
    for scn in result.test_scenarios:
        old_sid = str(scn.scenario_id)
        db_id = _generate_behaviour_scenario_id()
        scenario_db_id_map[old_sid] = db_id
        scn.scenario_id = db_id
        _persist_scenario_row(db, run_id, scn, db_scenario_id=db_id)

    for cm in result.coverage_matrix:
        oid = cm.scenario_id
        if oid and oid in scenario_db_id_map:
            cm.scenario_id = scenario_db_id_map[oid]

    try:
        await db.commit()
    except Exception as e:
        logger.error("Failed to commit scenarios for run %s: %s", run_id, e)
        await db.rollback()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("bdd_scenario_generation_completed", run_id=run_id, duration_ms=duration_ms)

    out_payload = result.model_dump(mode="python")
    for sc in out_payload.get("test_scenarios") or []:
        sc_steps = sc.get("steps", [])
        sc["gherkin"] = [f"Scenario: {sc.get('scenario_name', '')}"] + [
            f"{s.get('keyword')} {s.get('text')}" for s in sc_steps
        ]

    gen_mode = "llm_anchor_grounded" if use_llm else "deterministic_python"
    out_payload["report"] = {
        "generated_scenario_count": len(test_scenarios),
        "unresolved_count": len(unresolved_items),
        "coverage_rate": result.generation_summary.coverage_rate,
        "mode": gen_mode,
        "auto_revision_retry": bool(use_llm),
        "scenario_generation_metrics": metrics.model_dump(mode="python"),
    }
    out_payload["scenario_generation_metrics"] = metrics.model_dump(mode="python")

    return out_payload
