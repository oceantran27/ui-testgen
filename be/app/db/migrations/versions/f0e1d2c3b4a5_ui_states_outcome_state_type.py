"""ui_states outcome_state_type

Revision ID: f0e1d2c3b4a5
Revises: 2c9f4a1e8d0b
Create Date: 2026-05-16

Adds column expected by UIState ORM / UI state extraction v2 schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, Sequence[str], None] = "2c9f4a1e8d0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ui_states",
        sa.Column(
            "outcome_state_type",
            sa.String(),
            nullable=False,
            server_default="normal",
        ),
    )


def downgrade() -> None:
    op.drop_column("ui_states", "outcome_state_type")
