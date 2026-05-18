"""Drop unused behaviour_scenarios.path_id

Revision ID: f9e8d7c6b5a4
Revises: 7306af112e61
Create Date: 2026-05-18

Column was never read or written by application code; scenario rows are created
without path_id in scenario_generation_service.

See be/app/db/schema_audit_drop_candidates.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f9e8d7c6b5a4"
down_revision: Union[str, Sequence[str], None] = "7306af112e61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("behaviour_scenarios", "path_id")


def downgrade() -> None:
    op.add_column(
        "behaviour_scenarios",
        sa.Column("path_id", sa.String(), nullable=True),
    )
