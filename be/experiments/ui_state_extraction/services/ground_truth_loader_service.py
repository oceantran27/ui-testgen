"""Load and validate temp ground truth JSON for module 3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import TempGroundTruthDocument


def load_temp_ground_truth(path: Path) -> tuple[TempGroundTruthDocument | None, str | None]:
    """Returns (document, None) on success or (None, error_message)."""
    try:
        with open(path, encoding="utf-8") as f:
            payload: dict[str, Any] = json.load(f)
        return TempGroundTruthDocument.model_validate(payload), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    except ValidationError as exc:
        return None, str(exc)
