"""Batch and single-app orchestration: raw capture + evaluation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

from experiments.flow_discovery.evaluator.evaluation_runner import run_evaluation
from experiments.flow_discovery.evaluator.report_writer import write_batch_summary_csv
from experiments.flow_discovery.io_utils import read_json_document
from experiments.flow_discovery.paths import (
    DEFAULT_GT_DRAFT_BASENAME,
    resolve_path_under_package,
    work_dir_evaluation_dir,
    work_dir_gt_converter_dir,
    work_dir_ground_truth_reviewed_path,
    work_dir_input_builder_dir,
    work_dir_raw_output_path,
)
from experiments.flow_discovery.schemas.evaluation_schema import EvaluationResult
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


class ManifestAppEntry(BaseModel):
    app_id: str
    compressed_catalog: str = Field(description="Absolute or package-relative catalogue JSON path.")
    ground_truth: str = Field(description="Reviewed GroundTruthFlowPackage JSON path.")
    work_dir: str | None = Field(
        default=None,
        description="Intermediate outputs; defaults to parent directory of ``ground_truth``.",
    )
    skip_raw_capture: bool = Field(default=False, description="If True, reuse existing raw capture under ``work_dir``.")


class AppsManifest(BaseModel):
    apps: List[ManifestAppEntry]

    @field_validator("apps")
    @classmethod
    def _non_empty_apps(cls, v: List[ManifestAppEntry]) -> List[ManifestAppEntry]:
        if not v:
            raise ValueError("manifest_must_list_at_least_one_app")
        return v


class JointRawManifestAppEntry(BaseModel):
    app_id: str
    raw_joint_dir: str = Field(description="Path to directory of *.raw.json joint outputs.")
    work_dir: str = Field(description="Experiment work directory (input_builder + raw_capture + gt_converter).")
    image_map: str | None = Field(default=None, description="Optional image_map.json path.")


class JointRawManifest(BaseModel):
    apps: List[JointRawManifestAppEntry]

    @field_validator("apps")
    @classmethod
    def _non_empty_joint_apps(cls, v: List[JointRawManifestAppEntry]) -> List[JointRawManifestAppEntry]:
        if not v:
            raise ValueError("joint_manifest_must_list_at_least_one_app")
        return v


@dataclass(frozen=True)
class RunOneFromJointRawOutcome:
    app_id: str
    work_dir: Path
    input_builder_dir: Path
    compressed_catalog_path: Path
    raw_path: Path
    ground_truth_draft_path: Path
    ok: bool
    error_message: str | None = None


@dataclass(frozen=True)
class RunOneOutcome:
    app_id: str
    compressed_catalog: Path
    work_dir: Path
    raw_path: Path
    ground_truth_path: Path
    evaluation_dir: Path
    result: EvaluationResult | None
    ok: bool
    error_message: str | None = None


async def run_one_async(
    *,
    app_id: str,
    compressed_catalog: Path | str,
    work_dir: Path | str,
    ground_truth_path: Optional[Path | str] = None,
    run_id: Optional[str] = None,
    skip_raw_capture: bool = False,
    prompt_version: Optional[str] = None,
    prompt_name_override: Optional[str] = None,
    provider_override: Optional[str] = None,
    model_name_override: Optional[str] = None,
    max_catalog_screens: Optional[int] = None,
    validate_screen_count: bool = True,
) -> RunOneOutcome:
    wd = Path(work_dir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    cat_path = Path(compressed_catalog).resolve()
    gt_path = Path(
        ground_truth_path if ground_truth_path is not None else work_dir_ground_truth_reviewed_path(wd),
    ).resolve()
    raw_path = work_dir_raw_output_path(wd)
    eval_dir = work_dir_evaluation_dir(wd)

    if not skip_raw_capture:
        from experiments.flow_discovery.raw_capture.raw_flow_discovery_runner import ExperimentRawFlowDiscoveryRunner

        runner = ExperimentRawFlowDiscoveryRunner(validate_screen_count=validate_screen_count)
        await runner.run_from_compressed_catalog(
            app_id,
            cat_path,
            run_id=run_id,
            prompt_version=prompt_version,
            provider_override=provider_override,
            model_name_override=model_name_override,
            prompt_name_override=prompt_name_override,
            max_catalog_screens=max_catalog_screens,
            write_to_path=raw_path,
        )
    else:
        if not raw_path.is_file():
            return RunOneOutcome(
                app_id=app_id,
                compressed_catalog=cat_path,
                work_dir=wd,
                raw_path=raw_path,
                ground_truth_path=gt_path,
                evaluation_dir=eval_dir,
                result=None,
                ok=False,
                error_message=f"skip_raw_capture_set_but_missing_file:{raw_path.as_posix()}",
            )

    if not gt_path.is_file():
        return RunOneOutcome(
            app_id=app_id,
            compressed_catalog=cat_path,
            work_dir=wd,
            raw_path=raw_path,
            ground_truth_path=gt_path,
            evaluation_dir=eval_dir,
            result=None,
            ok=False,
            error_message=f"missing_reviewed_ground_truth:{gt_path.as_posix()}",
        )

    env_data = read_json_document(raw_path)
    env_run_id: Optional[str] = None
    try:
        env = RawFlowDiscoveryExperimentPackage.model_validate(env_data)
        env_run_id = env.run_id
    except Exception:
        env_run_id = str(env_data.get("run_id") or "").strip() or None if isinstance(env_data, dict) else None

    eff_run_id = run_id or env_run_id

    try:
        res = run_evaluation(
            app_id=app_id,
            raw_output_path=raw_path,
            ground_truth_path=gt_path,
            out_dir=eval_dir,
            run_id=eff_run_id,
        )
    except Exception as exc:  # noqa: BLE001 — surface batch-friendly single-line error
        return RunOneOutcome(
            app_id=app_id,
            compressed_catalog=cat_path,
            work_dir=wd,
            raw_path=raw_path,
            ground_truth_path=gt_path,
            evaluation_dir=eval_dir,
            result=None,
            ok=False,
            error_message=str(exc),
        )

    return RunOneOutcome(
        app_id=app_id,
        compressed_catalog=cat_path,
        work_dir=wd,
        raw_path=raw_path,
        ground_truth_path=gt_path,
        evaluation_dir=eval_dir,
        result=res,
        ok=True,
    )


def run_one(
    *,
    app_id: str,
    compressed_catalog: Path | str,
    work_dir: Path | str,
    ground_truth_path: Optional[Path | str] = None,
    run_id: Optional[str] = None,
    skip_raw_capture: bool = False,
    prompt_version: Optional[str] = None,
    prompt_name_override: Optional[str] = None,
    provider_override: Optional[str] = None,
    model_name_override: Optional[str] = None,
    max_catalog_screens: Optional[int] = None,
    validate_screen_count: bool = True,
) -> RunOneOutcome:
    return asyncio.run(
        run_one_async(
            app_id=app_id,
            compressed_catalog=compressed_catalog,
            work_dir=work_dir,
            ground_truth_path=ground_truth_path,
            run_id=run_id,
            skip_raw_capture=skip_raw_capture,
            prompt_version=prompt_version,
            prompt_name_override=prompt_name_override,
            provider_override=provider_override,
            model_name_override=model_name_override,
            max_catalog_screens=max_catalog_screens,
            validate_screen_count=validate_screen_count,
        ),
    )


async def run_one_from_joint_raw_async(
    *,
    app_id: str,
    raw_joint_dir: Path | str,
    work_dir: Path | str,
    image_map_path: str | Path | None = None,
    run_id: str | None = None,
    strict_input: bool = False,
    prompt_version: Optional[str] = None,
    prompt_name_override: Optional[str] = None,
    provider_override: Optional[str] = None,
    model_name_override: Optional[str] = None,
    max_catalog_screens: Optional[int] = None,
    validate_screen_count: bool = True,
) -> RunOneFromJointRawOutcome:
    """input_builder → raw_capture → gt-convert draft (no evaluation)."""
    wd = Path(work_dir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    ib = work_dir_input_builder_dir(wd)
    ib.mkdir(parents=True, exist_ok=True)
    raw_path = work_dir_raw_output_path(wd)
    gt_dir = work_dir_gt_converter_dir(wd)
    gt_dir.mkdir(parents=True, exist_ok=True)
    gt_draft = gt_dir / DEFAULT_GT_DRAFT_BASENAME

    from experiments.flow_discovery.input_builder.input_build_runner import FlowDiscoveryInputBuildRunner

    build_runner = FlowDiscoveryInputBuildRunner()
    built = build_runner.run(
        app_id=app_id,
        raw_joint_dir=str(Path(raw_joint_dir).resolve()),
        out_dir=str(ib),
        image_map_path=str(Path(image_map_path).resolve()) if image_map_path else None,
        strict=strict_input,
        experiment_run_id=run_id,
    )
    cat_path = ib / "compressed_catalog_package.json"

    try:
        from experiments.flow_discovery.raw_capture.raw_flow_discovery_runner import ExperimentRawFlowDiscoveryRunner

        runner = ExperimentRawFlowDiscoveryRunner(validate_screen_count=validate_screen_count)
        env = await runner.run_from_compressed_catalog(
            app_id,
            cat_path,
            run_id=built.experiment_run_id,
            prompt_version=prompt_version,
            provider_override=provider_override,
            model_name_override=model_name_override,
            prompt_name_override=prompt_name_override,
            max_catalog_screens=max_catalog_screens,
            write_to_path=raw_path,
        )

        from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
        from experiments.flow_discovery.io_utils import write_json_document

        gt_pkg = convert_raw_package_to_draft(env, app_id_override=app_id)
        write_json_document(gt_draft, gt_pkg.model_dump(mode="json", round_trip=True))
    except Exception as exc:  # noqa: BLE001
        return RunOneFromJointRawOutcome(
            app_id=app_id,
            work_dir=wd,
            input_builder_dir=ib,
            compressed_catalog_path=cat_path,
            raw_path=raw_path,
            ground_truth_draft_path=gt_draft,
            ok=False,
            error_message=str(exc),
        )

    return RunOneFromJointRawOutcome(
        app_id=app_id,
        work_dir=wd,
        input_builder_dir=ib,
        compressed_catalog_path=cat_path,
        raw_path=raw_path,
        ground_truth_draft_path=gt_draft,
        ok=True,
        error_message=None,
    )


def run_one_from_joint_raw(
    *,
    app_id: str,
    raw_joint_dir: Path | str,
    work_dir: Path | str,
    image_map_path: str | Path | None = None,
    run_id: str | None = None,
    strict_input: bool = False,
    prompt_version: Optional[str] = None,
    prompt_name_override: Optional[str] = None,
    provider_override: Optional[str] = None,
    model_name_override: Optional[str] = None,
    max_catalog_screens: Optional[int] = None,
    validate_screen_count: bool = True,
) -> RunOneFromJointRawOutcome:
    return asyncio.run(
        run_one_from_joint_raw_async(
            app_id=app_id,
            raw_joint_dir=raw_joint_dir,
            work_dir=work_dir,
            image_map_path=image_map_path,
            run_id=run_id,
            strict_input=strict_input,
            prompt_version=prompt_version,
            prompt_name_override=prompt_name_override,
            provider_override=provider_override,
            model_name_override=model_name_override,
            max_catalog_screens=max_catalog_screens,
            validate_screen_count=validate_screen_count,
        ),
    )


def run_batch_joint_raw_from_manifest(
    manifest_path: Path | str,
    *,
    continue_on_error: bool = True,
) -> List[RunOneFromJointRawOutcome]:
    doc = JointRawManifest.model_validate(read_json_document(Path(manifest_path).resolve()))
    outcomes: List[RunOneFromJointRawOutcome] = []
    for entry in doc.apps:
        rdir = resolve_path_under_package(entry.raw_joint_dir)
        wdir = resolve_path_under_package(entry.work_dir)
        imap = resolve_path_under_package(entry.image_map) if entry.image_map else None
        out = run_one_from_joint_raw(
            app_id=entry.app_id.strip(),
            raw_joint_dir=rdir,
            work_dir=wdir,
            image_map_path=imap,
        )
        outcomes.append(out)
        if not out.ok and not continue_on_error:
            raise RuntimeError(out.error_message or "run_one_from_joint_raw_failed")
    return outcomes


def run_batch_from_manifest(
    manifest_path: Path | str,
    out_dir: Path | str,
    *,
    continue_on_error: bool = True,
) -> List[RunOneOutcome]:
    """Run ``run_one`` for each manifest row; aggregate CSV into ``out_dir``."""
    outp = Path(out_dir).resolve()
    outp.mkdir(parents=True, exist_ok=True)
    doc = AppsManifest.model_validate(read_json_document(Path(manifest_path).resolve()))

    csv_rows: List[Any] = []
    outcomes: List[RunOneOutcome] = []

    for entry in doc.apps:
        gt_resolved = resolve_path_under_package(entry.ground_truth)
        work = (
            resolve_path_under_package(entry.work_dir)
            if entry.work_dir
            else gt_resolved.parent.resolve()
        )
        outcome = run_one(
            app_id=entry.app_id.strip(),
            compressed_catalog=resolve_path_under_package(entry.compressed_catalog),
            work_dir=work,
            ground_truth_path=gt_resolved,
            skip_raw_capture=entry.skip_raw_capture,
        )
        outcomes.append(outcome)
        if outcome.ok and outcome.result:
            csv_rows.append(outcome.result)
        else:
            csv_rows.append((entry.app_id, "", outcome.error_message or "UNKNOWN_ERROR"))

        if not outcome.ok and not continue_on_error:
            write_batch_summary_csv(outp / "evaluation_summary.csv", csv_rows)
            raise RuntimeError(outcome.error_message or "run_one_failed")

    write_batch_summary_csv(outp / "evaluation_summary.csv", csv_rows)

    mf_copy = outp / "batch_manifest_used.json"
    mf_copy.write_text(json.dumps(doc.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")

    failures = [o for o in outcomes if not o.ok]

    failure_log = outp / "batch_failures.jsonl"
    if failure_log.exists():
        failure_log.unlink()

    failure_lines: List[str] = []
    for o in failures:
        failure_lines.append(
            json.dumps(
                {
                    "app_id": o.app_id,
                    "error_message": o.error_message,
                    "raw_path": o.raw_path.as_posix(),
                    "ground_truth_path": o.ground_truth_path.as_posix(),
                },
            ),
        )
    if failure_lines:
        failure_log.write_text("\n".join(failure_lines) + "\n", encoding="utf-8")

    return outcomes


__all__ = [
    "AppsManifest",
    "JointRawManifest",
    "JointRawManifestAppEntry",
    "ManifestAppEntry",
    "RunOneFromJointRawOutcome",
    "RunOneOutcome",
    "run_batch_from_manifest",
    "run_batch_joint_raw_from_manifest",
    "run_one",
    "run_one_async",
    "run_one_from_joint_raw",
    "run_one_from_joint_raw_async",
]

