"""Module 2 entry: read module-1 raw outputs, build temp ground truth + manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.logging import logger

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ModelCallMeta,
)
from experiments.ui_state_extraction.schemas.raw_output_manifest_schema import RawOutputManifest
from experiments.ui_state_extraction.schemas.temp_ground_truth_manifest_schema import (
    TempGroundTruthManifest,
    TempGroundTruthManifestItem,
)
from experiments.ui_state_extraction.services.raw_output_persistence_service import path_for_manifest
from experiments.ui_state_extraction.services.experiment_debug_log_service import (
    append_module2_event,
    new_debug_log_path,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import try_build_temp_ground_truth
from experiments.ui_state_extraction.services.temp_ground_truth_persistence_service import (
    temp_gt_file_path,
    write_json_document,
)


def _load_raw_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _discover_raw_paths_from_folder(raw_dir: Path) -> list[Path]:
    paths = sorted(raw_dir.rglob("*.raw.json"), key=lambda p: p.as_posix().lower())
    return paths


def run(
    *,
    raw_manifest_path: Path | None,
    use_raw_folder: bool,
    overwrite: bool,
    only_success: bool,
    limit: int,
    validate_joint_schema: bool,
    write_debug_log: bool = False,
    debug_log_verbose: bool = False,
) -> TempGroundTruthManifest:
    config.TEMP_GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    work_items: list[tuple[str, Path, str | None]] = []
    # (relative_path_for_output, raw_path_absolute, manifest_status or None)
    source_raw_manifest = ""

    if use_raw_folder:
        raw_dir = config.RAW_OUTPUT_DIR
        if not raw_dir.is_dir():
            logger.error("RAW_OUTPUT_DIR does not exist: %s", raw_dir)
            return TempGroundTruthManifest(
                schema_version=config.TEMP_GT_MANIFEST_SCHEMA_VERSION,
                source_mode="folder",
                total_raw_outputs=0,
            )
        paths = _discover_raw_paths_from_folder(raw_dir)
        for rp in paths:
            rel = path_for_manifest(rp)
            work_items.append((rel, rp, None))
        source_raw_manifest = ""
        mode_label = "folder"
    else:
        m_path = raw_manifest_path or (config.REPORT_DIR / "raw_output_manifest.json")
        source_raw_manifest = path_for_manifest(m_path)
        if not m_path.is_file():
            logger.error("Raw output manifest not found: %s", m_path)
            return TempGroundTruthManifest(
                schema_version=config.TEMP_GT_MANIFEST_SCHEMA_VERSION,
                source_raw_manifest=source_raw_manifest,
                source_mode="manifest",
                total_raw_outputs=0,
            )
        payload = _load_raw_json(m_path)
        manifest = RawOutputManifest.model_validate(payload)
        for it in manifest.items:
            if only_success and it.status != "success":
                continue
            raw_p = config.PACKAGE_ROOT / Path(it.raw_output_path)
            work_items.append((it.relative_path, raw_p, it.status))
        mode_label = "manifest"

    if limit > 0:
        work_items = work_items[:limit]

    manifest_items: list[TempGroundTruthManifestItem] = []
    converted = 0
    failed = 0

    debug_log_path: Path | None = None
    if write_debug_log:
        debug_log_path = new_debug_log_path(config.EXPERIMENT_DEBUG_LOG_DIR)
        logger.info("Module 2 debug log: %s", debug_log_path)

    for relative_path, raw_path, mf_status in work_items:
        if not raw_path.is_file():
            logger.warning("Missing raw output file: %s", raw_path)
            manifest_items.append(
                TempGroundTruthManifestItem(
                    image_id="",
                    relative_path=relative_path,
                    raw_output_path=path_for_manifest(raw_path) if raw_path else "",
                    temp_ground_truth_path="",
                    conversion_status="failed",
                    review_priority="high",
                    error_message="raw file missing",
                )
            )
            failed += 1
            if debug_log_path:
                append_module2_event(
                    debug_log_path,
                    image_id="",
                    relative_path=relative_path,
                    conversion_status="failed",
                    error_message="raw file missing",
                    raw_output_path=path_for_manifest(raw_path) if raw_path else "",
                    temp_ground_truth_path="",
                    verbose_log=debug_log_verbose,
                )
            continue

        try:
            raw_payload = _load_raw_json(raw_path)
            doc = ExperimentRawOutputDocument.model_validate(raw_payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Invalid raw wrapper %s", raw_path)
            manifest_items.append(
                TempGroundTruthManifestItem(
                    image_id="",
                    relative_path=relative_path,
                    raw_output_path=path_for_manifest(raw_path),
                    temp_ground_truth_path="",
                    conversion_status="failed",
                    review_priority="high",
                    error_message=str(exc),
                )
            )
            failed += 1
            if debug_log_path:
                append_module2_event(
                    debug_log_path,
                    image_id="",
                    relative_path=relative_path,
                    conversion_status="failed",
                    error_message=str(exc),
                    raw_output_path=path_for_manifest(raw_path),
                    temp_ground_truth_path="",
                    verbose_log=debug_log_verbose,
                )
            continue

        if mf_status is None and only_success:
            m = ModelCallMeta.model_validate(raw_payload.get("model_call") or {})
            if m.status != "success":
                manifest_items.append(
                    TempGroundTruthManifestItem(
                        image_id=doc.image.image_id,
                        relative_path=doc.image.relative_path or relative_path,
                        raw_output_path=path_for_manifest(raw_path),
                        temp_ground_truth_path="",
                        conversion_status="skipped",
                        review_priority="low",
                        error_message="not_success_model_call",
                    )
                )
                if debug_log_path:
                    append_module2_event(
                        debug_log_path,
                        image_id=doc.image.image_id,
                        relative_path=doc.image.relative_path or relative_path,
                        conversion_status="skipped",
                        error_message="not_success_model_call",
                        raw_output_path=path_for_manifest(raw_path),
                        temp_ground_truth_path="",
                        verbose_log=debug_log_verbose,
                    )
                continue

        raw_rel = path_for_manifest(raw_path)
        stem = doc.image.stem or Path(doc.image.relative_path or relative_path).stem
        out_path = temp_gt_file_path(
            config.TEMP_GROUND_TRUTH_DIR,
            doc.image.relative_path or relative_path,
            stem,
        )

        if out_path.exists() and not overwrite:
            manifest_items.append(
                TempGroundTruthManifestItem(
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    conversion_status="skipped",
                    review_priority="low",
                    error_message="temp_gt_exists",
                )
            )
            if debug_log_path:
                append_module2_event(
                    debug_log_path,
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    conversion_status="skipped",
                    error_message="temp_gt_exists",
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    verbose_log=debug_log_verbose,
                )
            continue
            manifest_items.append(
                TempGroundTruthManifestItem(
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    conversion_status="failed",
                    review_priority="high",
                    error_message="raw_model_output is null",
                )
            )
            failed += 1
            if debug_log_path:
                append_module2_event(
                    debug_log_path,
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    conversion_status="failed",
                    error_message="raw_model_output is null",
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    verbose_log=debug_log_verbose,
                )
            continue

        gt_doc, err = try_build_temp_ground_truth(
            doc,
            source_raw_output_path=raw_rel,
            validate_joint_schema=validate_joint_schema,
        )
        if gt_doc is None or err:
            manifest_items.append(
                TempGroundTruthManifestItem(
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    conversion_status="failed",
                    review_priority="high",
                    error_message=err or "build failed",
                )
            )
            failed += 1
            if debug_log_path:
                append_module2_event(
                    debug_log_path,
                    image_id=doc.image.image_id,
                    relative_path=doc.image.relative_path or relative_path,
                    conversion_status="failed",
                    error_message=err or "build failed",
                    raw_output_path=raw_rel,
                    temp_ground_truth_path=path_for_manifest(out_path),
                    verbose_log=debug_log_verbose,
                )
            continue

        write_json_document(out_path, gt_doc.model_dump(mode="json"))
        converted += 1
        pri = gt_doc.annotation_meta.review_priority
        manifest_items.append(
            TempGroundTruthManifestItem(
                image_id=doc.image.image_id,
                relative_path=doc.image.relative_path or relative_path,
                raw_output_path=raw_rel,
                temp_ground_truth_path=path_for_manifest(out_path),
                conversion_status="converted",
                review_priority=pri,
                auto_flag_count=len(gt_doc.conversion_report.auto_flags),
                invalid_reference_count=len(gt_doc.conversion_report.invalid_references),
            )
        )
        if debug_log_path:
            append_module2_event(
                debug_log_path,
                image_id=doc.image.image_id,
                relative_path=doc.image.relative_path or relative_path,
                conversion_status="converted",
                raw_output_path=raw_rel,
                temp_ground_truth_path=path_for_manifest(out_path),
                review_priority=pri,
                conversion_report=gt_doc.conversion_report,
                verbose_log=debug_log_verbose,
            )

    skipped = sum(1 for i in manifest_items if i.conversion_status == "skipped")
    converted_items = [i for i in manifest_items if i.conversion_status == "converted"]
    total_high = sum(1 for i in converted_items if i.review_priority == "high")
    total_med = sum(1 for i in converted_items if i.review_priority == "medium")
    total_low = sum(1 for i in converted_items if i.review_priority == "low")

    out_manifest = TempGroundTruthManifest(
        schema_version=config.TEMP_GT_MANIFEST_SCHEMA_VERSION,
        source_raw_manifest=source_raw_manifest,
        source_mode=mode_label,
        total_raw_outputs=len(work_items),
        total_converted=converted,
        total_failed=failed,
        total_skipped=skipped,
        total_high_priority_review=total_high,
        total_medium_priority_review=total_med,
        total_low_priority_review=total_low,
        items=sorted(manifest_items, key=lambda x: x.relative_path),
    )

    m_out = config.REPORT_DIR / "temp_ground_truth_manifest.json"
    write_json_document(m_out, out_manifest.model_dump(mode="json"))
    logger.info(
        "Module 2 finished mode=%s total=%s converted=%s failed=%s skipped=%s manifest=%s",
        mode_label,
        len(work_items),
        converted,
        failed,
        skipped,
        m_out,
    )
    return out_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build temp ground truth from module 1 raw outputs.")
    parser.add_argument(
        "--raw-manifest",
        type=Path,
        default=None,
        help="Path to raw_output_manifest.json (default: REPORT_DIR/raw_output_manifest.json)",
    )
    parser.add_argument(
        "--use-raw-folder",
        action="store_true",
        help="DFS raw_outputs/*.raw.json instead of manifest",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing .temp_gt.json files")
    parser.add_argument(
        "--include-non-success",
        action="store_true",
        help="Manifest mode: also include items not marked success (still requires raw_model_output)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0=all)")
    parser.add_argument(
        "--skip-joint-schema-validation",
        action="store_true",
        help="Do not validate raw_model_output with JointScreenUnderstandingResult",
    )
    parser.add_argument(
        "--write-debug-log",
        action="store_true",
        help="Append structured JSONL under reports/pipeline_debug/ (see config.EXPERIMENT_DEBUG_LOG_*)",
    )
    parser.add_argument(
        "--debug-log-verbose",
        action="store_true",
        help="More detail in JSONL and extra logger lines",
    )
    args = parser.parse_args()
    only_success = not args.include_non_success
    overwrite = args.overwrite or config.OVERWRITE_TEMP_GROUND_TRUTH
    write_dbg = bool(args.write_debug_log or config.EXPERIMENT_DEBUG_LOG_ENABLED)
    dbg_verbose = bool(args.debug_log_verbose or config.EXPERIMENT_DEBUG_LOG_VERBOSE)
    run(
        raw_manifest_path=args.raw_manifest,
        use_raw_folder=args.use_raw_folder,
        overwrite=overwrite,
        only_success=only_success,
        limit=max(0, args.limit),
        validate_joint_schema=not args.skip_joint_schema_validation,
        write_debug_log=write_dbg,
        debug_log_verbose=dbg_verbose,
    )


if __name__ == "__main__":
    main()
