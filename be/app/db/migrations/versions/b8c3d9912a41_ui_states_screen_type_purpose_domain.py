"""ui_states screen_type screen_purpose domain

Revision ID: b8c3d9912a41
Revises: 7db9f1c3afcc
Create Date: 2026-05-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c3d9912a41"
down_revision: Union[str, Sequence[str], None] = "7db9f1c3afcc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ui_states", sa.Column("screen_type", sa.String(), nullable=True))
    op.add_column("ui_states", sa.Column("screen_purpose", sa.String(), nullable=True))
    op.add_column("ui_states", sa.Column("domain", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("ui_states", "domain")
    op.drop_column("ui_states", "screen_purpose")
    op.drop_column("ui_states", "screen_type")
