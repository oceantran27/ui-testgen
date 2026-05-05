from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MatchResult:
    """One-to-one greedy match between ground-truth strings and model-output strings."""

    matched_pairs: list[tuple[int, int, float]]  # (gt_index, mo_index, similarity)
    fail: list[str]  # GT items with no match
    excess: list[str]  # MO items with no match
    tp: int  # number of successful matches (same as len(matched_pairs) when all >= threshold)

    @property
    def true_positives(self) -> int:
        return self.tp


def greedy_cosine_match(
    gt: list[str],
    mo: list[str],
    gt_emb: np.ndarray,
    mo_emb: np.ndarray,
    threshold: float,
) -> MatchResult:
    """
    Build all pairwise cosines (assumed L2-normalized rows so sim = G @ M^T),
    sort pairs by score descending, greedily take disjoint pairs with sim >= threshold.
    """
    if not gt and not mo:
        return MatchResult(matched_pairs=[], fail=[], excess=[], tp=0)
    n_g, n_m = len(gt), len(mo)
    if n_g == 0:
        return MatchResult(matched_pairs=[], fail=[], excess=list(mo), tp=0)
    if n_m == 0:
        return MatchResult(matched_pairs=[], fail=list(gt), excess=[], tp=0)

    sim = np.matmul(gt_emb, mo_emb.T)  # (n_g, n_m)
    pairs: list[tuple[float, int, int]] = []
    for i in range(n_g):
        for j in range(n_m):
            pairs.append((float(sim[i, j]), i, j))
    pairs.sort(key=lambda t: t[0], reverse=True)

    used_g: set[int] = set()
    used_m: set[int] = set()
    matched: list[tuple[int, int, float]] = []
    for s, i, j in pairs:
        if s < threshold:
            break
        if i in used_g or j in used_m:
            continue
        used_g.add(i)
        used_m.add(j)
        matched.append((i, j, s))

    fail = [gt[i] for i in range(n_g) if i not in used_g]
    excess = [mo[j] for j in range(n_m) if j not in used_m]
    return MatchResult(matched_pairs=matched, fail=fail, excess=excess, tp=len(matched))
