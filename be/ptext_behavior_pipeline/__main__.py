"""CLI: manifest JSON → P-TEXT pipeline → stdout."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid manifest JSON: {exc}") from exc


def _manifest_to_captures(data: dict[str, Any]) -> list[tuple[str, str]]:
    raw = data.get("captures")
    if not isinstance(raw, list) or not raw:
        raise SystemExit("manifest must contain non-empty 'captures' array")
    out: list[tuple[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit(f"captures[{i}] must be an object")
        cid = item.get("capture_id")
        pth = item.get("path")
        if not isinstance(cid, str) or not isinstance(pth, str):
            raise SystemExit(f"captures[{i}] needs string capture_id and path")
        out.append((cid, pth))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "P-TEXT behavior pipeline: Stage B+C per screenshot, Stage A on JSON bundle only. "
            "Run from the `be` directory:  set PYTHONPATH=.  then  python -m ptext_behavior_pipeline"
        )
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="JSON file: {\"captures\":[{\"capture_id\":\"img_001\",\"path\":\"...\"}], \"model\": optional}",
    )
    parser.add_argument("--model", default=None, help="OpenAI model id (default: gpt-4.1)")
    parser.add_argument("--concurrency", type=int, default=4, help="Max parallel B+C runs (default 4)")
    parser.add_argument("--verbose", action="store_true", help="Include per-capture hierarchy/bdd in output")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write JSON result to file")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress log lines to stderr")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)
    data = _load_manifest(args.manifest)
    captures = _manifest_to_captures(data)
    model = args.model or data.get("model")

    from ptext_behavior_pipeline.pipeline import run_ptext_pipeline_async

    async def _go() -> Any:
        return await run_ptext_pipeline_async(
            captures,
            model=model if isinstance(model, str) else None,
            max_concurrency=args.concurrency,
        )

    result = asyncio.run(_go())
    payload: dict[str, Any] = {
        "model": result.model,
        "flows": [f.model_dump(mode="json") for f in result.flows],
    }
    if args.verbose:
        payload["captures"] = result.captures
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
