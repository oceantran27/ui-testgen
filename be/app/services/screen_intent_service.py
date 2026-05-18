"""
Screen Intent Service — helpers for persisting validated ScreenBehaviourIntent rows (joint pipeline).
"""

import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.screen_intent import ScreenBehaviourIntent
from app.model_providers.schemas import ScreenBehaviourIntentA2


def _generate_screen_intent_id() -> str:
    return f"sbi_{uuid.uuid4().hex[:12]}"


def generate_screen_intent_id() -> str:
    """Public id factory for joint pipeline reuse."""
    return _generate_screen_intent_id()


def persist_screen_intent_catalog_rows(
    db: AsyncSession,
    run_id: str,
    state_id: str,
    catalog_dicts: List[Dict[str, Any]],
    draft_raw_outer: Dict[str, Any] | None,
) -> None:
    """Insert validated intent catalogue rows."""
    for intent_dict in catalog_dicts:
        vdetail = intent_dict.pop("_validation_detail", None)
        hydrated = ScreenBehaviourIntentA2.model_validate(intent_dict)
        vid = hydrated.screen_intent_id

        draft_snap = None
        if isinstance(vdetail, dict):
            draft_snap = vdetail.get("draft_snapshot")

        db_row = ScreenBehaviourIntent(
            id=vid,
            run_id=run_id,
            state_id=state_id,
            source_group_id=hydrated.source_group_id,
            intent_name=hydrated.intent_name,
            intent_kind=hydrated.intent_kind,
            local_user_goal=hydrated.local_user_goal,
            primary_action_json=(
                hydrated.primary_action.model_dump() if hydrated.primary_action is not None else None
            ),
            selection_options_json=[o.model_dump() for o in hydrated.selection_options],
            commit_action_json=(
                hydrated.commit_action.model_dump() if hydrated.commit_action is not None else None
            ),
            secondary_actions_json=[a.model_dump() for a in hydrated.secondary_actions],
            local_action_sequence_templates_json=[
                s.model_dump() for s in hydrated.local_action_sequence_templates
            ],
            required_input_element_ids_json=list(hydrated.required_input_element_ids),
            evidence_json=[e.model_dump() for e in hydrated.evidence_refs],
            confidence=hydrated.confidence,
            model_confidence=hydrated.model_confidence,
            validation_confidence=hydrated.validation_confidence,
            validation_report_json=vdetail,
            raw_model_output_json=draft_snap,
            raw_result_json=None,
        )
        db.add(db_row)
