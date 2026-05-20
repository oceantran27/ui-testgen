"""Build ``GroundTruthState`` rows + ``catalog_state_id`` → ``gt_state_id`` registry."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthState, VisibleEvidenceBuckets


def _slug_fragment(label: str, fallback: str) -> str:
    s = str(label or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    out = s.strip("_")
    return out or re.sub(r"[^a-z0-9]+", "_", str(fallback).lower()).strip("_") or "screen"


def _text_from_field(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, list):
        parts = [str(x).strip() for x in item if str(x).strip()]
        return " ".join(parts)
    if isinstance(item, dict):
        parts: List[str] = []
        if item.get("text"):
            parts.extend([str(t).strip() for t in list(item.get("text") or []) if str(t).strip()])
        return " ".join(parts) if parts else str(item.get("label") or "").strip()
    return str(item).strip()


def _bucket_visible_evidence(card: Dict[str, Any]) -> VisibleEvidenceBuckets:
    headings: List[str] = []
    texts: List[str] = []
    for el in card.get("visible_elements") or []:
        if not isinstance(el, dict):
            continue
        et = str(el.get("element_type") or el.get("role_hint") or "").lower()
        evid = str(el.get("evidence_type") or "").lower()
        label = _text_from_field(el.get("text"))
        if not label and el.get("anchor_texts"):
            label = _text_from_field(el.get("anchor_texts"))
        if not label:
            continue
        if evid in ("heading", "title") or et in ("heading", "title", "h1", "header"):
            headings.append(label)
        else:
            texts.append(label)

    action_labels: List[str] = []
    for act in card.get("available_actions") or []:
        if not isinstance(act, dict):
            continue
        t = _text_from_field(act.get("text"))
        if t:
            action_labels.append(t)

    feedback_labels: List[str] = []
    for fb in card.get("visible_feedback") or []:
        if not isinstance(fb, dict):
            continue
        t = _text_from_field(fb.get("text"))
        if t:
            feedback_labels.append(t)

    return VisibleEvidenceBuckets(
        headings=headings,
        texts=texts,
        actions=action_labels,
        feedback=feedback_labels,
    )


def build_catalog_state_index(cards: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for c in cards:
        if not isinstance(c, dict):
            continue
        sid = str(c.get("state_id") or "").strip()
        if sid:
            out[sid] = c
    return out


def build_states_from_compressed_catalog(
    app_id: str,
    compressed_catalog_package: Dict[str, Any],
) -> Tuple[List[GroundTruthState], Dict[str, str], Dict[str, Dict[str, Any]]]:
    trace = compressed_catalog_package.get("trace_index") or {}
    cards = [c for c in (compressed_catalog_package.get("compressed_catalog") or []) if isinstance(c, dict)]
    catalog_to_gt: Dict[str, str] = {}
    states: List[GroundTruthState] = []
    for idx, card in enumerate(cards):
        cid = str(card.get("state_id") or "").strip()
        if not cid:
            continue
        slug_base = _slug_fragment(str(card.get("screen_purpose") or ""), cid)
        gt_state_id = f"gt_s_{app_id}_{slug_base}_{idx + 1:03d}"
        catalog_to_gt[cid] = gt_state_id
        tax = dict(card.get("taxonomy") or {})
        src_img = ""
        tentry = trace.get(cid)
        if isinstance(tentry, dict):
            src_img = str(tentry.get("source_image_id") or "")
        elif hasattr(tentry, "source_image_id"):
            src_img = str(getattr(tentry, "source_image_id", "") or "")

        ev = _bucket_visible_evidence(card)
        states.append(
            GroundTruthState(
                gt_state_id=gt_state_id,
                catalog_state_id=cid,
                source_image_id=src_img,
                screen_name=str(card.get("screen_purpose") or ""),
                screen_type=str(tax.get("screen_type") or ""),
                outcome_state_type=str(tax.get("outcome_state_type") or ""),
                taxonomy=tax,
                visible_evidence=ev,
            )
        )

    index = build_catalog_state_index(cards)
    return states, catalog_to_gt, index
