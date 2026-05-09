"""Shared detection of transient Gemini overload (503 UNAVAILABLE)."""

from __future__ import annotations

GEMINI_503_RETRY_SLEEP_SEC = 2.0


def is_gemini_503_unavailable(exc: BaseException) -> bool:
    """True for transient model overload (caller may sleep and retry until success)."""
    if getattr(exc, "status_code", None) == 503:
        return True
    msg = str(exc).upper()
    return "503" in msg and "UNAVAILABLE" in msg
