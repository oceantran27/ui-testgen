"""Write `progress.json` under each state-graph run `out_dir` for polling endpoints."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter

from app.schemas.state_graph import (
    PIPELINE_PHASE_LABELS,
    PIPELINE_PHASE_ORDER,
    PipelinePhaseId,
    PipelinePhaseProgress,
    PipelinePhaseTiming,
    PipelineRunTiming,
    RunStatus,
)

PROGRESS_FILENAME = "progress.json"

_progress_adapter = TypeAdapter(list[PipelinePhaseProgress])


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_json_write(path: str, payload: dict[str, Any]) -> None:
    d = os.path.dirname(path)
    base = os.path.basename(path)
    tmp = os.path.join(d, f".{base}.tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _empty_phase_models() -> list[PipelinePhaseProgress]:
    rows: list[PipelinePhaseProgress] = []
    for pid in PIPELINE_PHASE_ORDER:
        rows.append(PipelinePhaseProgress(id=pid, label=PIPELINE_PHASE_LABELS[pid], status="pending"))
    return rows


def _persist(
    *,
    input_id: str,
    out_dir: str,
    run_status: RunStatus,
    current_phase: PipelinePhaseId | None,
    phases: list[PipelinePhaseProgress],
    error: str | None = None,
    timing: PipelineRunTiming | None = None,
) -> None:
    payload: dict[str, Any] = {
        "input_id": input_id,
        "status": run_status,
        "current_phase": current_phase,
        "error": error,
        "phases": [p.model_dump(mode="json") for p in phases],
    }
    if timing is not None:
        payload["timing"] = timing.model_dump(mode="json")
    path = os.path.join(out_dir, PROGRESS_FILENAME)
    _atomic_json_write(path, payload)


@dataclass
class StateGraphProgressTracker:
    input_id: str
    out_dir: str
    phases: list[PipelinePhaseProgress]
    run_wall_start: float

    def __init__(self, *, input_id: str, out_dir: str) -> None:
        self.input_id = input_id
        self.out_dir = out_dir
        self.phases = _empty_phase_models()
        self.run_wall_start = time.perf_counter()
        os.makedirs(out_dir, exist_ok=True)

    def _phase_index(self, pid: PipelinePhaseId) -> int:
        return PIPELINE_PHASE_ORDER.index(pid)

    def start_run_begin_dedupe(self) -> None:
        dedupe = self.phases[self._phase_index("dedupe")]
        dedupe.status = "running"
        dedupe.started_at_iso = _iso_now()
        _persist(
            input_id=self.input_id,
            out_dir=self.out_dir,
            run_status="running",
            current_phase="dedupe",
            phases=self.phases,
        )

    def advance_after_phase(self, finished: PipelinePhaseId, duration_ms: int) -> None:
        row = self.phases[self._phase_index(finished)]
        row.status = "completed"
        row.ended_at_iso = _iso_now()
        row.duration_ms = duration_ms

        cur_idx = self._phase_index(finished)
        next_idx = cur_idx + 1

        next_phase_id: PipelinePhaseId | None
        if next_idx < len(PIPELINE_PHASE_ORDER):
            next_phase_id = PIPELINE_PHASE_ORDER[next_idx]
            nx = self.phases[next_idx]
            nx.status = "running"
            nx.started_at_iso = row.ended_at_iso
        else:
            next_phase_id = None

        _persist(
            input_id=self.input_id,
            out_dir=self.out_dir,
            run_status="running",
            current_phase=next_phase_id,
            phases=self.phases,
        )

    def finalize_success(self, timings: list[PipelinePhaseTiming]) -> PipelineRunTiming:
        wall_clock_ms = int((time.perf_counter() - self.run_wall_start) * 1000)
        timing = PipelineRunTiming(phases=list(timings), wall_clock_ms=wall_clock_ms)
        _persist(
            input_id=self.input_id,
            out_dir=self.out_dir,
            run_status="completed",
            current_phase=None,
            phases=self.phases,
            error=None,
            timing=timing,
        )
        return timing

    def fail(self, message: str, at_phase: PipelinePhaseId | None = None) -> None:
        # Pick the phase that was running when we failed
        failing: PipelinePhaseId | None = at_phase
        if failing is None:
            for p in reversed(self.phases):
                if p.status == "running":
                    failing = p.id
                    break
            failing = failing or PIPELINE_PHASE_ORDER[0]

        rp = self.phases[self._phase_index(failing)]
        if rp.status == "running":
            rp.status = "failed"
            rp.ended_at_iso = _iso_now()
            rp.duration_ms = max(
                0,
                min(
                    int((time.perf_counter() - self.run_wall_start) * 1000),
                    86400_000,
                ),
            )

        fi = self._phase_index(failing)
        for p in self.phases[fi + 1 :]:
            if p.status == "pending":
                p.status = "pending"

        _persist(
            input_id=self.input_id,
            out_dir=self.out_dir,
            run_status="failed",
            current_phase=failing,
            phases=self.phases,
            error=message,
        )


def read_progress_snapshot(out_dir: str) -> dict[str, Any] | None:
    path = os.path.join(out_dir, PROGRESS_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None


def phases_from_snapshot(d: dict[str, Any]) -> list[PipelinePhaseProgress]:
    return _progress_adapter.validate_python(d.get("phases") or [])
