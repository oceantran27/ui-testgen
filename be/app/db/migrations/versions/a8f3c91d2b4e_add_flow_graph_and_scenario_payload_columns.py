"""Add flow graph columns and behaviour_scenario payload columns

Revision ID: a8f3c91d2b4e
Revises: 50d620491557
Create Date: 2026-05-12

Aligns DB with ORM:
- flows: flow_label, entry_state_id, terminal_state_ids_json, flow_completeness_json
- flow_transitions: LLM / visual validation fields
- behaviour_scenarios: bdd_steps_json, final_reliability, scores_json, step_audits_json, acceptance_decision_json
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8f3c91d2b4e"
down_revision: Union[str, Sequence[str], None] = "50d620491557"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_json_empty = sa.text("'{}'::json")


def upgrade() -> None:
    op.add_column("flows", sa.Column("flow_label", sa.String(), nullable=True))
    op.add_column("flows", sa.Column("entry_state_id", sa.String(), nullable=True))
    op.add_column(
        "flows",
        sa.Column(
            "terminal_state_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "flows",
        sa.Column(
            "flow_completeness_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )

    op.add_column(
        "flow_transitions", sa.Column("trigger_element_id", sa.String(), nullable=True)
    )
    op.add_column(
        "flow_transitions", sa.Column("transition_basis", sa.String(), nullable=True)
    )
    op.add_column(
        "flow_transitions",
        sa.Column(
            "ordering_strength",
            sa.String(),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        "flow_transitions",
        sa.Column(
            "supporting_evidence_refs_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "flow_transitions", sa.Column("uncertainty_reason", sa.String(), nullable=True)
    )
    op.add_column(
        "flow_transitions", sa.Column("visual_delta_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "flow_transitions",
        sa.Column(
            "transition_support",
            sa.String(),
            nullable=False,
            server_default="not_verifiable",
        ),
    )
    op.add_column(
        "flow_transitions",
        sa.Column(
            "validation_flags_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )

    op.add_column(
        "behaviour_scenarios",
        sa.Column(
            "bdd_steps_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_scenarios",
        sa.Column(
            "final_reliability",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "behaviour_scenarios",
        sa.Column(
            "scores_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_scenarios",
        sa.Column(
            "step_audits_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_scenarios",
        sa.Column(
            "acceptance_decision_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )


def downgrade() -> None:
    op.drop_column("behaviour_scenarios", "acceptance_decision_json")
    op.drop_column("behaviour_scenarios", "step_audits_json")
    op.drop_column("behaviour_scenarios", "scores_json")
    op.drop_column("behaviour_scenarios", "final_reliability")
    op.drop_column("behaviour_scenarios", "bdd_steps_json")

    op.drop_column("flow_transitions", "validation_flags_json")
    op.drop_column("flow_transitions", "transition_support")
    op.drop_column("flow_transitions", "visual_delta_json")
    op.drop_column("flow_transitions", "uncertainty_reason")
    op.drop_column("flow_transitions", "supporting_evidence_refs_json")
    op.drop_column("flow_transitions", "ordering_strength")
    op.drop_column("flow_transitions", "transition_basis")
    op.drop_column("flow_transitions", "trigger_element_id")

    op.drop_column("flows", "flow_completeness_json")
    op.drop_column("flows", "terminal_state_ids_json")
    op.drop_column("flows", "entry_state_id")
    op.drop_column("flows", "flow_label")
