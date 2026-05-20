"""Build ``GroundTruthAction`` rows from catalogue cards (intents + bare actions)."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple


def _joined_text_from_action_dict(act: Dict[str, Any]) -> str:
    texts = act.get("text")
    if isinstance(texts, list) and texts:
        parts = [str(t).strip() for t in texts if str(t).strip()]
        return " ".join(parts)
    return ""


def build_actions_for_catalog(
    app_id: str,
    compressed_cards: Iterable[Dict[str, Any]],
    catalog_to_gt: Dict[str, str],
) -> List:
    """Return list of GroundTruthAction (import lazily avoids cycles)."""

    from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthAction

    actions: List[GroundTruthAction] = []
    seen: Set[str] = set()
    ctr = 0

    def next_id(prefix: str) -> str:
        nonlocal ctr
        ctr += 1
        return f"gt_a_{app_id}_{prefix}_{ctr:03d}"

    for card in compressed_cards:
        if not isinstance(card, dict):
            continue
        catalog_sid = str(card.get("state_id") or "").strip()
        if not catalog_sid or catalog_sid not in catalog_to_gt:
            continue
        gt_sid = catalog_to_gt[catalog_sid]

        queued: List[Tuple[Dict[str, Any], str, str | None]] = []
        for intent in card.get("screen_intents") or []:
            if not isinstance(intent, dict):
                continue
            iid = str(intent.get("intent_id") or "") or None
            for key in ("commit_action", "primary_action"):
                act = intent.get(key)
                if isinstance(act, dict):
                    queued.append((act, "intent_embedded", iid))
            for sec in intent.get("secondary_actions") or []:
                if isinstance(sec, dict):
                    queued.append((sec, "intent_embedded", iid))

        for act in card.get("available_actions") or []:
            if isinstance(act, dict):
                queued.append((act, "available_actions", None))

        for act, _src, intent_id in queued:
            aid = str(act.get("action_id") or "").strip()
            text = _joined_text_from_action_dict(act)
            atype = str(act.get("action_type") or "")
            dedupe_key = f"{gt_sid}::{aid or text}::{atype}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            actions.append(
                GroundTruthAction(
                    gt_action_id=next_id(_slug_action_prefix(text, aid)),
                    system_action_id=aid,
                    source_state_gt_id=gt_sid,
                    action_text=text,
                    action_type=atype,
                    intent_id=intent_id,
                )
            )

    return actions


def _slug_action_prefix(text: str, action_id: str) -> str:
    base = (text or action_id or "action").lower()
    out = "".join(ch if ch.isalnum() else "_" for ch in base)
    return out.strip("_")[:40] or "action"
