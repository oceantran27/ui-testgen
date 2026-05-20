"""Aggregate transitions that share anchor state + normalized trigger."""

from __future__ import annotations

from typing import List

from experiments.flow_discovery.gt_converter.transition_converter import (
    transitions_by_branch_key,
)
from experiments.flow_discovery.schemas.ground_truth_schema import (
    GroundTruthBranchGroup,
    GroundTruthTransition,
)


def build_branch_groups(
    app_id: str,
    transitions: List[GroundTruthTransition],
    *,
    default_branching_flow_id: str | None = None,
) -> List[GroundTruthBranchGroup]:
    grouped = transitions_by_branch_key(transitions)
    out: List[GroundTruthBranchGroup] = []
    ctr = 0
    for key, gt_ids in grouped.items():
        if len(gt_ids) < 2:
            continue
        parts = key.split("||", 1)
        anchor = parts[0] if parts else ""
        trig = parts[1] if len(parts) > 1 else ""

        ctr += 1
        bgid = f"gt_bg_{app_id}_{anchor.replace(':', '_').replace('>', '_').replace('=', '_').replace('-', '')[:42]}_{ctr:03d}"
        out.append(
            GroundTruthBranchGroup(
                branch_group_id=bgid,
                anchor_source_gt_state_id=anchor,
                normalized_trigger=trig,
                state_ids=list({anchor}),
                branching_flow_id=default_branching_flow_id,
                alternative_transition_ids=list(dict.fromkeys(gt_ids)),
                rationale=(
                    "auto_group_same_trigger"
                ),
            )
        )

    return out
