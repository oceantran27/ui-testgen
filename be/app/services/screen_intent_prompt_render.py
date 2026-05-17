"""Render taxonomy blocks for Phase 2 screen intent prompts (avoid static enum drift)."""

from __future__ import annotations

from textwrap import dedent

from app.constants.screen_intent_taxonomy import (
    EVIDENCE_TYPE_ORDERED,
    INTENT_KIND_ORDERED,
    MODEL_CONFIDENCE_VALUES,
    STEP_TYPE_ORDERED,
    taxonomy_bullets,
    UNRESOLVED_REASON_ORDERED,
    VISIBLE_STATUS_ORDERED,
)


def render_phase2_taxonomy_system_suffix() -> str:
    mc = "|".join(sorted(MODEL_CONFIDENCE_VALUES))
    return dedent(
        f"""

        ── Allowed enumerated values (backend-enforced — use EXACT spelling) ──

        **intent_kind** (pick exactly one per intent):
        {taxonomy_bullets(INTENT_KIND_ORDERED)}

        **model_confidence** (MODEL only — final confidence computed by backend):
        - Allowed: `{mc}`

        **visible_status**
        {taxonomy_bullets(VISIBLE_STATUS_ORDERED)}

        **evidence_refs[].evidence_type**
        {taxonomy_bullets(EVIDENCE_TYPE_ORDERED)}

        **local_action_sequence_templates.steps[].step_type**
        {taxonomy_bullets(STEP_TYPE_ORDERED)}

        **Option reference:** `selection_options[].option_ref_type` must be `element` OR `action`.
        Provide the matching `option_element_id` OR `option_action_id` accordingly (the other MUST be null).

        **unresolved_screen_groups.reason_code**
        {taxonomy_bullets(UNRESOLVED_REASON_ORDERED)}

        Classification rubric (decision aide):
        - Input controls visible but NO commit action in the group ⇒ prefer `data_entry` for that group's typing goal.
        - Input + explicit Save/Submit/Continue ⇒ emit separate `data_entry` and `submission` intents when both goals are grounded.
        - Search field alone ⇒ `data_entry`; explicit Search control/action ⇒ `search`.
        - Picking date/plan/item/filter value (not yet committed) ⇒ `selection` (filtering maps here unless lookup is explicitly search).
        - Menu/tab/link/view-detail/back ⇒ `navigation`.
        - Save / Create / Book / Submit / Continue / Place order ⇒ `submission`.
        - Confirm / Accept / Yes on explicit prompt ⇒ `confirmation`.
        - Cancel / Back / Close / Dismiss / Decline / Discard ⇒ `cancellation`.
        - Delete / Remove / Clear item ⇒ `deletion`.
        - Edit existing state/data ⇒ `editing`.
        - Visible feedback/snackbar/dialog with OK / Dismiss / Got it ⇒ `feedback_acknowledgement`.
        - Read-only / no actionable control ⇒ `informative`.

        Principle reminders:
        - Backend is source of truth for `action_type` and label text — output **IDs only** for actions/options/evidence (`primary_action_id`, `commit_action_id`, …); never invent `tap`/`click_button` synonyms.
        - Evidence is **references only** (`evidence_type` + `source_id`). Do NOT paste long free-text rationales inside evidence — use `intent_name` / `local_user_goal` for wording.
        - Do NOT describe future/next-screen outcomes inside `intent_name`, `local_user_goal`, or step text (local screen only).

        ── ID constraints ──
        The user JSON includes `allowed_group_ids`, `allowed_element_ids_by_group`, `allowed_action_ids_by_group`, and `allowed_feedback_ids_by_group`.
        Every `source_group_id`, element id, action id, and feedback id you emit MUST appear in those maps.
        If you cannot ground an intent within those IDs, add the interaction group id to `unresolved_screen_groups` with an appropriate **reason_code** and short **details**.
        """
    ).strip()
