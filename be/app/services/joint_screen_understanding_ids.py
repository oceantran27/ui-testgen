"""Apply canonical ``state_id_`` prefix to Phase-B intent drafts (matches Agent 1 ID convention)."""

from __future__ import annotations

from typing import Optional

from app.model_providers.schemas import (
    ActionSequenceStepDraftA2,
    ActionSequenceTemplateDraftA2,
    EvidenceRefDraftA2,
    ScreenBehaviourIntentDraftA2,
    ScreenIntentExtractionV2Result,
    SelectionOptionDraftA2,
    UnresolvedScreenGroupA2,
)


def prefix_under(state_id: str, raw_id: Optional[str]) -> Optional[str]:
    if raw_id is None:
        return None
    s = str(raw_id).strip()
    if not s:
        return s
    pre = f"{state_id}_"
    return s if s.startswith(pre) else pre + s


def prefix_screen_intent_payload(state_id: str, p: ScreenIntentExtractionV2Result) -> ScreenIntentExtractionV2Result:
    new_intents: list[ScreenBehaviourIntentDraftA2] = []
    for d in p.screen_behaviour_intents:
        sec = [prefix_under(state_id, x) or x for x in (d.secondary_action_ids or [])]
        sec = [x for x in sec if x]
        sel_opts: list[SelectionOptionDraftA2] = []
        for o in d.selection_options:
            sel_opts.append(
                SelectionOptionDraftA2(
                    option_ref_type=o.option_ref_type,
                    option_element_id=prefix_under(state_id, o.option_element_id),
                    option_action_id=prefix_under(state_id, o.option_action_id),
                    visible_status=o.visible_status,
                )
            )
        seq_templates: list[ActionSequenceTemplateDraftA2] = []
        for t in d.local_action_sequence_templates:
            steps_out: list[ActionSequenceStepDraftA2] = []
            for st in t.steps:
                steps_out.append(
                    ActionSequenceStepDraftA2(
                        step_type=st.step_type,
                        source_action_id=prefix_under(state_id, st.source_action_id),
                        source_element_id=prefix_under(state_id, st.source_element_id),
                    )
                )
            seq_templates.append(
                ActionSequenceTemplateDraftA2(
                    sequence_name=t.sequence_name,
                    steps=steps_out,
                    outcome_prediction_allowed=t.outcome_prediction_allowed,
                )
            )
        ev_refs = [
            EvidenceRefDraftA2(evidence_type=r.evidence_type, source_id=prefix_under(state_id, r.source_id) or r.source_id)
            for r in d.evidence_refs
        ]
        req_inputs = [prefix_under(state_id, x) or x for x in d.required_input_element_ids]

        new_intents.append(
            ScreenBehaviourIntentDraftA2(
                source_group_id=prefix_under(state_id, d.source_group_id) or d.source_group_id,
                intent_kind=d.intent_kind,
                intent_name=d.intent_name,
                local_user_goal=d.local_user_goal,
                primary_action_id=prefix_under(state_id, d.primary_action_id),
                commit_action_id=prefix_under(state_id, d.commit_action_id),
                secondary_action_ids=sec,
                selection_options=sel_opts,
                local_action_sequence_templates=seq_templates,
                required_input_element_ids=req_inputs,
                evidence_refs=ev_refs,
                model_confidence=d.model_confidence,
            )
        )

    new_unres: list[UnresolvedScreenGroupA2] = []
    for u in p.unresolved_screen_groups:
        new_unres.append(
            UnresolvedScreenGroupA2(
                group_id=prefix_under(state_id, u.group_id) or u.group_id,
                reason_code=u.reason_code,
                details=u.details,
            )
        )

    return ScreenIntentExtractionV2Result(
        screen_behaviour_intents=new_intents,
        unresolved_screen_groups=new_unres,
    )
