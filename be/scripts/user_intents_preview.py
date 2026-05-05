#!/usr/bin/env python3
"""
Run the user-intents phase (OpenAI) against one UI extraction JSON file.

Uses the same prompt and minification as the state-graph pipeline
(`user_intents_generation_system_prompt.txt` via settings
`STATE_GRAPH_USER_INTENTS_PROMPT_PATH` / `generate_user_intents_openai_sync`).

Run (from repo backend root):
    cd be
    python scripts/user_intents_preview.py --hierarchy path/to/extraction.json --image-id <sha256_hex>

With defaults from the "configure here" block (leave CLI args off when both are set):
    cd be
    python scripts/user_intents_preview.py

Environment:
    OPENAI_API_KEY — required (load from `.env` when present if you run from `be/`).

Input file:
    - A JSON object matching `UIExtractionResult` (schema `ui-flat-v3`), or
    - A pipeline artifact `screen_*.json` containing top-level ``ui_extraction`` or legacy ``hierarchy``.

Optional:
    --model   overrides `STATE_GRAPH_USER_INTENT_MODEL` (default from settings).
    --output  write JSON (result + metadata) to this path.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# --- configure here (used when CLI omits --hierarchy / --image-id) ---
DEFAULT_HIERARCHY_PATH: Path | str | None = r"C:\sqa-workspace\ui-testgen\be\data\images\02_ui_extraction_preview.json"
DEFAULT_IMAGE_ID: str | None = "02"
# Example:
# DEFAULT_HIERARCHY_PATH = r"C:\path\to\screen_abc123.json"
# DEFAULT_IMAGE_ID = "a" * 64  # your canonical content hash
# --------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.exceptions import AIProcessingError  # noqa: E402
from app.services.ui_extraction_payload import (  # noqa: E402
    parse_ui_extraction_payload,
    ui_extraction_to_minified_json,
)
from app.services.user_intent_service import generate_user_intents_openai_sync  # noqa: E402


def _extraction_raw_from_file_text(text: str) -> str:
    """If file is `screen_*.json`, use nested `ui_extraction` or legacy `hierarchy`; else pass through."""
    stripped = text.strip()
    if not stripped.startswith("{"):
        return text
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict):
        nested = data.get("ui_extraction")
        if isinstance(nested, dict):
            return json.dumps(nested, ensure_ascii=False)
        legacy = data.get("hierarchy")
        if isinstance(legacy, dict):
            return json.dumps(legacy, ensure_ascii=False)
    return text


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, str, str] | None:
    hier_path_s = args.hierarchy or DEFAULT_HIERARCHY_PATH
    image_id = (args.image_id or DEFAULT_IMAGE_ID or "").strip()

    if not hier_path_s:
        print(
            "ERROR: missing input path (--hierarchy or DEFAULT_HIERARCHY_PATH)",
            file=sys.stderr,
        )
        return None
    if not image_id:
        print(
            "ERROR: missing image id (--image-id or DEFAULT_IMAGE_ID)",
            file=sys.stderr,
        )
        return None

    hier_path = Path(hier_path_s).expanduser().resolve()
    if not hier_path.is_file():
        print(f"ERROR: not a file: {hier_path}", file=sys.stderr)
        return None

    model = (args.model or "").strip() or settings.STATE_GRAPH_USER_INTENT_MODEL
    return hier_path, image_id, model


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview user intents from one UI extraction JSON (OpenAI).",
    )
    parser.add_argument(
        "--hierarchy",
        metavar="PATH",
        help="Path to UI extraction JSON or screen_*.json with ui_extraction / hierarchy",
    )
    parser.add_argument(
        "--image-id",
        dest="image_id",
        metavar="ID",
        help="Canonical image_id (e.g. sha256 hex) passed to the model",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        help=f"OpenAI model (default: {settings.STATE_GRAPH_USER_INTENT_MODEL!r} from settings)",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Write result JSON (with metadata) to this file",
    )
    args = parser.parse_args()

    resolved = _resolve_inputs(args)
    if resolved is None:
        return 1
    hier_path, image_id, model = resolved

    raw_text = hier_path.read_text(encoding="utf-8")
    extraction_raw = _extraction_raw_from_file_text(raw_text)

    try:
        ui_extraction = parse_ui_extraction_payload(extraction_raw)
    except AIProcessingError as exc:
        print(f"ERROR: failed to parse UI extraction: {exc}", file=sys.stderr)
        return 1

    minified = ui_extraction_to_minified_json(ui_extraction)

    t0 = time.perf_counter()
    try:
        result = generate_user_intents_openai_sync(image_id, minified, model)
    except AIProcessingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    elapsed_s = time.perf_counter() - t0

    result_body = result.model_dump(mode="json")
    print(json.dumps(result_body, ensure_ascii=False, indent=2))
    print()
    print(f"OpenAI call time: {elapsed_s:.3f}s", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        payload = {
            "input_path": str(hier_path),
            "image_id": image_id,
            "model": model,
            "elapsed_seconds": round(elapsed_s, 6),
            "user_intents_result": result_body,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
