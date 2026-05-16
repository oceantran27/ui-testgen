"""screen_behaviour_intents action / selection JSON columns

Revision ID: 2c9f4a1e8d0b
Revises: 617efa320277
Create Date: 2026-05-16

Adds columns expected by ScreenBehaviourIntent ORM (v2 extraction) that were
missing from the initial screen_behaviour_intents table creation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2c9f4a1e8d0b"
down_revision: Union[str, Sequence[str], None] = "617efa320277"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("selection_options_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("commit_action_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("secondary_actions_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("local_action_sequence_templates_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screen_behaviour_intents", "local_action_sequence_templates_json")
    op.drop_column("screen_behaviour_intents", "secondary_actions_json")
    op.drop_column("screen_behaviour_intents", "commit_action_json")
    op.drop_column("screen_behaviour_intents", "selection_options_json")
