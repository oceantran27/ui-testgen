"""
Standalone full LangGraph pipeline — same execution path as the ARQ worker
(``GraphExecutionService.execute``), without Redis.

Run from the ``be/`` directory::

    cd be
    python experiments/full_pipeline_standalone.py

Infrastructure (required):
- PostgreSQL: ``DATABASE_URL`` in ``.env`` / ``app.core.config``. If you use
  ``be/docker/docker-compose.yml``, Postgres is exposed on host port **5433** —
  use e.g. ``postgresql+asyncpg://testgen_user:testgen_password@localhost:5433/testgen_db``.
- MinIO (or S3-compatible): ``STORAGE_*``; default bucket ``ui-testgen-local`` is
  created by the docker compose ``minio-setup`` service.

LLM / VLM (real APIs, not mock):
- Set ``DEFAULT_MODEL_PROVIDER`` to ``gemini`` or ``openai`` and provide
  ``OPENAI_API_KEY`` as needed. Per-task overrides
  (e.g. behaviour intent) require keys for those providers too.
- Do not set provider to ``mock`` when you expect real model calls.

Logging:
- **Console:** short lines only (run_id, seed progress, graph start/done, errors).
- **Files:** ``experiments/logs/<run_id>/pipeline.log`` and ``raw/*.json`` for
  node state slices, model request/response, and seed metadata. Do not commit
  ``experiments/logs/`` (gitignored).
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Tuple

# ── User: input folder (screenshots) and summary output path ───────────────
INPUT_IMAGES_DIR: Path = Path(r"C:\Users\daidu\Desktop\flow\shopee")

OUTPUT_JSON_PATH: Path = (
    Path(__file__).resolve().parent / "full_pipeline_standalone_summary.json"
)


def _be_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_sys_path() -> None:
    root = str(_be_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _suffix_to_format(suffix: str) -> str | None:
    s = suffix.lower().lstrip(".")
    if s == "jpeg":
        return "jpg"
    if s in ("png", "jpg", "webp"):
        return s
    return None


async def _seed_run_images_from_dir(
    *,
    run_id: str,
    file_paths: list[Path],
) -> Tuple[int, int]:
    """
    Mirror successful path of ``image_service.upload_images`` using bytes from disk.
    Returns (uploaded_count, failed_count).
    """
    from PIL import Image as PILImage
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.logging import logger, log_event
    from app.db.models.image import Image
    from app.db.models.run import Run
    from app.db.session import AsyncSessionLocal
    from app.services.image_service import (
        ALLOWED_EXTENSIONS,
        _FORMAT_MAP,
        _compute_sha256_chunked,
        _generate_image_id,
    )
    from app.services.storage_service import storage_service
    from app.core import pipeline_run_log as prl

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Run).where(Run.id == run_id))
        run = res.scalar_one()
        current_count = run.total_images
        max_allowed = settings.MAX_IMAGES_PER_RUN
        upload_order_base = current_count

        if current_count >= max_allowed:
            raise SystemExit(
                f"Run already has {current_count} images (max {max_allowed})."
            )

        remaining = max_allowed - current_count
        uploaded_count = 0
        failed_count = 0

        for idx, path in enumerate(file_paths):
            filename = path.name
            if uploaded_count >= remaining:
                prl.file_detail(
                    "[seed]",
                    [f"skipped (max images): {filename}"],
                )
                failed_count += 1
                continue

            try:
                file_bytes = path.read_bytes()
            except OSError as e:
                logger.error("Failed to read %s: %s", path, e)
                failed_count += 1
                continue

            size_bytes = len(file_bytes)
            if not file_bytes:
                failed_count += 1
                continue

            max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            if size_bytes > max_bytes:
                failed_count += 1
                continue

            try:
                pil_img = PILImage.open(BytesIO(file_bytes))
                pil_img.verify()
                pil_img = PILImage.open(BytesIO(file_bytes))
                width, height = pil_img.size
                pil_format = pil_img.format
            except Exception:
                failed_count += 1
                continue

            ext = _FORMAT_MAP.get(pil_format, (pil_format or "").lower())
            if ext not in ALLOWED_EXTENSIONS:
                failed_count += 1
                continue

            sha256_hash = _compute_sha256_chunked(file_bytes)
            image_id = _generate_image_id()
            object_key = f"raw/{run_id}/{image_id}.{ext}"
            content_type = f"image/{ext}"

            try:
                storage_uri = storage_service.upload_file(
                    file_content=file_bytes,
                    object_name=object_key,
                    content_type=content_type,
                )
            except Exception as e:
                logger.error("Storage upload failed for %s: %s", filename, e)
                failed_count += 1
                continue

            upload_order = upload_order_base + uploaded_count + 1
            image_record = Image(
                id=image_id,
                run_id=run_id,
                original_filename=filename,
                storage_uri=storage_uri,
                width=width,
                height=height,
                format=ext,
                file_size=size_bytes,
                sha256_hash=sha256_hash,
                upload_order=upload_order,
                quality_status="pending_validation",
                is_valid=True,
            )
            db.add(image_record)
            uploaded_count += 1
            log_event("image_upload_completed", run_id=run_id, image_id=image_id)

            raw_meta: dict[str, Any] = {
                "original_filename": filename,
                "source_path": str(path.resolve()),
                "image_id": image_id,
                "storage_uri": storage_uri,
                "object_key": object_key,
                "sha256_hash": sha256_hash,
                "width": width,
                "height": height,
                "format": ext,
                "file_size": size_bytes,
                "upload_order": upload_order,
            }
            if prl.is_active():
                sidecar = prl.write_raw_json("seed_image", raw_meta)
                prl.file_detail(
                    "[seed]",
                    [f"uploaded {filename}", f"artifact={sidecar}"],
                )

        if uploaded_count > 0:
            run.total_images = current_count + uploaded_count
            if run.status == "created":
                run.status = "uploading"

        await db.commit()

    return uploaded_count, failed_count


async def _async_main() -> int:
    _ensure_sys_path()

    from sqlalchemy import select

    from app.core import pipeline_run_log as prl
    from app.core.config import settings
    from app.db.models.run import Run
    from app.db.session import AsyncSessionLocal
    from app.services import run_service
    from app.services.graph_service import GraphExecutionService

    input_dir = INPUT_IMAGES_DIR.resolve()
    if not input_dir.is_dir():
        print(f"ERROR: INPUT_IMAGES_DIR is not a directory: {input_dir}", file=sys.stderr)
        return 1

    allowed_lower = {x.lower() for x in settings.ALLOWED_IMAGE_FORMATS}
    files: list[Path] = []
    for p in sorted(input_dir.iterdir()):
        if not p.is_file():
            continue
        fmt = _suffix_to_format(p.suffix)
        if fmt and fmt in allowed_lower:
            files.append(p)

    if not files:
        print(
            f"ERROR: No images ({sorted(allowed_lower)}) under {input_dir}",
            file=sys.stderr,
        )
        return 1

    async with AsyncSessionLocal() as db:
        run = await run_service.create_run(
            db,
            project_name="full_pipeline_standalone",
            description="Local full pipeline experiment",
        )
        run_id = run.id

    log_dir = Path(__file__).resolve().parent / "logs" / run_id
    prl.activate(run_id, log_dir)

    try:
        prl.console_line(f"run_id={run_id}")
        prl.console_line(f"log_dir={log_dir}")
        prl.file_detail(
            "[seed]",
            [
                f"INPUT_IMAGES_DIR={input_dir}",
                f"files_discovered={len(files)}",
                f"DEFAULT_MODEL_PROVIDER={settings.DEFAULT_MODEL_PROVIDER}",
            ],
            raw={
                "paths": [str(f.resolve()) for f in files],
            },
        )

        prl.console_line(f"Seed: uploading up to {len(files)} images…")
        uploaded, failed = await _seed_run_images_from_dir(run_id=run_id, file_paths=files)
        prl.console_line(f"Seed: done ({uploaded} ok, {failed} failed).")
        prl.file_detail(
            "[seed]",
            ["upload batch finished", f"uploaded={uploaded}", f"failed_reads_or_skips={failed}"],
        )

        if uploaded == 0:
            prl.console_line("ERROR: no images uploaded — abort.")
            return 1

        prl.console_line("Graph: executing pipeline…")
        prl.file_detail("[pipeline]", ["GraphExecutionService.execute start", f"job_id=None"])

        final_state: dict[str, Any] = {}
        pipeline_exc: Optional[str] = None
        try:
            final_state = await GraphExecutionService.execute(run_id=run_id, job_id=None)
        except Exception as e:
            pipeline_exc = str(e)
            prl.console_line(f"ERROR: pipeline raised: {e}")
            prl.file_detail(
                "[pipeline]",
                ["GraphExecutionService.execute raised", pipeline_exc],
            )

        prl.file_detail(
            "[pipeline]",
            ["GraphExecutionService.execute finished"],
            state_slice={"keys": list(final_state.keys()) if final_state else []},
        )
        if final_state and prl.is_active():
            fs_path = prl.write_raw_json("final_graph_state", final_state)
            prl.file_detail(
                "[pipeline]",
                [f"final_state_file={fs_path}"],
            )
        prl.console_line("Graph: finished.")

        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Run).where(Run.id == run_id))
            run_final = res.scalar_one()

        summary = {
            "run_id": run_id,
            "log_dir": str(log_dir),
            "input_dir": str(input_dir),
            "uploaded_images": uploaded,
            "failed_seed_items": failed,
            "run_status": run_final.status,
            "graph_status": run_final.graph_status,
            "error_message": run_final.error_message,
            "pipeline_exception": pipeline_exc,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "final_state_keys": list(final_state.keys()) if final_state else [],
        }

        OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_JSON_PATH.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        prl.console_line(f"Summary JSON: {OUTPUT_JSON_PATH.resolve()}")

        success = (
            pipeline_exc is None
            and run_final.status == "completed"
            and run_final.graph_status == "completed"
        )
        if not success:
            prl.console_line(
                f"WARN: status={run_final.status} graph_status={run_final.graph_status}"
            )
        return 0 if success else 1

    finally:
        prl.deactivate()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
