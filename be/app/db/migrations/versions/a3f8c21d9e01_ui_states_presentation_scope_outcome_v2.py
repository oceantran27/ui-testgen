"""ui_states presentation_scope and outcome_state_type v2 enums

Revision ID: a3f8c21d9e01
Revises: f0e1d2c3b4a5
Create Date: 2026-05-17

Adds presentation_scope; renames outcome_state_type defaults and backfills legacy values.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3f8c21d9e01"
down_revision: Union[str, Sequence[str], None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ui_states",
        sa.Column("presentation_scope", sa.String(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'neutral'
            WHERE outcome_state_type = 'normal'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'error'
            WHERE outcome_state_type = 'failure'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'empty'
            WHERE outcome_state_type = 'empty_state'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'confirmation_required'
            WHERE outcome_state_type = 'confirmation'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'review_required'
            WHERE outcome_state_type = 'review'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'unknown'
            WHERE outcome_state_type = 'modal'
            """
        )
    )
    op.alter_column(
        "ui_states",
        "outcome_state_type",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'neutral'"),
        existing_server_default=sa.text("'normal'"),
    )


def downgrade() -> None:
    op.alter_column(
        "ui_states",
        "outcome_state_type",
        existing_type=sa.String(),
        existing_nullable=False,
        server_default=sa.text("'normal'"),
        existing_server_default=sa.text("'neutral'"),
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'normal'
            WHERE outcome_state_type = 'neutral'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'failure'
            WHERE outcome_state_type = 'error'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'empty_state'
            WHERE outcome_state_type = 'empty'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'confirmation'
            WHERE outcome_state_type = 'confirmation_required'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ui_states SET outcome_state_type = 'review'
            WHERE outcome_state_type = 'review_required'
            """
        )
    )
    op.drop_column("ui_states", "presentation_scope")
