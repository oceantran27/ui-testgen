"""
Read-only wrappers and re-exports for global flow discovery production services.

Do NOT import orchestration helpers with DB or unmanaged side effects, e.g.:
``run_global_flow_discovery``, ``_persist_bridge_flow_rows``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings as _settings
from app.constants.ui_screen_taxonomy import normalize_screen_type
from app.model_providers.schemas import (
    JointScreenUnderstandingResult,
    ScreenIntentExtractionV2Result,
    UIStateExtractionV2Result,
)
from app.services.compressed_representation_service import (
    run_build_compressed_catalog,
    validate_compressed_catalog_size,
)
from app.services.global_flow_discovery_catalog import (
    build_llm_discovery_catalog,
    catalog_state_ids_from_compressed_pkg,
    catalog_state_ids_from_llm_catalog,
    validate_discovery_input,
)
from app.services.global_flow_discovery_service import (
    assemble_flow_discovery_bundle,
    compute_discovery_report,
)
from app.services.global_flow_discovery_validate import (
    extract_ordered_states_from_steps,
    repair_or_filter_discovery_output,
    validate_and_repair_global_flow_discovery,
    validate_discovery_output,
)
from app.services.joint_screen_understanding_ids import prefix_screen_intent_payload
from app.services.joint_screen_understanding_validation import validate_joint_screen_understanding_structured
from app.services.screen_intent_validation import process_screen_intents_for_state
from app.services.ui_state_evidence_persist import (
    ensure_fallback_interaction_groups,
    prefix_ui_state_ids,
)


def validate_discovery_catalog_dimensions(
    pkg: Dict[str, Any],
    *,
    max_screens: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Size guard matching production global flow discovery (uses settings.GLOBAL_FLOW_DISCOVERY_MAX_SCREENS)."""
    lim = max_screens if max_screens is not None else int(_settings.GLOBAL_FLOW_DISCOVERY_MAX_SCREENS)
    return validate_compressed_catalog_size(pkg, max_screens=lim)


def build_validation_snapshot(
    raw: Dict[str, Any],
    *,
    llm_catalog: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str], Dict[str, Any]]:
    """
    Pre-scan invalid refs with ``validate_discovery_output``, repair with
    ``validate_and_repair_global_flow_discovery``, return JSON-serializable
    repaired dict, merged discovery_warnings, and combined metrics.

    Intended for assembling ``RawFlowDiscoveryExperimentPackage`` in raw_capture (Sprint 2+).
    """
    preview = validate_discovery_output(raw, llm_catalog=llm_catalog)
    repaired_model, metrics = validate_and_repair_global_flow_discovery(
        raw, llm_catalog=llm_catalog
    )
    combined: Dict[str, Any] = {"pre_scan": preview, **metrics}
    repaired_dict = repaired_model.model_dump(mode="json")
    warnings = list(repaired_model.discovery_warnings)
    return repaired_dict, warnings, combined


__all__ = [
    "JointScreenUnderstandingResult",
    "ScreenIntentExtractionV2Result",
    "UIStateExtractionV2Result",
    "assemble_flow_discovery_bundle",
    "build_llm_discovery_catalog",
    "build_validation_snapshot",
    "catalog_state_ids_from_compressed_pkg",
    "catalog_state_ids_from_llm_catalog",
    "compute_discovery_report",
    "ensure_fallback_interaction_groups",
    "extract_ordered_states_from_steps",
    "normalize_screen_type",
    "prefix_screen_intent_payload",
    "prefix_ui_state_ids",
    "process_screen_intents_for_state",
    "repair_or_filter_discovery_output",
    "run_build_compressed_catalog",
    "validate_and_repair_global_flow_discovery",
    "validate_compressed_catalog_size",
    "validate_discovery_catalog_dimensions",
    "validate_discovery_input",
    "validate_discovery_output",
    "validate_joint_screen_understanding_structured",
]
