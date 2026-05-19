"""Shared text list matching for evaluation (spec §8)."""

from __future__ import annotations

from experiments.ui_state_extraction.services.text_normalization_service import (
    normalize_for_match,
    text_matches,
)


def normalize_text_list(strings: list[str]) -> list[str]:
    out: list[str] = []
    for s in strings:
        t = str(s).strip()
        if not t:
            continue
        n = normalize_for_match(t)
        if n:
            out.append(n)
    return out


def text_anchor_match(pred_anchors: list[str], gt_anchors: list[str]) -> bool:
    """True if any normalized pair matches per §8.2 (equality or mutual contains)."""
    if not pred_anchors or not gt_anchors:
        return False
    for p in pred_anchors:
        for g in gt_anchors:
            if text_matches(p, g):
                return True
    return False


def longest_anchor_overlap_score(pred_anchors: list[str], gt_anchors: list[str]) -> int:
    """Heuristic tie-break: max combined length of matching pair."""
    best = 0
    for p in pred_anchors:
        for g in gt_anchors:
            if text_matches(p, g):
                np = normalize_for_match(p)
                ng = normalize_for_match(g)
                best = max(best, len(np) + len(ng))
    return best
