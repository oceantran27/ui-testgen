#!/usr/bin/env python3
"""
Run the full state-graph pipeline live: dedupe images, Gemini UI extraction, OpenAI user intents,
Gemini flow inference, then Actor–Critic E2E scenarios. Writes artifacts under a run directory
(dedup.json, screen_*.json, screens_bundle.json, flows_raw.json, final_test_output.json, result.json).

Configure INPUT_FOLDER below (local path or file:// URL), or pass --folder on the CLI.

From backend root (requires GEMINI_API_KEY and OPENAI_API_KEY in be/.env):

    cd be
    python scripts/state_graph_pipeline_preview.py --folder path/to/images

On success prints one line: absolute path to result.json. Errors on stderr.

Gemini UI extraction retries indefinitely on transient 503 / UNAVAILABLE (e.g. high demand),
waiting 2 seconds between attempts (preview script only).

Scan rules match ui_extraction_preview (suffixes, optional RECURSIVE).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse


# --- configure here ---
INPUT_FOLDER: Path | str | None = r"C:\sqa-workspace\ui-testgen\be\uploads\multi-img-input\593e720a-0908-4e95-98df-f3b9e445f25e"
RECURSIVE = False
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
# Default output root under be/ (resolved relative to this script's parent = be/)
OUTPUT_RUNS_ROOT: Path | str | None = None  # None -> be/state_graph_preview_runs
# ----------------------


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.exceptions import AIProcessingError  # noqa: E402
import app.services.state_graph_pipeline_service as sg_pipeline  # noqa: E402
from app.services.state_graph_pipeline_service import state_graph_pipeline_service  # noqa: E402


def _is_transient_ui_extraction_error(exc: AIProcessingError) -> bool:
    parts: list[str] = [str(exc)]
    if exc.__cause__ is not None:
        parts.append(str(exc.__cause__))
    text = " ".join(parts).lower()
    return (
        "503" in text
        or "unavailable" in text
        or "high demand" in text
        or "try again later" in text
    )


def _extract_ui_extraction_gemini_sync_with_retry(orig_fn):
    def _wrapped(image_path: str, gemini_model: str):
        attempt = 0
        while True:
            try:
                return orig_fn(image_path, gemini_model)
            except AIProcessingError as e:
                if not _is_transient_ui_extraction_error(e):
                    raise
                attempt += 1
                print(
                    f"UI extraction transient error (attempt {attempt}), retrying in 2s — {e}",
                    file=sys.stderr,
                )
                time.sleep(2)

    return _wrapped


def _folder_path_from_arg(s: str) -> Path:
    s = s.strip()
    if s.lower().startswith("file:"):
        parsed = urlparse(s)
        path = unquote(parsed.path or "")
        if os.name == "nt" and path.startswith("/") and len(path) >= 3 and path[2] == ":":
            path = path[1:]
        return Path(path).resolve()
    return Path(s).expanduser().resolve()


def _collect_image_paths(folder: Path) -> list[str]:
    if RECURSIVE:
        paths_set: set[Path] = set()
        for suf in IMAGE_SUFFIXES:
            for p in folder.rglob(f"*{suf}"):
                if p.is_file():
                    paths_set.add(p.resolve())
        paths = list(paths_set)
    else:
        paths = []
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                paths.append(p.resolve())
    return sorted(str(p) for p in paths)


def _default_runs_root() -> Path:
    if OUTPUT_RUNS_ROOT:
        return Path(OUTPUT_RUNS_ROOT).expanduser().resolve()
    return (_ROOT / "state_graph_preview_runs").resolve()


async def _run_pipeline(*, input_id: str, saved_paths: list[str], out_dir: str) -> Path:
    await state_graph_pipeline_service.run(
        input_id=input_id,
        saved_paths=saved_paths,
        out_dir=out_dir,
    )
    return Path(out_dir) / "result.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Full state-graph pipeline from a folder of screenshots (live LLM calls).",
    )
    parser.add_argument(
        "--folder",
        metavar="PATH",
        help="Local folder or file:// URL with images (overrides INPUT_FOLDER when set)",
    )
    args = parser.parse_args()

    folder_s = args.folder or INPUT_FOLDER
    if not folder_s:
        print("ERROR: set INPUT_FOLDER or pass --folder", file=sys.stderr)
        return 1

    if not settings.GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is not set (configure be/.env)", file=sys.stderr)
        return 1
    if not settings.OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set (configure be/.env)", file=sys.stderr)
        return 1

    folder = _folder_path_from_arg(str(folder_s))
    if not folder.is_dir():
        print(f"ERROR: not a directory: {folder}", file=sys.stderr)
        return 1

    image_paths = _collect_image_paths(folder)
    if not image_paths:
        print(f"No images in {folder} (suffixes: {IMAGE_SUFFIXES}, recursive={RECURSIVE})", file=sys.stderr)
        return 1

    input_id = str(uuid.uuid4())
    out_dir = _default_runs_root() / input_id
    out_dir.mkdir(parents=True, exist_ok=True)

    _ui_extract_orig = sg_pipeline.extract_ui_extraction_gemini_sync
    sg_pipeline.extract_ui_extraction_gemini_sync = _extract_ui_extraction_gemini_sync_with_retry(
        _ui_extract_orig
    )
    try:
        result_path = asyncio.run(
            _run_pipeline(
                input_id=input_id,
                saved_paths=image_paths,
                out_dir=str(out_dir),
            )
        )
    except AIProcessingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        sg_pipeline.extract_ui_extraction_gemini_sync = _ui_extract_orig

    print(result_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
