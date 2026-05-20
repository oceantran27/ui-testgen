"""Module 1 entry: discover images, call vision model, write raw outputs + manifest."""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.logging import logger
from app.model_providers.base import ImageInput, ModelCallStatus
from app.services.storage_service import storage_service

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.schemas.raw_output_manifest_schema import (
    ManifestItem,
    RawOutputManifest,
)
from experiments.ui_state_extraction.services.experiment_image_id_service import (
    build_experiment_image_id,
)
from experiments.ui_state_extraction.services.experiment_model_call_service import (
    call_joint_screen_understanding_for_experiment,
    utc_now_iso,
)
from experiments.ui_state_extraction.services.image_discovery_service import (
    ImageDiscoveryError,
    discover_images,
)
from experiments.ui_state_extraction.services.module1_run_report_service import (
    aggregate_model_latency,
    build_model_config_snapshot,
    build_timing_notes,
    configured_primary_avg_ms,
    write_raw_output_report_md,
)
from experiments.ui_state_extraction.services.raw_output_persistence_service import (
    path_for_manifest,
    raw_output_file_path,
    write_json_document,
)

_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _mime_for_extension(ext: str) -> str:
    e = ext.lower()
    if e in _EXT_MIME:
        return _EXT_MIME[e]
    g = mimetypes.guess_type(f"x{e}")[0]
    return g or "application/octet-stream"


def _read_image_bytes_sync(source: str) -> bytes:
    if source.lower().startswith("http://") or source.lower().startswith("https://"):
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            r = client.get(source)
            r.raise_for_status()
            return r.content
    return Path(source).read_bytes()


async def _read_image_bytes(source: str) -> bytes:
    return await asyncio.to_thread(_read_image_bytes_sync, source)


def _model_error_message(resp: Any) -> str:
    err = getattr(resp, "error", None)
    if err is not None:
        return getattr(err, "message", str(err))
    return f"status={getattr(resp, 'status', '')}"


async def _prepare_image_input(
    *,
    image_id: str,
    source_path: str,
    extension: str,
) -> tuple[ImageInput, str]:
    """Returns ImageInput and image_uri_used_for_model."""
    image_uri_meta = source_path
    if not source_path.lower().startswith("http"):
        image_uri_meta = str(Path(source_path).resolve())

    if config.USE_STORAGE_UPLOAD:
        data = await _read_image_bytes(source_path)
        ext = extension.lower()
        mime = _mime_for_extension(ext)
        key = f"experiments/ui_state_extraction/images/{image_id}{ext}"
        storage_uri = storage_service.upload_file(data, key, content_type=mime)
        return ImageInput(image_id=image_id, storage_uri=storage_uri), storage_uri

    data = await _read_image_bytes(source_path)
    mime = _mime_for_extension(extension)
    return ImageInput(image_id=image_id, image_bytes=data, mime_type=mime), image_uri_meta


def _warn_state_id(image_id: str, raw: dict[str, Any] | None) -> None:
    if not raw:
        return
    ui = raw.get("ui_state")
    if not isinstance(ui, dict):
        return
    expected = f"state_{image_id}"
    got = ui.get("state_id")
    if got != expected:
        logger.warning(
            "ui_state.state_id mismatch for image_id=%s: expected %r got %r",
            image_id,
            expected,
            got,
        )


async def _process_image(
    *,
    run_id: str,
    sem: asyncio.Semaphore,
    record: dict[str, Any],
    out_path: Path,
    overwrite: bool,
) -> ManifestItem:
    relative_path = record["relative_path"]
    stem = record["stem"]
    image_id = build_experiment_image_id(relative_path=relative_path, stem=stem).image_id

    meta_uri = record["image_source_path"]
    if not meta_uri.lower().startswith("http"):
        meta_uri = str(Path(meta_uri).resolve())

    if out_path.exists() and not overwrite:
        return ManifestItem(
            image_id=image_id,
            relative_path=relative_path,
            raw_output_path=path_for_manifest(out_path),
            status="skipped",
            skip_reason="raw_output_exists",
        )

    image_uri_for_model: str | None = None
    async with sem:
        try:
            image_input, image_uri_for_model = await _prepare_image_input(
                image_id=image_id,
                source_path=record["image_source_path"],
                extension=record["extension"],
            )
            response = await call_joint_screen_understanding_for_experiment(
                run_id=run_id,
                image_id=image_id,
                image_uri=meta_uri,
                image_input=image_input,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Model call failed for %s", relative_path)
            doc = ExperimentRawOutputDocument(
                schema_version=config.RAW_OUTPUT_SCHEMA_VERSION,
                experiment_name=config.EXPERIMENT_NAME,
                image=ImageMetaInRawOutput(
                    image_id=image_id,
                    source_path=record["image_source_path"],
                    relative_path=relative_path,
                    filename=record.get("filename", ""),
                    stem=stem,
                    extension=record.get("extension", ""),
                    image_uri_used_for_model=image_uri_for_model,
                ),
                model_call=ModelCallMeta(
                    prompt_name=config.PROMPT_NAME,
                    prompt_version="v1",
                    status="failed",
                    error_message=str(exc),
                    created_at=utc_now_iso(),
                    latency_ms=None,
                    retry_count=0,
                ),
                raw_model_output=None,
            )
            write_json_document(out_path, doc.model_dump(mode="json"))
            return ManifestItem(
                image_id=image_id,
                relative_path=relative_path,
                raw_output_path=path_for_manifest(out_path),
                status="failed",
                latency_ms=None,
                provider=None,
                model_name=None,
            )

    created_at = utc_now_iso()
    _lat = getattr(response, "latency_ms", None)
    call_latency: int | None = int(_lat) if _lat is not None else None
    call_retry = int(getattr(response, "retry_count", 0) or 0)
    resp_provider = getattr(response, "provider", "") or ""
    resp_model = getattr(response, "model_name", "") or ""

    if response.status == ModelCallStatus.SUCCESS and response.parsed_output is not None:
        raw_model = response.parsed_output.model_dump(mode="json")
        _warn_state_id(image_id, raw_model)
        doc = ExperimentRawOutputDocument(
            schema_version=config.RAW_OUTPUT_SCHEMA_VERSION,
            experiment_name=config.EXPERIMENT_NAME,
            image=ImageMetaInRawOutput(
                image_id=image_id,
                source_path=record["image_source_path"],
                relative_path=relative_path,
                filename=record["filename"],
                stem=stem,
                extension=record["extension"],
                image_uri_used_for_model=image_uri_for_model,
            ),
            model_call=ModelCallMeta(
                prompt_name=config.PROMPT_NAME,
                prompt_version="v1",
                provider=response.provider,
                model_name=response.model_name,
                status="success",
                error_message=None,
                created_at=created_at,
                latency_ms=call_latency,
                retry_count=call_retry,
            ),
            raw_model_output=raw_model,
        )
        write_json_document(out_path, doc.model_dump(mode="json"))
        return ManifestItem(
            image_id=image_id,
            relative_path=relative_path,
            raw_output_path=path_for_manifest(out_path),
            status="success",
            latency_ms=call_latency,
            provider=resp_provider or None,
            model_name=resp_model or None,
        )

    err = _model_error_message(response)
    doc = ExperimentRawOutputDocument(
        schema_version=config.RAW_OUTPUT_SCHEMA_VERSION,
        experiment_name=config.EXPERIMENT_NAME,
        image=ImageMetaInRawOutput(
            image_id=image_id,
            source_path=record["image_source_path"],
            relative_path=relative_path,
            filename=record["filename"],
            stem=stem,
            extension=record["extension"],
            image_uri_used_for_model=image_uri_for_model,
        ),
        model_call=ModelCallMeta(
            prompt_name=config.PROMPT_NAME,
            prompt_version="v1",
            provider=resp_provider,
            model_name=resp_model,
            status="failed",
            error_message=err,
            created_at=created_at,
            latency_ms=call_latency,
            retry_count=call_retry,
        ),
        raw_model_output=None,
    )
    write_json_document(out_path, doc.model_dump(mode="json"))
    return ManifestItem(
        image_id=image_id,
        relative_path=relative_path,
        raw_output_path=path_for_manifest(out_path),
        status="failed",
        latency_ms=call_latency,
        provider=resp_provider or None,
        model_name=resp_model or None,
    )


async def run_async() -> RawOutputManifest:
    config.RAW_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    records_all = discover_images(config.IMAGE_ROOT_URL_OR_PATH, list(config.ALLOWED_IMAGE_EXTENSIONS))
    total_discovered = len(records_all)
    cap = max(0, config.MAX_IMAGES_TO_PROCESS)
    records = records_all if cap == 0 else records_all[:cap]
    if cap > 0 and total_discovered > cap:
        logger.info(
            "MAX_IMAGES_TO_PROCESS=%s: processing first %s of %s discovered images (sorted by relative_path)",
            cap,
            len(records),
            total_discovered,
        )

    run_id = f"exp_ui_state_extract_{uuid.uuid4().hex[:12]}"
    sem = asyncio.Semaphore(max(1, config.MAX_CONCURRENCY))
    overwrite = config.OVERWRITE_RAW_OUTPUT

    tasks: list[asyncio.Task[ManifestItem]] = []
    for rec in records:
        out_p = raw_output_file_path(
            config.RAW_OUTPUT_DIR,
            rec["relative_path"],
            rec["stem"],
        )
        tasks.append(
            asyncio.create_task(
                _process_image(
                    run_id=run_id,
                    sem=sem,
                    record=rec,
                    out_path=out_p,
                    overwrite=overwrite,
                )
            )
        )

    items = await asyncio.gather(*tasks) if tasks else []
    items_sorted = sorted(items, key=lambda x: x.relative_path)
    success = sum(1 for i in items_sorted if i.status == "success")
    failed = sum(1 for i in items_sorted if i.status == "failed")
    skipped = sum(1 for i in items_sorted if i.status == "skipped")

    model_cfg = build_model_config_snapshot()
    latency_summary = aggregate_model_latency(items_sorted)
    timing_notes = build_timing_notes(items_sorted)

    manifest = RawOutputManifest(
        schema_version=config.MANIFEST_SCHEMA_VERSION,
        run_id=run_id,
        image_root_url_or_path=config.IMAGE_ROOT_URL_OR_PATH,
        total_images_discovered=total_discovered,
        total_images_enqueued=len(records),
        max_images_to_process=config.MAX_IMAGES_TO_PROCESS,
        total_success=success,
        total_failed=failed,
        total_skipped=skipped,
        experiment_model_settings=model_cfg,
        model_latency_summary=latency_summary,
        timing_notes=timing_notes,
        items=items_sorted,
    )
    m_path = config.REPORT_DIR / "raw_output_manifest.json"
    write_json_document(m_path, manifest.model_dump(mode="json"))

    report_path = config.REPORT_DIR / config.RAW_OUTPUT_REPORT_FILENAME
    write_raw_output_report_md(
        report_path,
        run_id=run_id,
        model_config=model_cfg,
        model_latency_summary=latency_summary,
        timing_notes=timing_notes,
        total_images_discovered=total_discovered,
        total_images_enqueued=len(records),
        total_success=success,
        total_failed=failed,
        total_skipped=skipped,
    )

    primary_avg = configured_primary_avg_ms(latency_summary, model_cfg)
    logger.info(
        "Module 1 finished: run_id=%s discovered=%s enqueued=%s success=%s failed=%s skipped=%s "
        "manifest=%s report=%s configured_model_avg_latency_ms=%s",
        run_id,
        total_discovered,
        len(records),
        success,
        failed,
        skipped,
        m_path,
        report_path,
        primary_avg,
    )
    return manifest


def main() -> None:
    try:
        asyncio.run(run_async())
    except ImageDiscoveryError as e:
        logger.error("Image discovery failed: %s", e)
        raise SystemExit(2) from e


if __name__ == "__main__":
    main()
