"""Orchestration for behaviour contracts + scenario drafts (Agents 5 + 6)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.behaviour_contract_service import run_behaviour_contract_builder
from app.services.scenario_generation_service import run_bdd_scenario_generation


async def run_generate_tests(
    db: AsyncSession,
    run_id: str,
    *,
    flow_discovery_result: Dict[str, Any],
    state_catalog: List[Dict[str, Any]],
    compressed_catalog_package: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Returns (intent_package, scenario_draft_package)."""
    intent_pkg = await run_behaviour_contract_builder(
        db=db,
        run_id=run_id,
        flow_discovery_result=flow_discovery_result,
        state_catalog=state_catalog,
    )
    scenario_pkg = await run_bdd_scenario_generation(
        db=db,
        run_id=run_id,
        intent_package=intent_pkg,
        compressed_catalog_package=compressed_catalog_package,
    )
    return intent_pkg, scenario_pkg
