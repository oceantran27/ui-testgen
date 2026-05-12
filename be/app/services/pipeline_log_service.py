"""
Read pipeline worker session logs from disk (PIPELINE_RUN_LOG_ROOT).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings


def _be_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_latest_log_file(run_id: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Find newest session dir *_{run_id} and return (pipeline.log path or None, relative path hint).
    """
    base = _be_root() / settings.PIPELINE_RUN_LOG_ROOT
    if not base.is_dir():
        return None, None

    suffix = f"_{run_id}"
    matches = sorted(
        [p for p in base.iterdir() if p.is_dir() and p.name.endswith(suffix)],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        return None, None

    session = matches[0]
    log_file = session / "pipeline.log"
    try:
        rel = str(log_file.relative_to(_be_root()))
    except ValueError:
        rel = str(log_file)

    if not log_file.is_file():
        return None, rel

    return log_file, rel


def read_latest_pipeline_log(run_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (pipeline.log text, relative path under be/) for the newest session dir
    matching *_{run_id}. If nothing found, (None, None).
    """
    log_file, rel_hint = _resolve_latest_log_file(run_id)
    if log_file is None:
        if rel_hint is not None:
            return None, rel_hint
        return None, None

    text = log_file.read_text(encoding="utf-8", errors="replace")
    return text, rel_hint


def read_pipeline_log_incremental(
    run_id: str,
    from_byte: int = 0,
) -> Tuple[Optional[str], Optional[str], int, Optional[str]]:
    """
    Return (content, rel_path, next_byte, message).

    - from_byte == 0: content is the entire file (or None if missing).
    - from_byte > 0: content is only new bytes from that offset; if offset is past
      end (e.g. file truncated), the full file is returned and next_byte reset.

    next_byte is the new file size in bytes (read offset for EOF).
    """
    if from_byte < 0:
        from_byte = 0

    log_file, rel_hint = _resolve_latest_log_file(run_id)
    if log_file is None:
        if rel_hint is not None:
            return None, rel_hint, 0, None
        return None, None, 0, None

    raw = log_file.read_bytes()
    total = len(raw)

    if from_byte == 0:
        text = raw.decode("utf-8", errors="replace")
        return text, rel_hint, total, None

    if from_byte > total:
        text = raw.decode("utf-8", errors="replace")
        return text, rel_hint, total, None

    chunk = raw[from_byte:]
    text = chunk.decode("utf-8", errors="replace")
    return text, rel_hint, total, None
