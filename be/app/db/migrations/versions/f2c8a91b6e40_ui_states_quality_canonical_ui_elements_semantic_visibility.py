"""ui_states canonical + state_quality; ui_elements semantic_role + visibility

Revision ID: f2c8a91b6e40
Revises: a8f3c91d2b4e
Create Date: 2026-05-12

Aligns DB with ORM (prompt-driven extraction fields).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c8a91b6e40"
down_revision: Union[str, Sequence[str], None] = "a8f3c91d2b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_json_empty = sa.text("'{}'::json")


def upgrade() -> None:
    op.add_column(
        "ui_states",
        sa.Column(
            "state_quality",
            sa.JSON(),
            nullable=False,
            server_default=_json_empty,
        ),
    )
    op.add_column(
        "ui_states",
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "ui_states",
        sa.Column("canonical_id", sa.String(), nullable=True),
    )

    op.add_column(
        "ui_elements",
        sa.Column("semantic_role", sa.String(), nullable=True),
    )
    op.add_column(
        "ui_elements",
        sa.Column(
            "visibility",
            sa.String(),
            nullable=False,
            server_default="fully_visible",
        ),
    )


def downgrade() -> None:
    op.drop_column("ui_elements", "visibility")
    op.drop_column("ui_elements", "semantic_role")

    op.drop_column("ui_states", "canonical_id")
    op.drop_column("ui_states", "is_canonical")
    op.drop_column("ui_states", "state_quality")
