"""Unit tests for module 1 run report helpers (latency aggregation)."""

from __future__ import annotations

from pathlib import Path

from experiments.ui_state_extraction.schemas.raw_output_manifest_schema import (
    ManifestItem,
    ModelConfigSnapshot,
)
from experiments.ui_state_extraction.services.module1_run_report_service import (
    aggregate_model_latency,
    build_timing_notes,
    configured_primary_avg_ms,
    write_raw_output_report_md,
)


def _item(
    *,
    status: str = "success",
    latency_ms: int | None = 100,
    provider: str | None = "gemini",
    model_name: str | None = "gemini-2.0-flash",
) -> ManifestItem:
    return ManifestItem(
        image_id="x",
        relative_path="a.png",
        raw_output_path="raw_outputs/a.raw.json",
        status=status,
        skip_reason=None,
        latency_ms=latency_ms,
        provider=provider,
        model_name=model_name,
    )


def test_aggregate_model_latency_single_model_three_calls() -> None:
    items = [
        _item(latency_ms=100),
        _item(latency_ms=200),
        _item(latency_ms=300),
    ]
    rows = aggregate_model_latency(items)
    assert len(rows) == 1
    r = rows[0]
    assert r.provider == "gemini"
    assert r.model_name == "gemini-2.0-flash"
    assert r.call_count == 3
    assert r.avg_latency_ms == 200.0
    assert r.min_latency_ms == 100
    assert r.max_latency_ms == 300


def test_aggregate_model_latency_two_buckets() -> None:
    items = [
        _item(latency_ms=50, provider="gemini", model_name="flash"),
        _item(latency_ms=150, provider="openai", model_name="gpt-5"),
    ]
    rows = aggregate_model_latency(items)
    assert len(rows) == 2
    by_key = {(x.provider, x.model_name): x for x in rows}
    assert by_key[("gemini", "flash")].avg_latency_ms == 50.0
    assert by_key[("openai", "gpt-5")].avg_latency_ms == 150.0


def test_aggregate_skips_no_latency_and_skipped_status() -> None:
    items = [
        _item(latency_ms=100),
        ManifestItem(
            image_id="s",
            relative_path="s.png",
            raw_output_path="raw_outputs/s.raw.json",
            status="skipped",
            skip_reason="raw_output_exists",
        ),
        _item(latency_ms=None, provider="gemini", model_name="flash", status="failed"),
    ]
    rows = aggregate_model_latency(items)
    assert len(rows) == 1
    assert rows[0].call_count == 1


def test_build_timing_notes_skipped_and_no_latency() -> None:
    items = [
        ManifestItem(
            image_id="s",
            relative_path="s.png",
            raw_output_path="raw_outputs/s.raw.json",
            status="skipped",
            skip_reason="x",
        ),
        _item(latency_ms=None, status="failed"),
    ]
    notes = build_timing_notes(items)
    assert any("Skipped items" in n for n in notes)
    assert any("no latency_ms" in n for n in notes)


def test_build_timing_notes_empty_run() -> None:
    notes = build_timing_notes([])
    assert len(notes) == 1
    assert "No images" in notes[0]


def test_configured_primary_avg_ms() -> None:
    cfg = ModelConfigSnapshot(
        configured_provider="gemini",
        configured_model_name="flash",
        prompt_name="p",
        prompt_version="v1",
        max_concurrency=3,
    )
    summary = aggregate_model_latency(
        [
            _item(latency_ms=100, provider="gemini", model_name="flash"),
            _item(latency_ms=300, provider="gemini", model_name="flash"),
        ]
    )
    assert configured_primary_avg_ms(summary, cfg) == 200.0
    assert configured_primary_avg_ms(summary, ModelConfigSnapshot(configured_provider="x")) is None


def test_write_raw_output_report_md_smoke(tmp_path: Path) -> None:
    p = tmp_path / "raw_output_report.md"
    write_raw_output_report_md(
        p,
        run_id="run_1",
        model_config=ModelConfigSnapshot(
            configured_provider="gemini",
            configured_model_name="flash",
            prompt_name="prompt_joint_screen_understanding_v1",
            prompt_version="v1",
            max_concurrency=2,
        ),
        model_latency_summary=aggregate_model_latency(
            [_item(latency_ms=80, provider="gemini", model_name="flash")]
        ),
        timing_notes=["Test note."],
        total_images_discovered=1,
        total_images_enqueued=1,
        total_success=1,
        total_failed=0,
        total_skipped=0,
    )
    text = p.read_text(encoding="utf-8")
    assert "Module 1" in text
    assert "gemini" in text
    assert "80.00" in text
