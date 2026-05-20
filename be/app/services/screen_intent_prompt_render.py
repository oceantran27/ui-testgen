"""Render taxonomy blocks for Phase 2 screen intent prompts (avoid static enum drift)."""

from __future__ import annotations

from textwrap import dedent

from app.constants.screen_intent_taxonomy import (
    EVIDENCE_TYPE_ORDERED,
    INTENT_KIND_ORDERED,
    MODEL_CONFIDENCE_VALUES,
    STEP_TYPE_ORDERED,
    UNRESOLVED_REASON_ORDERED,
    VISIBLE_STATUS_ORDERED,
    taxonomy_bullets,
)


def render_phase2_taxonomy_system_suffix() -> str:
    """Backend-enforced enums for `screen_intents`; must match screen_intent_taxonomy + JointScreenUnderstandingResult."""
    mc = "|".join(sorted(MODEL_CONFIDENCE_VALUES))
    _split_at = UNRESOLVED_REASON_ORDERED.index("no_interaction_group")
    llm_reason_block = taxonomy_bullets(UNRESOLVED_REASON_ORDERED[:_split_at])
    srv_reason_block = taxonomy_bullets(UNRESOLVED_REASON_ORDERED[_split_at:])
    return dedent(
        f"""

        ── Allowed enumerated values (backend-enforced — EXACT spelling) ──

        Phase B JSON must follow Section 4 of the main prompt (`intent_kind`, `step_type`, evidence, unresolved).

        **intent_kind** (exactly one per behaviour intent):
        {taxonomy_bullets(INTENT_KIND_ORDERED)}

        **model_confidence** (model field only — backend merges into final confidence):
        - Allowed: `{mc}`

        **visible_status**
        {taxonomy_bullets(VISIBLE_STATUS_ORDERED)}

        **evidence_refs[].evidence_type**
        {taxonomy_bullets(EVIDENCE_TYPE_ORDERED)}

        **local_action_sequence_templates.steps[].step_type**
        {taxonomy_bullets(STEP_TYPE_ORDERED)}

        **Option reference:** `selection_options[].option_ref_type` must be `element` OR `action`.
        Provide the matching `option_element_id` OR `option_action_id` (the other MUST be null).

        **unresolved_screen_groups.reason_code** — prompt §4.6:
        {llm_reason_block}

        Additional codes the server may record when rejecting a draft (do not invent unless instructed):
        {srv_reason_block}

        Classification rubric (align with Sections 3–4 of the main joint prompt):
        - One main intent per form/search/confirmation group with a commit control; supporting inputs belong in that intent’s sequence, not as per-field `data_entry` intents.
        - Typing-only goal with no visible submit ⇒ `data_entry`.
        - Query + results affordance ⇒ `search`; filters/sort/narrowing a visible list ⇒ `filtering`.
        - Pick among sibling visible options (tabs/radios/expanded list items) ⇒ `selection`.
        - Menu / tab / link navigation ⇒ `navigation`.
        - Submit / save / place order / primary commit ⇒ `submission`.
        - Confirm / accept on an explicit confirmation surface ⇒ `confirmation`.
        - Cancel / back / close / dismiss without deleting data ⇒ `cancellation`.
        - Explicit delete/remove ⇒ `deletion`.
        - Change existing data ⇒ `editing`.
        - Start a new entity from empty state or primary “create” ⇒ `creation`.
        - Dismiss or act on visible feedback (OK / Got it) ⇒ `feedback_acknowledgement`.
        - Read-only passive blocks ⇒ usually `unresolved_screen_groups` with `passive_content_only`, not a behaviour intent.

        Principle reminders:
        - Output **IDs only** for actions/evidence/options (`primary_action_id`, `commit_action_id`, …).
        - Evidence rows are `evidence_type` + `source_id` only (no long rationale blobs).
        - Stay on the visible screen — no next-screen / backend outcome language in `intent_name`, `local_user_goal`, or steps.

        ── ID constraints ──
        When the user payload includes `allowed_group_ids` and per-group ID maps, every id you emit MUST appear there.
        Otherwise follow Section 5 consistency rules in the main prompt.
        """
    ).strip()
