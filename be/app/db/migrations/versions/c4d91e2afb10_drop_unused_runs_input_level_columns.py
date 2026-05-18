"""Drop unused runs input_level columns

Revision ID: c4d91e2afb10
Revises: b1e2c3d4a5f6
Create Date: 2026-05-17

These columns were never read or written outside the ORM layer; pipeline and API use
Flow.input_level and run config schema (input_level_mode), not Run.input_level*.

See be/app/db/schema_audit_drop_candidates.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d91e2afb10"
down_revision: Union[str, Sequence[str], None] = "b1e2c3d4a5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("runs", "input_level_reason")
    op.drop_column("runs", "input_level_confidence")
    op.drop_column("runs", "input_level")


def downgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("input_level", sa.String(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("input_level_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("input_level_reason", sa.String(), nullable=True),
    )
