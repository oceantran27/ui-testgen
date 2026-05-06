#!/usr/bin/env python3
"""
Run Gemini UI extraction (flat controls + semantic groups, state-graph phase 1) on one image or all images in a folder.

Run from backend root so imports and .env resolve like the API:

    cd be
    python scripts/ui_extraction_preview.py

Requires GEMINI_API_KEY (see be/.env.example). Optional env: UI_EXTRACTION_PROMPT_PATH
(or legacy TWO_STAGE_UI_HIERARCHY_PROMPT_PATH), STATE_GRAPH_UI_EXTRACTION_MODEL.

Configure INPUT_PATH below (Windows path or pathlib):
- File: runs once; writes ``<stem>_ui_extraction_preview.json`` next to the image.
- Folder: scans images (suffixes below); writes ``<folder>/<OUTPUT_JSON_NAME>`` with all results.

Set INCLUDE_MINIFIED=true to add ``minified`` JSON string per screen (full extraction via
``ui_extraction_to_minified_json``, including ``is_primary_layer`` on controls). The state-graph
user-intents stage uses ``filter_scoped_ui_extraction`` plus ``user_intent_input_to_minified_json``
instead.

Each result object uses the top-level key ``ui_extraction`` for the parsed ``UIExtractionResult``.

On success the script prints only the path of the written JSON file (one line). Errors go to stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# --- configure here ---
INPUT_PATH: Path | str = r"C:\sqa-workspace\ui-testgen\be\data\images\07.png"
OUTPUT_JSON_NAME = "ui_extraction_preview.json"
RECURSIVE = False
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
# If None or empty, uses settings.STATE_GRAPH_UI_EXTRACTION_MODEL (same as state graph pipeline).
GEMINI_MODEL: str | None = None
INCLUDE_MINIFIED = False
# ----------------------

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.exceptions import AIProcessingError  # noqa: E402
from app.services.ui_extraction_payload import ui_extraction_to_minified_json  # noqa: E402
from app.services.ui_extraction_service import extract_ui_extraction_gemini_sync  # noqa: E402


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


def _resolve_model() -> str:
    if GEMINI_MODEL and str(GEMINI_MODEL).strip():
        return str(GEMINI_MODEL).strip()
    return settings.STATE_GRAPH_UI_EXTRACTION_MODEL


def _one_payload(
    *,
    image_path: str,
    model: str,
    ui_extraction: Any,
    llm_seconds: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "image_path": image_path,
        "model": model,
        "llm_seconds": round(llm_seconds, 6),
        "ui_extraction": ui_extraction.model_dump(mode="json", exclude_none=True),
    }
    if INCLUDE_MINIFIED:
        out["minified"] = ui_extraction_to_minified_json(ui_extraction)
    return out


def main() -> int:
    path = Path(INPUT_PATH).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: path does not exist: {path}", file=sys.stderr)
        return 1

    model = _resolve_model()
    if not settings.GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY is not set (configure be/.env)", file=sys.stderr)
        return 1

    if path.is_file():
        try:
            ui_extraction, llm_seconds = extract_ui_extraction_gemini_sync(str(path), model)
        except AIProcessingError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        payload = _one_payload(
            image_path=str(path), model=model, ui_extraction=ui_extraction, llm_seconds=llm_seconds
        )
        out_path = path.parent / f"{path.stem}_ui_extraction_preview.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(out_path.resolve())
        return 0

    if not path.is_dir():
        print(f"ERROR: not a file or directory: {path}", file=sys.stderr)
        return 1

    folder = path
    image_paths = _collect_image_paths(folder)
    if not image_paths:
        print(
            f"No images found in {folder} (suffixes: {IMAGE_SUFFIXES}, recursive={RECURSIVE})",
            file=sys.stderr,
        )
        return 0

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    total_llm = 0.0
    for img in image_paths:
        try:
            ui_extraction, llm_seconds = extract_ui_extraction_gemini_sync(img, model)
            total_llm += llm_seconds
            results.append(
                _one_payload(image_path=img, model=model, ui_extraction=ui_extraction, llm_seconds=llm_seconds)
            )
        except AIProcessingError as exc:
            errors.append({"image_path": img, "error": str(exc)})

    aggregate: dict[str, Any] = {
        "input_folder": str(folder),
        "file_count": len(image_paths),
        "recursive": RECURSIVE,
        "model": model,
        "prompt_path_setting": settings.UI_EXTRACTION_PROMPT_PATH,
        "include_minified": INCLUDE_MINIFIED,
        "total_llm_seconds": round(total_llm, 6),
        "results": results,
        "errors": errors,
    }
    out_path = folder / OUTPUT_JSON_NAME
    out_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path.resolve())
    if errors:
        print(f"errors: {len(errors)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
