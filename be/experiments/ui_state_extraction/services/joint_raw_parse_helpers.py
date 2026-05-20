"""Shared parsing helpers for JointScreenUnderstanding-shaped raw dict fragments."""

from __future__ import annotations

from typing import Any


def safe_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def safe_list(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return []


def as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]
