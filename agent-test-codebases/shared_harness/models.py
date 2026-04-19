from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StageRunMetrics:
    stage_name: str
    provider: str
    model: str
    temperature: float
    requested_temperature: float
    attempts: int
    elapsed_ms: int
    prompt_token_estimate: int
    output_token_estimate: int
    total_token_estimate: int
    cost_usd_estimate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageRunResult:
    raw_text: str
    parsed_json: dict[str, Any]
    validated_json: dict[str, Any]
    metrics: StageRunMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "parsed_json": self.parsed_json,
            "validated_json": self.validated_json,
            "metrics": self.metrics.to_dict(),
        }
