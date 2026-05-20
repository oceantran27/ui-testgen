"""Stable experiment-scoped IDs for offline joint → compressed catalog."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

_ID_SAFE = re.compile(r"[^a-z0-9]+")


def _slug(raw: str) -> str:
    t = (raw or "").strip().lower()
    t = _ID_SAFE.sub("_", t).strip("_")
    return t or "x"


def new_experiment_run_id(app_id: str) -> str:
    """Run id: exp_fd_{app}_{YYYYMMDD}_{shortuniq}."""
    slug = _slug(app_id)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"exp_fd_{slug}_{day}_{uuid.uuid4().hex[:6]}"


class ExperimentIdFactory:
    """Prefix rules: expst_/expel_/expac_/expfb_/expgrp_/sbi_exp_ (see product plan)."""

    def __init__(self, app_id: str) -> None:
        self._app = _slug(app_id)
        self._sbi_n = 0

    def state_id(self, source_image_id: str, index: int) -> str:
        slug = _slug(source_image_id)
        return f"expst_{self._app}_{slug}_{index:03d}"

    def fallback_element_id(self, state_id: str, index: int) -> str:
        slug = _slug(state_id)
        return f"expel_{slug}_{index:03d}"

    def fallback_action_id(self, state_id: str, index: int) -> str:
        slug = _slug(state_id)
        return f"expac_{slug}_{index:03d}"

    def fallback_feedback_id(self, state_id: str, index: int) -> str:
        slug = _slug(state_id)
        return f"expfb_{slug}_{index:03d}"

    def fallback_group_id(self, state_id: str, index: int) -> str:
        slug = _slug(state_id)
        return f"expgrp_{slug}_{index:03d}"

    def screen_intent_id(self) -> str:
        self._sbi_n += 1
        return f"sbi_exp_{self._app}_{self._sbi_n:06d}"


__all__ = ["ExperimentIdFactory", "new_experiment_run_id"]
