from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


def _bootstrap_paths() -> Path:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    be_dir = repo_root / "be"
    agent_root = repo_root / "agent-test-codebases"

    for path in (str(be_dir), str(agent_root)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return repo_root


REPO_ROOT = _bootstrap_paths()

from app.schemas.pipeline import VisualParserOutput  # noqa: E402
from app.services.prompt_service import load_visual_parser_prompt  # noqa: E402

from shared_harness.bootstrap import read_json_file  # noqa: E402
from shared_harness.kpi import latency_summary, traceability_coverage  # noqa: E402
from shared_harness.reporting import write_report  # noqa: E402
from shared_harness.stage_runner import StageRunner  # noqa: E402


def _run_once(runner: StageRunner, image_path: Path) -> dict[str, Any]:
    result = runner.run_stage(
        stage_name="visual_parser",
        prompt_text=load_visual_parser_prompt(),
        temperature=0.1,
        image_path=str(image_path),
        context_text=None,
        user_instruction="Input: UI screenshot. Produce the Visual Parser JSON.",
        schema_model=VisualParserOutput,
    )
    return result.to_dict()


def _fixture_run(payload: dict[str, Any]) -> dict[str, Any]:
    validated = VisualParserOutput.model_validate(payload).model_dump(mode="json")
    return {
        "validated_json": validated,
        "metrics": {
            "elapsed_ms": 0,
            "prompt_token_estimate": 0,
            "output_token_estimate": 0,
            "cost_usd_estimate": 0.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Visual Parser evaluator")
    parser.add_argument(
        "--image-path",
        default=str(REPO_ROOT / "be" / "data" / "images" / "02.png"),
        help="Path to test image",
    )
    parser.add_argument("--repeat", type=int, default=1, help="Number of repeated runs")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"), help="Provider name")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "gemini-2.5-flash"), help="Model name")
    parser.add_argument(
        "--execution-mode",
        choices=("live", "fixture"),
        default="live",
        help="Run live stage call or consume a deterministic fixture output",
    )
    parser.add_argument(
        "--stage-output-fixture",
        default=str(Path(__file__).resolve().parent / "fixtures" / "vp_output_02.json"),
        help="Fixture file for execution-mode=fixture",
    )
    parser.add_argument(
        "--report-dir",
        default=str(Path(__file__).resolve().parent / "reports"),
        help="Report output directory",
    )
    args = parser.parse_args()

    image_path = Path(args.image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    runs: list[dict[str, Any]] = []
    if args.execution_mode == "fixture":
        payload = read_json_file(Path(args.stage_output_fixture).resolve())
        for _ in range(max(1, args.repeat)):
            runs.append(_fixture_run(payload))
    else:
        runner = StageRunner(provider_name=args.provider, model_name=args.model)
        for _ in range(max(1, args.repeat)):
            runs.append(_run_once(runner, image_path))

    latencies = [int(run["metrics"]["elapsed_ms"]) for run in runs]
    prompt_tokens = sum(int(run["metrics"]["prompt_token_estimate"]) for run in runs)
    output_tokens = sum(int(run["metrics"]["output_token_estimate"]) for run in runs)
    cost_total = round(sum(float(run["metrics"]["cost_usd_estimate"]) for run in runs), 8)

    last = runs[-1]
    traceability = traceability_coverage("visual_parser", last["validated_json"])

    report = {
        "stage": "visual_parser",
        "provider": args.provider,
        "model": args.model,
        "execution_mode": args.execution_mode,
        "image_path": str(image_path),
        "repeat": max(1, args.repeat),
        "kpis": {
            "schema_validity_rate": 1.0,
            "latency_ms": latency_summary(latencies),
            "traceability_coverage": traceability,
            "semantic": {
                "available": False,
                "reason": "Visual Parser output does not expose user-goal strings for semantic goal scoring.",
            },
            "token_and_cost_estimate": {
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens": prompt_tokens + output_tokens,
                "cost_usd": cost_total,
            },
        },
        "sample_output": last["validated_json"],
    }

    report_path = write_report(Path(args.report_dir), "vp_eval", report)
    print(f"Saved report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
