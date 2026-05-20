"""Structural validation + metrics for joint vision output (post-schema, typically post-ID-prefix)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Set

from app.constants.screen_intent_taxonomy import ELEMENT_SCOPED_EVIDENCE_TYPES


@dataclass
class JointUnderstandingValidationReport:
    duplicate_element_ids: int = 0
    duplicate_action_ids: int = 0
    duplicate_feedback_ids: int = 0
    duplicate_group_ids: int = 0
    orphan_elements_not_in_any_group: int = 0
    orphan_actions_not_in_any_group: int = 0
    orphan_feedback_not_in_any_group: int = 0
    multi_group_elements: int = 0
    multi_group_actions: int = 0
    multi_group_feedback: int = 0
    invalid_intent_group_refs: int = 0
    invalid_intent_primary_action_refs: int = 0
    invalid_intent_commit_action_refs: int = 0
    invalid_intent_secondary_action_refs: int = 0
    invalid_intent_required_input_refs: int = 0
    invalid_intent_evidence_refs: int = 0
    invalid_intent_selection_option_refs: int = 0
    invalid_intent_sequence_refs: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def invalid_ref_total(self) -> int:
        return (
            self.invalid_intent_group_refs
            + self.invalid_intent_primary_action_refs
            + self.invalid_intent_commit_action_refs
            + self.invalid_intent_secondary_action_refs
            + self.invalid_intent_required_input_refs
            + self.invalid_intent_evidence_refs
            + self.invalid_intent_selection_option_refs
            + self.invalid_intent_sequence_refs
        )

    def joint_validation_pass_rate(self, intent_count: int, unresolved_count: int) -> float:
        """Soft rate: 1.0 when no invalid refs; scales down by invalid refs."""
        denom = max(1, intent_count + unresolved_count)
        return max(0.0, 1.0 - (self.invalid_ref_total / denom))


def _count_duplicates(ids: List[str]) -> int:
    seen: Set[str] = set()
    dup = 0
    for i in ids:
        if i in seen:
            dup += 1
        else:
            seen.add(i)
    return dup


def validate_joint_screen_understanding_structured(
    state_row: Mapping[str, Any],
    intent_payload: Mapping[str, Any],
    *,
    strict_single_group_membership_warnings_only: bool = True,
) -> JointUnderstandingValidationReport:
    """
    Validates prefixed ``state_row`` (catalog dict) + raw intent payload dict (draft IDs already prefixed).
    Membership overlap violations increment counters / warnings only (do not raise).
    """
    rep = JointUnderstandingValidationReport()

    els = list(state_row.get("visible_elements") or [])
    acts = list(state_row.get("available_actions") or [])
    fbs = list(state_row.get("visible_feedback") or [])
    groups = list(state_row.get("interaction_groups") or [])

    el_ids = [str(e["element_id"]) for e in els if e.get("element_id")]
    ac_ids = [str(a["action_id"]) for a in acts if a.get("action_id")]
    fb_ids = [str(f["feedback_id"]) for f in fbs if f.get("feedback_id")]
    rep.duplicate_element_ids = _count_duplicates(el_ids)
    rep.duplicate_action_ids = _count_duplicates(ac_ids)
    rep.duplicate_feedback_ids = _count_duplicates(fb_ids)

    gid_list = [str(g["group_id"]) for g in groups if g.get("group_id")]
    rep.duplicate_group_ids = _count_duplicates(gid_list)

    el_set = set(el_ids)
    ac_set = set(ac_ids)
    fb_set = set(fb_ids)

    el_memberships: Dict[str, int] = {i: 0 for i in el_set}
    ac_memberships: Dict[str, int] = {i: 0 for i in ac_set}
    fb_memberships: Dict[str, int] = {i: 0 for i in fb_set}

    groups_by_id: Dict[str, Any] = {}
    for g in groups:
        gid = str(g.get("group_id") or "")
        if not gid:
            continue
        groups_by_id[gid] = g
        ge = set(str(x) for x in (g.get("element_ids") or []))
        ga = set(str(x) for x in (g.get("action_ids") or []))
        gf = set(str(x) for x in (g.get("feedback_ids") or []))
        for eid in ge:
            el_memberships[eid] = el_memberships.get(eid, 0) + 1
        for aid in ga:
            ac_memberships[aid] = ac_memberships.get(aid, 0) + 1
        for fid in gf:
            fb_memberships[fid] = fb_memberships.get(fid, 0) + 1

    rep.orphan_elements_not_in_any_group = sum(1 for i in el_set if el_memberships.get(i, 0) == 0)
    rep.orphan_actions_not_in_any_group = sum(1 for i in ac_set if ac_memberships.get(i, 0) == 0)
    rep.orphan_feedback_not_in_any_group = sum(1 for i in fb_set if fb_memberships.get(i, 0) == 0)
    rep.multi_group_elements = sum(1 for i in el_set if el_memberships.get(i, 0) > 1)
    rep.multi_group_actions = sum(1 for i in ac_set if ac_memberships.get(i, 0) > 1)
    rep.multi_group_feedback = sum(1 for i in fb_set if fb_memberships.get(i, 0) > 1)

    if strict_single_group_membership_warnings_only and (
        rep.multi_group_elements or rep.multi_group_actions or rep.multi_group_feedback
    ):
        rep.warnings.append(
            "interaction_groups_overlap_controls_seen_joint_validator_counts_multi_membership_fields_only"
        )

    intents = list(intent_payload.get("screen_behaviour_intents") or [])

    for draft in intents:
        gid = str(draft.get("source_group_id") or "")
        g = groups_by_id.get(gid)
        if not g:
            rep.invalid_intent_group_refs += 1
            continue
        ge = set(str(x) for x in (g.get("element_ids") or []))
        ga = set(str(x) for x in (g.get("action_ids") or []))
        gf = set(str(x) for x in (g.get("feedback_ids") or []))

        pa = draft.get("primary_action_id")
        if pa and str(pa) not in ga:
            rep.invalid_intent_primary_action_refs += 1
        ca = draft.get("commit_action_id")
        if ca and str(ca) not in ga:
            rep.invalid_intent_commit_action_refs += 1
        for sid in draft.get("secondary_action_ids") or []:
            if str(sid) not in ga:
                rep.invalid_intent_secondary_action_refs += 1
        for rid in draft.get("required_input_element_ids") or []:
            if str(rid) not in ge:
                rep.invalid_intent_required_input_refs += 1

        for ref in draft.get("evidence_refs") or []:
            et = str(ref.get("evidence_type") or "")
            sid = str(ref.get("source_id") or "")
            ok = False
            if et == "group_evidence" and sid == str(g.get("group_id")):
                ok = True
            elif et in ELEMENT_SCOPED_EVIDENCE_TYPES and sid in ge:
                ok = True
            elif et == "action_text" and sid in ga:
                ok = True
            elif et == "feedback_text" and sid in gf:
                ok = True
            if not ok:
                rep.invalid_intent_evidence_refs += 1

        for opt in draft.get("selection_options") or []:
            rt = str(opt.get("option_ref_type") or "")
            if rt == "element":
                oe = opt.get("option_element_id")
                if not oe or str(oe) not in ge:
                    rep.invalid_intent_selection_option_refs += 1
            elif rt == "action":
                oa = opt.get("option_action_id")
                if not oa or str(oa) not in ga:
                    rep.invalid_intent_selection_option_refs += 1

        for tmpl in draft.get("local_action_sequence_templates") or []:
            for step in tmpl.get("steps") or []:
                sai = step.get("source_action_id")
                sei = step.get("source_element_id")
                if sai and str(sai) not in ga:
                    rep.invalid_intent_sequence_refs += 1
                if sei and str(sei) not in ge:
                    rep.invalid_intent_sequence_refs += 1

    return rep
