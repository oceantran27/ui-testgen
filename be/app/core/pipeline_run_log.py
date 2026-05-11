"""
Optional dual-channel logging for pipeline experiments: short console, detailed files.

Activated by standalone harness via activate(). Nodes and model_adapter no-op when inactive.
"""
from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

_ctx: ContextVar[Optional["PipelineRunLogContext"]] = ContextVar(
    "pipeline_run_log_ctx", default=None
)


@dataclass
class PipelineRunLogContext:
    run_id: str
    log_dir: Path
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def next_raw_basename(self, prefix: str) -> str:
        with self._lock:
            self._seq += 1
            return f"{prefix}_{self._seq:04d}"


def is_active() -> bool:
    return _ctx.get() is not None


def activate(run_id: str, log_dir: Path) -> None:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "raw").mkdir(parents=True, exist_ok=True)
    _ctx.set(PipelineRunLogContext(run_id=run_id, log_dir=log_dir))


def deactivate() -> None:
    _ctx.set(None)


def _ctx_or_none() -> Optional[PipelineRunLogContext]:
    return _ctx.get()


def console_line(message: str) -> None:
    """Short progress line only (stdout)."""
    print(message, flush=True)


def console_warn(message: str) -> None:
    print(f"WARN: {message}", flush=True)


def console_err(message: str) -> None:
    print(f"ERROR: {message}", flush=True)


def _pipeline_log_path(ctx: PipelineRunLogContext) -> Path:
    return ctx.log_dir / "pipeline.log"


def _write_file_line(ctx: PipelineRunLogContext, line: str) -> None:
    path = _pipeline_log_path(ctx)
    ts = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{ts} {line}\n")


def file_detail(
    prefix: str,
    logic_lines: Sequence[str],
    *,
    raw: Any = None,
    raw_path: Optional[Path] = None,
    state_slice: Optional[Mapping[str, Any]] = None,
) -> None:
    """Append structured detail to pipeline.log; optional raw JSON sidecar or inline state_slice."""
    ctx = _ctx_or_none()
    if ctx is None:
        return
    lines = [f"[{prefix}] " + logic_lines[0]] if logic_lines else [f"[{prefix}]"]
    for extra in logic_lines[1:]:
        lines.append(f"    {extra}")
    block = "\n".join(lines)
    _write_file_line(ctx, block)
    if state_slice is not None:
        _write_file_line(
            ctx,
            f"[{prefix}] state_slice=\n{json.dumps(_json_safe(state_slice), indent=2, ensure_ascii=False)}",
        )
    if raw_path is not None:
        _write_file_line(ctx, f"[{prefix}] raw_file={raw_path}")
    if raw is not None:
        _write_file_line(
            ctx,
            f"[{prefix}] raw=\n{json.dumps(_json_safe(raw), indent=2, ensure_ascii=False)}",
        )


def write_raw_json(prefix: str, data: Any) -> Path:
    """Write full raw payload under log_dir/raw; return path. No console output."""
    ctx = _ctx_or_none()
    if ctx is None:
        raise RuntimeError("pipeline_run_log not active")
    name = f"{ctx.next_raw_basename(prefix)}.json"
    path = ctx.log_dir / "raw" / name
    path.write_text(
        json.dumps(_json_safe(data), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def log_node_return(
    node_name: str,
    intent_lines: Sequence[str],
    ret: Mapping[str, Any],
) -> None:
    """Log LangGraph node return dict (raw) to raw/ and reference in pipeline.log."""
    ctx = _ctx_or_none()
    if ctx is None:
        return
    path = write_raw_json(f"node_{node_name}_return", {"node": node_name, "return": dict(ret)})
    file_detail(
        f"node:{node_name}:return",
        [f"node={node_name}", *list(intent_lines)],
        raw_path=path,
    )


def log_node(
    node_name: str,
    *,
    intent_lines: Sequence[str],
    state_keys: Iterable[str],
    state: Mapping[str, Any],
    extra_raw: Any = None,
) -> None:
    """Log node entry: logic + raw slice of pipeline state for listed keys."""
    ctx = _ctx_or_none()
    if ctx is None:
        return
    console_line(f"→ {node_name}")
    slice_: Dict[str, Any] = {}
    for k in state_keys:
        if k in state:
            slice_[k] = state[k]
    payload: Dict[str, Any] = {"node": node_name, "state_slice": slice_}
    if extra_raw is not None:
        payload["extra"] = extra_raw
    path = write_raw_json(f"node_{node_name}", payload)
    file_detail(
        f"node:{node_name}",
        [f"node={node_name}", *list(intent_lines)],
        raw_path=path,
    )


def log_service(
    service_name: str,
    *,
    intent_lines: Sequence[str],
    raw: Any,
) -> None:
    ctx = _ctx_or_none()
    if ctx is None:
        return
    path = write_raw_json(f"service_{service_name}", {"service": service_name, "data": raw})
    file_detail(
        f"service:{service_name}",
        list(intent_lines),
        raw_path=path,
    )


def _json_safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "model_dump"):
        return _json_safe(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return _json_safe(vars(obj))
    if isinstance(obj, type):
        return str(obj)
    return str(obj)

