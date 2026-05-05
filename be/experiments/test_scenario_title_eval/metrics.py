from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Prf1:
    precision: float
    recall: float
    f1: float


def per_image_prf1(tp: int, num_gt: int, num_mo: float) -> Prf1:
    """
    Precision = TP / |MO|, Recall = TP / |GT|.
    If |MO| = 0: precision 0.0. If |GT| = 0: recall 0.0. F1 from P and R; if P+R=0, F1=0.
    """
    p = (tp / num_mo) if num_mo > 0 else 0.0
    r = (tp / num_gt) if num_gt > 0 else 0.0
    if p + r <= 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * p * r / (p + r)
    return Prf1(precision=p, recall=r, f1=f1)
