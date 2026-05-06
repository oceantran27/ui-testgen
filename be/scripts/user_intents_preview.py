#!/usr/bin/env python3

"""

Run the user-intents phase (OpenAI) against one UI extraction JSON file.



Uses the same system prompt as the state-graph pipeline

(`user_intents_generation_system_prompt.txt` via

`STATE_GRAPH_USER_INTENTS_PROMPT_PATH` / `generate_user_intents_openai_sync`).

That prompt describes ui-flat-v5 fields, group binding rules, intent limits (roughly 2-8

for typical UIs), and navigation/mega-menu heuristics.



Input is parsed as full stage-1 extraction, then ``filter_scoped_ui_extraction`` and

``user_intent_input_to_minified_json`` match the pipeline before the OpenAI call.



**image_id** is required (``--image-id`` or ``DEFAULT_IMAGE_ID``): the service always injects a

canonical id into the user message, unlike the prompt's optional ``not_provided`` fallback when no

id is supplied.



On success, writes one JSON file (default ``<hierarchy_stem>_user_intents_preview.json``).

Payload keys: ``input_path``, ``image_id``, ``model``, ``elapsed_seconds``,

``prompt_path_setting``, ``user_intents_result``.



On success the script prints only the absolute path of the written file (one line). Errors go to

stderr.



Run (from repo backend root):

    cd be

    python scripts/user_intents_preview.py --hierarchy path/to/extraction.json --image-id <sha256_hex>



With defaults from the "configure here" block:

    python scripts/user_intents_preview.py



Environment: OPENAI_API_KEY (e.g. from ``be/.env``).



Input file:

    - JSON matching ``UIExtractionResult`` (ui-flat-v5), or

    - ``screen_*.json`` with top-level ``ui_extraction`` or legacy ``hierarchy``.

"""



from __future__ import annotations



import argparse

import json

import sys

import time

from pathlib import Path

from typing import Any



# --- configure here (used when CLI omits --hierarchy / --image-id) ---

DEFAULT_HIERARCHY_PATH: Path | str | None = r"C:\sqa-workspace\ui-testgen\be\data\images\07_ui_extraction_preview.json"

DEFAULT_IMAGE_ID: str | None = "02"

# Default written path: ``{hierarchy.parent}/{hierarchy.stem}{OUTPUT_SUFFIX}`` when ``--output`` is omitted.

OUTPUT_SUFFIX = "_user_intents_preview.json"

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

    filter_scoped_ui_extraction,

    parse_ui_extraction_payload,

    user_intent_input_to_minified_json,

)

from app.services.user_intent_service import generate_user_intents_openai_sync  # noqa: E402





def _default_output_path(hier_path: Path) -> Path:

    return hier_path.parent / f"{hier_path.stem}{OUTPUT_SUFFIX}"





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

        description=(

            "Preview user intents from one ui-flat-v5 extraction JSON (OpenAI); "

            "requires canonical --image-id (pipeline-aligned)."

        ),

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

        help="Canonical image_id (e.g. sha256 hex); always sent to the model in this script",

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

        help=(

            "Override output JSON path (default: "

            f"<hierarchy_stem>{OUTPUT_SUFFIX} next to the hierarchy file)"

        ),

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



    scoped = filter_scoped_ui_extraction(ui_extraction)

    minified = user_intent_input_to_minified_json(scoped)



    t0 = time.perf_counter()

    try:

        result = generate_user_intents_openai_sync(image_id, minified, model)

    except AIProcessingError as exc:

        print(f"ERROR: {exc}", file=sys.stderr)

        return 1

    elapsed_s = time.perf_counter() - t0



    result_body = result.model_dump(mode="json")



    out_path = (

        Path(args.output).expanduser().resolve()

        if args.output

        else _default_output_path(hier_path)

    )

    payload: dict[str, Any] = {

        "input_path": str(hier_path),

        "image_id": image_id,

        "model": model,

        "elapsed_seconds": round(elapsed_s, 6),

        "prompt_path_setting": settings.STATE_GRAPH_USER_INTENTS_PROMPT_PATH,

        "user_intents_result": result_body,

    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(out_path.resolve())

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

