"""screen_behaviour_intents Phase 2: raw validation columns + rename required_input

Revision ID: b1e2c3d4a5f6
Revises: a3f8c21d9e01
Create Date: 2026-05-17

Adds raw_model_output_json, validation_report_json, dual confidence tracking;
renames required_input_groups_json → required_input_element_ids_json per Phase 2 spec.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1e2c3d4a5f6"
down_revision: Union[str, Sequence[str], None] = "a3f8c21d9e01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("raw_model_output_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("validation_report_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("model_confidence", sa.String(), nullable=True),
    )
    op.add_column(
        "screen_behaviour_intents",
        sa.Column("validation_confidence", sa.String(), nullable=True),
    )
    op.alter_column(
        "screen_behaviour_intents",
        "required_input_groups_json",
        new_column_name="required_input_element_ids_json",
        existing_type=sa.JSON(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "screen_behaviour_intents",
        "required_input_element_ids_json",
        new_column_name="required_input_groups_json",
        existing_type=sa.JSON(),
        existing_nullable=True,
    )
    op.drop_column("screen_behaviour_intents", "validation_confidence")
    op.drop_column("screen_behaviour_intents", "model_confidence")
    op.drop_column("screen_behaviour_intents", "validation_report_json")
    op.drop_column("screen_behaviour_intents", "raw_model_output_json")
