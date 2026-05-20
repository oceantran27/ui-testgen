"""CLI for flow_discovery experiment (run from repo ``be/`` directory).

Defaults for paths and flags live in ``experiments.flow_discovery.config`` (``CLI_*``).
Override any value by passing the corresponding CLI flag.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from experiments.flow_discovery import config as fd_config
from experiments.flow_discovery.gt_converter.ground_truth_auto_validator import annotate_package_issues
from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
from experiments.flow_discovery.io_utils import read_json_document, write_json_document
from experiments.flow_discovery.paths import resolve_path_under_package
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage

_CFG_HELP = "Mặc định: experiments.flow_discovery.config.CLI_*"


def _path_cli(path_arg: Path | None, config_str: str | None, *, required: bool, name: str) -> Path | None:
    if path_arg is not None:
        s = str(path_arg)
        if Path(s).is_absolute():
            return Path(s).resolve()
        return resolve_path_under_package(s)
    resolved = fd_config.resolve_cli_path(config_str)
    if resolved is None and required:
        print(
            f"flow_discovery: thiếu đường dẫn ({name}). "
            f"Đặt biến tương ứng trong config.py hoặc truyền flag CLI.",
            file=sys.stderr,
        )
        sys.exit(2)
    return resolved


def _req_path(path_arg: Path | None, config_str: str | None, *, name: str) -> Path:
    p = _path_cli(path_arg, config_str, required=True, name=name)
    assert p is not None
    return p


def _path_cli_opt(path_arg: Path | None, config_str: str | None) -> Path | None:
    if path_arg is not None:
        s = str(path_arg)
        if Path(s).is_absolute():
            return Path(s).resolve()
        return resolve_path_under_package(s)
    return fd_config.resolve_cli_path(config_str)


def _str_opt(cli: str | None, cfg: Optional[str]) -> Optional[str]:
    if cli is not None and str(cli).strip():
        return str(cli).strip()
    if cfg is not None and str(cfg).strip():
        return str(cfg).strip()
    return None


def _bool_skip_catalog(args: argparse.Namespace) -> bool:
    base = fd_config.CLI_VALIDATE_CATALOG_SCREEN_COUNT
    if args.skip_catalog_screen_check:
        return False
    return bool(base)


def _bool_strict_input(args: argparse.Namespace) -> bool:
    return bool(fd_config.CLI_INPUT_BUILDER_STRICT or getattr(args, "strict", False))


def run_print_config(_args: argparse.Namespace) -> int:
    def posix(cfg_attr: str) -> str | None:
        raw = getattr(fd_config, cfg_attr, None)
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            return None
        if not isinstance(raw, str):
            return str(raw)
        r = fd_config.resolve_cli_path(raw)
        return r.as_posix() if r else None

    data: dict[str, object] = {
        "CLI_APP_ID": fd_config.CLI_APP_ID,
        "CLI_WORK_DIR": posix("CLI_WORK_DIR"),
        "CLI_RAW_JOINT_DIR": posix("CLI_RAW_JOINT_DIR"),
        "CLI_INPUT_BUILDER_OUT_DIR": posix("CLI_INPUT_BUILDER_OUT_DIR"),
        "CLI_IMAGE_MAP_PATH": posix("CLI_IMAGE_MAP_PATH"),
        "CLI_INPUT_BUILDER_STRICT": fd_config.CLI_INPUT_BUILDER_STRICT,
        "CLI_COMPRESSED_CATALOG_PATH": posix("CLI_COMPRESSED_CATALOG_PATH"),
        "CLI_RAW_CAPTURE_OUTPUT_PATH": posix("CLI_RAW_CAPTURE_OUTPUT_PATH"),
        "CLI_GROUND_TRUTH_REVIEWED_PATH": posix("CLI_GROUND_TRUTH_REVIEWED_PATH"),
        "CLI_GT_CONVERT_RAW_OUTPUT": posix("CLI_GT_CONVERT_RAW_OUTPUT"),
        "CLI_GT_CONVERT_OUT": posix("CLI_GT_CONVERT_OUT"),
        "CLI_GT_VALIDATE_INPUT": posix("CLI_GT_VALIDATE_INPUT"),
        "CLI_GT_VALIDATE_OUT": posix("CLI_GT_VALIDATE_OUT"),
        "CLI_EVAL_RAW_OUTPUT": posix("CLI_EVAL_RAW_OUTPUT"),
        "CLI_EVAL_GROUND_TRUTH": posix("CLI_EVAL_GROUND_TRUTH"),
        "CLI_EVAL_OUT_DIR": posix("CLI_EVAL_OUT_DIR"),
        "CLI_RUN_BATCH_MANIFEST": posix("CLI_RUN_BATCH_MANIFEST"),
        "CLI_RUN_BATCH_OUT_DIR": posix("CLI_RUN_BATCH_OUT_DIR"),
        "CLI_BUILD_COMPRESSED_BATCH_MANIFEST": posix("CLI_BUILD_COMPRESSED_BATCH_MANIFEST"),
        "CLI_RUN_BATCH_FAIL_FAST": fd_config.CLI_RUN_BATCH_FAIL_FAST,
        "CLI_BUILD_COMPRESSED_BATCH_STRICT": fd_config.CLI_BUILD_COMPRESSED_BATCH_STRICT,
        "CLI_PROMPT_VERSION": fd_config.CLI_PROMPT_VERSION,
        "CLI_PROMPT_NAME": fd_config.CLI_PROMPT_NAME,
        "CLI_PROVIDER": fd_config.CLI_PROVIDER,
        "CLI_MODEL": fd_config.CLI_MODEL,
        "CLI_MAX_CATALOG_SCREENS": fd_config.CLI_MAX_CATALOG_SCREENS,
        "CLI_SKIP_RAW_CAPTURE": fd_config.CLI_SKIP_RAW_CAPTURE,
        "CLI_VALIDATE_CATALOG_SCREEN_COUNT": fd_config.CLI_VALIDATE_CATALOG_SCREEN_COUNT,
        "CLI_RUN_ID": fd_config.CLI_RUN_ID,
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))  # noqa: T201
    return 0


async def _run_one_from_joint_raw_async(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.pipeline_runner import run_one_from_joint_raw_async

    app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or fd_config.CLI_APP_ID
    work_dir = _req_path(args.work_dir, fd_config.CLI_WORK_DIR, name="work_dir / CLI_WORK_DIR")
    raw_joint = _req_path(args.raw_joint_dir, fd_config.CLI_RAW_JOINT_DIR, name="raw_joint_dir")
    imap = _path_cli_opt(args.image_map, fd_config.CLI_IMAGE_MAP_PATH)
    run_id = _str_opt(args.run_id, fd_config.CLI_RUN_ID)
    outcome = await run_one_from_joint_raw_async(
        app_id=app_id,
        raw_joint_dir=raw_joint,
        work_dir=work_dir,
        image_map_path=imap,
        run_id=run_id,
        strict_input=_bool_strict_input(args),
        prompt_version=_str_opt(args.prompt_version, fd_config.CLI_PROMPT_VERSION),
        prompt_name_override=_str_opt(args.prompt_name, fd_config.CLI_PROMPT_NAME),
        provider_override=_str_opt(args.provider, fd_config.CLI_PROVIDER),
        model_name_override=_str_opt(args.model, fd_config.CLI_MODEL),
        max_catalog_screens=(
            args.max_catalog_screens
            if args.max_catalog_screens is not None
            else fd_config.CLI_MAX_CATALOG_SCREENS
        ),
        validate_screen_count=_bool_skip_catalog(args),
    )
    print(f"wrote_compressed_catalog:{outcome.compressed_catalog_path.as_posix()}")  # noqa: T201
    print(f"wrote_raw_package:{outcome.raw_path.as_posix()}")  # noqa: T201
    print(f"wrote_gt_draft:{outcome.ground_truth_draft_path.as_posix()}")  # noqa: T201
    if not outcome.ok:
        print(f"run_one_from_joint_raw_failed:{outcome.error_message}", file=sys.stderr)  # noqa: T201
        return 2
    return 0


def run_build_compressed(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.input_builder.input_build_runner import FlowDiscoveryInputBuildRunner

    app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or fd_config.CLI_APP_ID
    raw_joint = _req_path(args.raw_joint_dir, fd_config.CLI_RAW_JOINT_DIR, name="raw_joint_dir")
    out_dir = _req_path(args.out_dir, fd_config.CLI_INPUT_BUILDER_OUT_DIR, name="out_dir")
    imap = _path_cli_opt(args.image_map, fd_config.CLI_IMAGE_MAP_PATH)
    run_id = _str_opt(args.run_id, fd_config.CLI_RUN_ID)

    runner = FlowDiscoveryInputBuildRunner()
    res = runner.run(
        app_id=app_id,
        raw_joint_dir=str(raw_joint),
        out_dir=str(out_dir),
        image_map_path=str(imap) if imap else None,
        strict=_bool_strict_input(args),
        experiment_run_id=run_id,
    )
    print(f"wrote_compressed_catalog:{(out_dir / 'compressed_catalog_package.json').as_posix()}")  # noqa: T201
    print(f"experiment_run_id:{res.experiment_run_id}")  # noqa: T201
    return 0


def run_build_compressed_batch(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.input_builder.input_build_runner import FlowDiscoveryInputBuildRunner

    manifest = _req_path(
        args.manifest,
        fd_config.CLI_BUILD_COMPRESSED_BATCH_MANIFEST or None,
        name="manifest / CLI_BUILD_COMPRESSED_BATCH_MANIFEST",
    )
    doc = read_json_document(manifest)
    apps = doc.get("apps")
    if not isinstance(apps, list):
        print("manifest_missing_apps", file=sys.stderr)  # noqa: T201
        return 2
    runner = FlowDiscoveryInputBuildRunner()
    strict = bool(fd_config.CLI_BUILD_COMPRESSED_BATCH_STRICT or args.strict)
    bad = 0
    for row in apps:
        if not isinstance(row, dict):
            bad += 1
            continue
        app_id = str(row.get("app_id") or "").strip()
        rdir = row.get("raw_joint_dir")
        wdir = row.get("work_dir")
        if not app_id or not rdir or not wdir:
            bad += 1
            continue
        out_ib = resolve_path_under_package(str(wdir)) / "input_builder"
        imap = row.get("image_map")
        runner.run(
            app_id=app_id,
            raw_joint_dir=str(resolve_path_under_package(str(rdir))),
            out_dir=str(out_ib),
            image_map_path=str(resolve_path_under_package(str(imap))) if imap else None,
            strict=strict,
        )
    if bad:
        print(f"build_compressed_batch_skipped_rows:{bad}", file=sys.stderr)  # noqa: T201
    return 0


async def _run_raw_capture_async(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.raw_capture.raw_flow_discovery_runner import ExperimentRawFlowDiscoveryRunner

    app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or fd_config.CLI_APP_ID
    cat = _req_path(args.compressed_catalog, fd_config.CLI_COMPRESSED_CATALOG_PATH, name="compressed-catalog")
    out_path = _req_path(args.out, fd_config.CLI_RAW_CAPTURE_OUTPUT_PATH, name="out / CLI_RAW_CAPTURE_OUTPUT_PATH")

    runner = ExperimentRawFlowDiscoveryRunner(validate_screen_count=_bool_skip_catalog(args))
    await runner.run_from_compressed_catalog(
        app_id,
        cat,
        run_id=_str_opt(args.run_id, fd_config.CLI_RUN_ID),
        prompt_version=_str_opt(args.prompt_version, fd_config.CLI_PROMPT_VERSION),
        provider_override=_str_opt(args.provider, fd_config.CLI_PROVIDER),
        model_name_override=_str_opt(args.model, fd_config.CLI_MODEL),
        prompt_name_override=_str_opt(args.prompt_name, fd_config.CLI_PROMPT_NAME),
        max_catalog_screens=(
            args.max_catalog_screens
            if args.max_catalog_screens is not None
            else fd_config.CLI_MAX_CATALOG_SCREENS
        ),
        write_to_path=out_path,
    )
    print(f"wrote_raw_package:{out_path.as_posix()}")  # noqa: T201
    return 0


def run_one_from_joint_raw(args: argparse.Namespace) -> int:
    return asyncio.run(_run_one_from_joint_raw_async(args))


def run_raw_capture(args: argparse.Namespace) -> int:
    return asyncio.run(_run_raw_capture_async(args))


def run_evaluate(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.evaluator.evaluation_runner import run_evaluation

    app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or fd_config.CLI_APP_ID
    raw_out = _req_path(args.raw_output, fd_config.CLI_EVAL_RAW_OUTPUT, name="raw-output")
    gt = _req_path(args.ground_truth, fd_config.CLI_EVAL_GROUND_TRUTH, name="ground-truth")
    out_dir = _req_path(args.out_dir, fd_config.CLI_EVAL_OUT_DIR, name="out-dir")

    run_evaluation(
        app_id=app_id,
        raw_output_path=raw_out,
        ground_truth_path=gt,
        out_dir=out_dir,
        run_id=_str_opt(args.run_id, fd_config.CLI_RUN_ID),
    )
    print(f"wrote_evaluation:{out_dir.as_posix()}")  # noqa: T201
    return 0


def run_gt_validate(args: argparse.Namespace) -> int:
    inp = _req_path(args.input, fd_config.CLI_GT_VALIDATE_INPUT, name="input / CLI_GT_VALIDATE_INPUT")
    pkg_data = read_json_document(inp)
    gt = GroundTruthFlowPackage.model_validate(pkg_data)
    annotate_package_issues(gt)
    out_data = gt.model_dump(mode="json", round_trip=True)
    if args.stdout:
        print(json.dumps(out_data, indent=2))  # noqa: T201
    else:
        def_out = fd_config.resolve_cli_path(fd_config.CLI_GT_VALIDATE_OUT)
        out_path = Path(args.out).resolve() if args.out else def_out or inp
        write_json_document(out_path, out_data)
        print(f"wrote_gt_validated:{out_path.as_posix()}")  # noqa: T201
    return 0


async def run_one_async_ns(args: argparse.Namespace) -> int:
    """Single app: compressed catalog capture (optional) → evaluation."""
    from experiments.flow_discovery.pipeline_runner import run_one_async as pipeline_run_one_async

    app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or fd_config.CLI_APP_ID
    work_dir = _req_path(args.work_dir, fd_config.CLI_WORK_DIR, name="work-dir")
    cat = _req_path(
        args.compressed_catalog,
        fd_config.CLI_COMPRESSED_CATALOG_PATH,
        name="compressed-catalog",
    )

    gt_cli = getattr(args, "ground_truth", None)
    gt_cfg = fd_config.resolve_cli_path(fd_config.CLI_GROUND_TRUTH_REVIEWED_PATH)
    if gt_cli is not None:
        gt_path: Path | None = _path_cli_opt(gt_cli, None)
    else:
        gt_path = gt_cfg

    outcome = await pipeline_run_one_async(
        app_id=app_id,
        compressed_catalog=cat,
        work_dir=work_dir,
        ground_truth_path=gt_path,
        run_id=_str_opt(args.run_id, fd_config.CLI_RUN_ID),
        skip_raw_capture=bool(fd_config.CLI_SKIP_RAW_CAPTURE or getattr(args, "skip_raw_capture", False)),
        prompt_version=_str_opt(args.prompt_version, fd_config.CLI_PROMPT_VERSION),
        prompt_name_override=_str_opt(args.prompt_name, fd_config.CLI_PROMPT_NAME),
        provider_override=_str_opt(args.provider, fd_config.CLI_PROVIDER),
        model_name_override=_str_opt(args.model, fd_config.CLI_MODEL),
        max_catalog_screens=(
            args.max_catalog_screens
            if args.max_catalog_screens is not None
            else fd_config.CLI_MAX_CATALOG_SCREENS
        ),
        validate_screen_count=_bool_skip_catalog(args),
    )
    print(f"wrote_raw_package:{outcome.raw_path.as_posix()}")  # noqa: T201 — raw path regardless
    print(f"wrote_evaluation:{outcome.evaluation_dir.as_posix()}")  # noqa: T201
    if not outcome.ok:
        print(f"run_one_failed:{outcome.error_message}", file=sys.stderr)  # noqa: T201
        return 2
    return 0


def run_one(args: argparse.Namespace) -> int:
    return asyncio.run(run_one_async_ns(args))


def run_batch(args: argparse.Namespace) -> int:
    from experiments.flow_discovery.pipeline_runner import run_batch_from_manifest

    manifest = _req_path(
        args.manifest,
        fd_config.CLI_RUN_BATCH_MANIFEST or None,
        name="manifest / CLI_RUN_BATCH_MANIFEST",
    )
    outp = _req_path(args.out_dir, fd_config.CLI_RUN_BATCH_OUT_DIR, name="out-dir")

    try:
        outs = run_batch_from_manifest(
            manifest,
            outp,
            continue_on_error=not (fd_config.CLI_RUN_BATCH_FAIL_FAST or args.fail_fast),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"run_batch_failed:{exc}", file=sys.stderr)  # noqa: T201
        return 2
    bad = [o for o in outs if not o.ok]
    if bad:
        for o in bad:
            print(f"batch_item_failed:{o.app_id}:{o.error_message}", file=sys.stderr)  # noqa: T201
        return 3
    print(f"wrote_batch_summary_csv:{outp.joinpath('evaluation_summary.csv').as_posix()}")  # noqa: T201
    return 0


def run_gt_convert(args: argparse.Namespace) -> int:
    raw_path = _req_path(args.raw_output, fd_config.CLI_GT_CONVERT_RAW_OUTPUT, name="raw-output")
    out_path = _req_path(args.out, fd_config.CLI_GT_CONVERT_OUT, name="out")

    pkg_data = read_json_document(raw_path)
    package = RawFlowDiscoveryExperimentPackage.model_validate(pkg_data)
    draft_app_id = _str_opt(args.app_id, fd_config.CLI_APP_ID) or package.app_id
    gt_pkg = convert_raw_package_to_draft(package, app_id_override=draft_app_id)
    write_json_document(out_path, gt_pkg.model_dump(mode="json", round_trip=True))
    print(f"wrote_gt_draft:{out_path.as_posix()}")  # noqa: T201
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="experiments.flow_discovery.cli")
    subs = p.add_subparsers(dest="command", required=True)

    subs.add_parser("print-config", help=f"In JSON: effective CLI defaults from config.py. ({_CFG_HELP})")

    r = subs.add_parser("raw-capture", help="Compressed catalog JSON → RawFlowDiscoveryExperimentPackage")
    r.add_argument("--app-id", default=None, help=f"App id ({_CFG_HELP})")
    r.add_argument("--compressed-catalog", type=Path, default=None, help=f"Catalog JSON ({_CFG_HELP})")
    r.add_argument("--out", type=Path, default=None, help=f"Output raw package path ({_CFG_HELP})")
    r.add_argument("--run-id", default=None)
    r.add_argument("--prompt-version", default=None)
    r.add_argument("--prompt-name", default=None)
    r.add_argument("--provider", default=None)
    r.add_argument("--model", dest="model", default=None)
    r.add_argument("--max-catalog-screens", type=int, default=None)
    r.add_argument("--skip-catalog-screen-check", action="store_true")

    g = subs.add_parser("gt-convert", help="Raw package JSON → GroundTruthFlowPackage draft")
    g.add_argument("--app-id", default=None, help="Override GroundTruthFlowPackage.app_id")
    g.add_argument("--raw-output", type=Path, default=None, help=f"Raw package JSON ({_CFG_HELP})")
    g.add_argument("--out", type=Path, default=None, help=f"Draft GT output ({_CFG_HELP})")

    v = subs.add_parser("gt-validate", help="Re-run auto-validation on GroundTruthFlowPackage JSON")
    v.add_argument("--input", type=Path, default=None, help=f"GT JSON ({_CFG_HELP})")
    v.add_argument("--out", type=Path, default=None)
    v.add_argument("--stdout", action="store_true")

    e = subs.add_parser("evaluate", help="Raw model output JSON + reviewed GT → evaluation metrics")
    e.add_argument("--app-id", default=None, help=f"({_CFG_HELP})")
    e.add_argument("--raw-output", type=Path, default=None, help=f"({_CFG_HELP})")
    e.add_argument("--ground-truth", type=Path, default=None, help=f"({_CFG_HELP})")
    e.add_argument("--out-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    e.add_argument("--run-id", default=None)

    o = subs.add_parser("run-one", help="Raw capture (+ optional GT path) → evaluation under ``work_dir``")
    o.add_argument("--app-id", default=None, help=f"({_CFG_HELP})")
    o.add_argument("--compressed-catalog", type=Path, default=None, help=f"({_CFG_HELP})")
    o.add_argument("--work-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    o.add_argument("--ground-truth", type=Path, default=None)
    o.add_argument("--skip-raw-capture", action="store_true")
    o.add_argument("--run-id", default=None)
    o.add_argument("--prompt-version", default=None)
    o.add_argument("--prompt-name", default=None)
    o.add_argument("--provider", default=None)
    o.add_argument("--model", dest="model", default=None)
    o.add_argument("--max-catalog-screens", type=int, default=None)
    o.add_argument("--skip-catalog-screen-check", action="store_true")

    b = subs.add_parser("run-batch", help="Iterate apps from manifest JSON; write evaluation_summary.csv")
    b.add_argument("--manifest", type=Path, default=None, help=f"({_CFG_HELP} if CLI_RUN_BATCH_MANIFEST set)")
    b.add_argument("--out-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    b.add_argument("--fail-fast", action="store_true")

    bc = subs.add_parser("build-compressed", help="Joint raw JSON directory → compressed_catalog_package.json")
    bc.add_argument("--app-id", default=None, help=f"({_CFG_HELP})")
    bc.add_argument("--raw-joint-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    bc.add_argument("--out-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    bc.add_argument("--image-map", type=Path, default=None)
    bc.add_argument("--run-id", default=None)
    bc.add_argument("--strict", action="store_true")

    bcb = subs.add_parser("build-compressed-batch", help="Batch build-compressed from manifest")
    bcb.add_argument("--manifest", type=Path, default=None, help=f"({_CFG_HELP})")
    bcb.add_argument("--strict", action="store_true")

    jr = subs.add_parser("run-one-from-joint-raw", help="input_builder → raw-capture → gt-convert draft")
    jr.add_argument("--app-id", default=None, help=f"({_CFG_HELP})")
    jr.add_argument("--raw-joint-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    jr.add_argument("--work-dir", type=Path, default=None, help=f"({_CFG_HELP})")
    jr.add_argument("--image-map", type=Path, default=None)
    jr.add_argument("--run-id", default=None)
    jr.add_argument("--strict", action="store_true")
    jr.add_argument("--prompt-version", default=None)
    jr.add_argument("--prompt-name", default=None)
    jr.add_argument("--provider", default=None)
    jr.add_argument("--model", dest="model", default=None)
    jr.add_argument("--max-catalog-screens", type=int, default=None)
    jr.add_argument("--skip-catalog-screen-check", action="store_true")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(list(argv) if argv is not None else None)

    if ns.command == "print-config":
        return run_print_config(ns)
    if ns.command == "raw-capture":
        return run_raw_capture(ns)
    if ns.command == "build-compressed":
        return run_build_compressed(ns)
    if ns.command == "build-compressed-batch":
        return run_build_compressed_batch(ns)
    if ns.command == "run-one-from-joint-raw":
        return run_one_from_joint_raw(ns)
    if ns.command == "gt-convert":
        return run_gt_convert(ns)
    if ns.command == "gt-validate":
        return run_gt_validate(ns)
    if ns.command == "evaluate":
        return run_evaluate(ns)
    if ns.command == "run-one":
        return run_one(ns)
    if ns.command == "run-batch":
        return run_batch(ns)

    parser.error(f"unknown command {ns.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
