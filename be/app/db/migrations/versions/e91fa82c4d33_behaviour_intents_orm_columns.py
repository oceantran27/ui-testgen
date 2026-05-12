"""behaviour_intents: columns aligned with BehaviourIntent ORM / prompts

Revision ID: e91fa82c4d33
Revises: f2c8a91b6e40
Create Date: 2026-05-12

Adds fields present on app.db.models.behaviour_intent but missing from the
initial behaviour_intents table migration (d90bc9652cfe).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91fa82c4d33"
down_revision: Union[str, Sequence[str], None] = "f2c8a91b6e40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_json_empty = sa.text("'{}'::json")


def upgrade() -> None:
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "intent_scope",
            sa.String(),
            nullable=False,
            server_default="end_to_end",
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "observable_precondition_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "main_user_action_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "observable_result_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "grounding_evidence_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "grounding_level",
            sa.String(),
            nullable=False,
            server_default="grounded",
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "ambiguity_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "behaviour_intents",
        sa.Column(
            "evidence_element_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )


def downgrade() -> None:
    op.drop_column("behaviour_intents", "evidence_element_ids_json")
    op.drop_column("behaviour_intents", "ambiguity_json")
    op.drop_column("behaviour_intents", "grounding_level")
    op.drop_column("behaviour_intents", "grounding_evidence_json")
    op.drop_column("behaviour_intents", "observable_result_json")
    op.drop_column("behaviour_intents", "main_user_action_json")
    op.drop_column("behaviour_intents", "observable_precondition_json")
    op.drop_column("behaviour_intents", "intent_scope")
