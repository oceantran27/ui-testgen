"""Coverage ratios and simple aggregates."""

from __future__ import annotations


def coverage_ratio(matched: int, n_total: int) -> float:
    if n_total <= 0:
        return 0.0
    return matched / n_total


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def pstdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return var**0.5
