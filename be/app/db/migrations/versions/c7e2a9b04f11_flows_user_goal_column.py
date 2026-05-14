"""flows user_goal column (ORM parity)

Revision ID: c7e2a9b04f11
Revises: b8c3d9912a41
Create Date: 2026-05-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7e2a9b04f11"
down_revision: Union[str, Sequence[str], None] = "b8c3d9912a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flows", sa.Column("user_goal", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("flows", "user_goal")
