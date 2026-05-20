"""Orchestrate catalog + discovery JSON → ``GroundTruthFlowPackage``."""

from __future__ import annotations

from typing import Any, Dict, Optional

from experiments.flow_discovery.gt_converter import (
    action_converter,
    branch_group_converter,
    flow_converter,
    state_converter,
    transition_converter,
)
from experiments.flow_discovery.gt_converter.ground_truth_auto_validator import annotate_package_issues
from experiments.flow_discovery.schemas.common_schema import AutoValidationBlock, ReviewInfo
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def convert_raw_package_to_draft(
    package: RawFlowDiscoveryExperimentPackage,
    *,
    app_id_override: Optional[str] = None,
) -> GroundTruthFlowPackage:
    """
    Convert experiment raw envelope to reviewable ground truth draft.

    Prefers ``repaired_model_output`` when present (matches production repair path).
    """

    app_id = (app_id_override or package.app_id).strip()

    compressed: Dict[str, Any] = package.compressed_catalog_package
    cards = compressed.get("compressed_catalog") or []

    states, catalog_to_gt, card_index = state_converter.build_states_from_compressed_catalog(app_id, compressed)
    card_by_catalog = dict(card_index)

    model_dict = package.repaired_model_output or package.raw_model_output
    if not isinstance(model_dict, dict):
        raise ValueError("model_output_must_be_dict")

    actions = action_converter.build_actions_for_catalog(app_id, cards if isinstance(cards, list) else [], catalog_to_gt)

    txs = transition_converter.build_transitions(
        app_id,
        model_dict,
        catalog_to_gt,
        card_by_catalog,
    )
    flows = flow_converter.build_flows_from_model(
        app_id,
        model_dict,
        card_by_catalog,
        catalog_to_gt,
        txs,
    )

    branch_groups: list = branch_group_converter.build_branch_groups(app_id, txs)

    pkg = GroundTruthFlowPackage(
        app_id=app_id,
        source_raw_run_id=package.run_id,
        states=list(states),
        actions=list(actions),
        transitions=list(txs),
        flows=list(flows),
        branch_groups=list(branch_groups),
        package_review=ReviewInfo(review_status="draft_from_model"),
        package_auto_validation=AutoValidationBlock(extras={"source_schema": package.schema_version}),
    )

    annotate_package_issues(pkg)
    return pkg
