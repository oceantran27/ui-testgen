"""Shared UI state normalization, ID prefixing, and DB persistence (Agent 1 / joint Phase A)."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.ui_screen_taxonomy import normalize_screen_type
from app.db.models.image import Image
from app.db.models.ui_element import UIElement
from app.db.models.ui_state import UIState
from app.model_providers.schemas import (
    GroupEvidenceA1V2,
    InteractionGroupA1V2,
    UIActionA1V2,
    UIFeedbackA1V2,
    UIElementA1V2,
    UIStateExtractionV2Result,
)


def sanitize_filename_for_state_id(name: str, max_len: int = 64) -> str:
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", base)
    base = base.strip("._") or "image"
    return base[:max_len]


def generate_state_id_for_image(image: Image) -> str:
    label = sanitize_filename_for_state_id(image.original_filename or image.id)
    return f"st_{uuid.uuid4().hex[:12]}_{label}"


def confidence_from_extraction(extraction_status: str, quality: Any) -> float:
    base = {"success": 0.88, "partial": 0.62, "failed": 0.05}.get(extraction_status, 0.5)
    if quality is None:
        return round(base, 3)
    vr = getattr(quality, "visual_readability", "") or ""
    ec = getattr(quality, "extraction_completeness", "") or ""
    if vr == "high" and ec == "complete":
        base = min(1.0, base + 0.08)
    elif vr == "low" or ec == "poor":
        base = max(0.05, base - 0.25)
    return round(base, 3)


def confidence_label(conf: float) -> str:
    if conf >= 0.75:
        return "high"
    if conf >= 0.5:
        return "medium"
    return "low"


def generate_state_signature(
    page_type: str,
    elements: List[UIElementA1V2],
    actions: List[UIActionA1V2],
    feedback_list: List[UIFeedbackA1V2],
) -> str:
    inputs: List[str] = []
    action_labels: List[str] = []
    fb_type = "none"

    for el in elements:
        if el.element_type in ("input", "textarea", "checkbox", "radio", "select", "switch", "date_picker"):
            t = " ".join(el.text) if el.text else ""
            if t:
                inputs.append(t[:20])

    for act in actions:
        t = " ".join(act.text) if act.text else ""
        if t:
            action_labels.append(t[:20])

    if feedback_list:
        fb_type = feedback_list[0].feedback_type

    return (
        f"{page_type}|inputs:{','.join(inputs[:5]) or 'none'}|actions:"
        f"{','.join(action_labels[:5]) or 'none'}|feedback:{fb_type}"
    )


def flags_from_elements(
    elements: List[UIElementA1V2],
    actions: List[UIActionA1V2],
    feedback_list: List[UIFeedbackA1V2],
    presentation_scope: str,
) -> tuple[bool, bool, bool, bool]:
    has_form = any(
        el.element_type in ("input", "textarea", "select", "checkbox", "radio")
        for el in elements
    ) or any(act.action_type == "submit" for act in actions)

    has_table = any(el.element_type == "table" for el in elements)
    overlay_regions = frozenset({"dialog", "drawer", "popover", "toast", "overlay"})
    has_modal = presentation_scope in ("modal", "drawer", "popover") or any(
        el.visual_region in overlay_regions for el in elements
    ) or any(ac.visual_region in overlay_regions for ac in actions) or any(
        fb.visual_region in overlay_regions for fb in feedback_list
    )
    has_feedback = len(feedback_list) > 0
    return has_form, has_table, has_modal, has_feedback


def ensure_fallback_interaction_groups(result_data: UIStateExtractionV2Result) -> None:
    if not result_data.interaction_groups and (
        result_data.visible_elements or result_data.available_actions or result_data.visible_feedback
    ):
        fallback_group = InteractionGroupA1V2(
            group_id="ig_fallback",
            group_type="content_section",
            group_label=f"Screen {result_data.screen_purpose}",
            element_ids=[el.element_id for el in result_data.visible_elements],
            action_ids=[ac.action_id for ac in result_data.available_actions],
            feedback_ids=[fb.feedback_id for fb in result_data.visible_feedback],
            primary_action_id=(
                result_data.available_actions[0].action_id if result_data.available_actions else None
            ),
            group_evidence=[
                GroupEvidenceA1V2(
                    evidence_type="explicit_container",
                    description="auto-generated fallback group covering full screen evidence",
                )
            ],
            group_confidence="low",
        )
        result_data.interaction_groups = [fallback_group]


def prefix_ui_state_ids(state_id: str, result_data: UIStateExtractionV2Result) -> None:
    for el in result_data.visible_elements:
        el.element_id = f"{state_id}_{el.element_id}"
    for ac in result_data.available_actions:
        ac.action_id = f"{state_id}_{ac.action_id}"
    for fb in result_data.visible_feedback:
        fb.feedback_id = f"{state_id}_{fb.feedback_id}"

    for ig in result_data.interaction_groups:
        ig.group_id = f"{state_id}_{ig.group_id}"
        ig.element_ids = [f"{state_id}_{eid}" for eid in ig.element_ids]
        ig.action_ids = [f"{state_id}_{aid}" for aid in ig.action_ids]
        ig.feedback_ids = [f"{state_id}_{fid}" for fid in ig.feedback_ids]
        if ig.primary_action_id:
            ig.primary_action_id = f"{state_id}_{ig.primary_action_id}"


def persist_ui_state_from_v2_result(
    db: AsyncSession,
    run_id: str,
    img: Image,
    result_data: UIStateExtractionV2Result,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """
    Mutates ``result_data`` (fallback groups + prefixed IDs). Adds UIState/UIElement rows (no commit).
    Returns (state_catalog_row, per_image_counts).
    """
    canonical_screen_type = normalize_screen_type(result_data.screen_type)

    extraction_status = (
        "success" if (result_data.visible_elements or result_data.available_actions) else "partial"
    )
    state_quality_payload: Dict[str, Any] = {}
    if not result_data.screen_purpose or result_data.screen_purpose == "null":
        extraction_status = "failed"

    state_id = generate_state_id_for_image(img)
    conf = confidence_from_extraction(extraction_status, None)
    conf_lbl = confidence_label(conf)

    has_form, has_table, has_modal, has_feedback = flags_from_elements(
        result_data.visible_elements,
        result_data.available_actions,
        result_data.visible_feedback,
        result_data.presentation_scope,
    )

    signature = generate_state_signature(
        canonical_screen_type,
        result_data.visible_elements,
        result_data.available_actions,
        result_data.visible_feedback,
    )

    db_state = UIState(
        id=state_id,
        run_id=run_id,
        image_id=img.id,
        page_type=canonical_screen_type,
        screen_type=canonical_screen_type,
        presentation_scope=result_data.presentation_scope,
        outcome_state_type=result_data.outcome_state_type,
        screen_purpose=result_data.screen_purpose,
        domain=result_data.domain,
        state_summary=result_data.screen_purpose,
        state_signature=signature,
        confidence=conf,
        confidence_label=conf_lbl,
        has_form=has_form,
        has_table=has_table,
        has_modal=has_modal,
        has_feedback=has_feedback,
        state_quality=state_quality_payload,
        extraction_status=extraction_status,
    )
    db.add(db_state)

    ensure_fallback_interaction_groups(result_data)
    prefix_ui_state_ids(state_id, result_data)

    db_state.interaction_groups_json = [ig.model_dump() for ig in result_data.interaction_groups]

    n_el = n_act = n_fb = 0
    for el_data in result_data.visible_elements:
        db.add(
            UIElement(
                id=el_data.element_id,
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type=el_data.element_type,
                text=el_data.text,
                actionable=False,
                is_feedback=False,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
        )
        n_el += 1

    for act_data in result_data.available_actions:
        db.add(
            UIElement(
                id=act_data.action_id,
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type="action",
                action_type=act_data.action_type,
                text=act_data.text,
                actionable=True,
                is_feedback=False,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
        )
        n_el += 1
        n_act += 1

    for fb_data in result_data.visible_feedback:
        db.add(
            UIElement(
                id=fb_data.feedback_id,
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type="feedback",
                feedback_type=fb_data.feedback_type,
                text=fb_data.text,
                actionable=False,
                is_feedback=True,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
        )
        n_el += 1
        n_fb += 1

    state_row: Dict[str, Any] = {
        "extraction_status": extraction_status,
        "state_id": state_id,
        "upload_order": img.upload_order,
        "source_image_id": img.id,
        "page_type": canonical_screen_type,
        "screen_type": canonical_screen_type,
        "presentation_scope": result_data.presentation_scope,
        "outcome_state_type": result_data.outcome_state_type,
        "screen_purpose": result_data.screen_purpose,
        "domain": result_data.domain,
        "state_summary": result_data.screen_purpose,
        "visible_texts": [],
        "visible_elements": [e.model_dump() for e in result_data.visible_elements],
        "available_actions": [a.model_dump() for a in result_data.available_actions],
        "visible_feedback": [f.model_dump() for f in result_data.visible_feedback],
        "interaction_groups": [ig.model_dump() for ig in result_data.interaction_groups],
        "state_quality": state_quality_payload,
    }
    counts = {
        "total_ui_elements": n_el,
        "total_actionable_elements": n_act,
        "total_feedback_elements": n_fb,
    }
    return state_row, counts
