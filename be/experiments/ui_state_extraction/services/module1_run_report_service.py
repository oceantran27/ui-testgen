"""Module 1 run report: model config snapshot, latency aggregation, Markdown report."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from app.core.config import settings

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.schemas.raw_output_manifest_schema import (
    ManifestItem,
    ModelConfigSnapshot,
    ModelLatencySummary,
)


def build_model_config_snapshot() -> ModelConfigSnapshot:
    return ModelConfigSnapshot(
        configured_provider=getattr(settings, "JOINT_SCREEN_UNDERSTANDING_PROVIDER", "") or "",
        configured_model_name=getattr(settings, "JOINT_SCREEN_UNDERSTANDING_MODEL_NAME", "") or "",
        prompt_name=config.PROMPT_NAME,
        prompt_version="v1",
        max_concurrency=max(1, config.MAX_CONCURRENCY),
    )


def aggregate_model_latency(items: Iterable[ManifestItem]) -> list[ModelLatencySummary]:
    """Bucket by actual (provider, model_name) from items with a recorded latency."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    for it in items:
        if it.latency_ms is None:
            continue
        prov = (it.provider or "").strip()
        mname = (it.model_name or "").strip()
        if not prov or not mname:
            continue
        buckets[(prov, mname)].append(it.latency_ms)

    out: list[ModelLatencySummary] = []
    for (prov, mname), latencies in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        if not latencies:
            continue
        n = len(latencies)
        total = sum(latencies)
        out.append(
            ModelLatencySummary(
                provider=prov,
                model_name=mname,
                call_count=n,
                avg_latency_ms=round(total / n, 2),
                min_latency_ms=min(latencies),
                max_latency_ms=max(latencies),
            )
        )
    return out


def build_timing_notes(items: Iterable[ManifestItem]) -> list[str]:
    """Human-readable notes about what was excluded from latency averages."""
    items_list = list(items)
    if not items_list:
        return ["No images were processed in this run."]
    skipped = sum(1 for i in items_list if i.status == "skipped")
    no_latency = sum(
        1
        for i in items_list
        if i.status in ("success", "failed") and i.latency_ms is None
    )
    notes: list[str] = []
    if skipped:
        notes.append(f"Skipped items ({skipped}) are excluded from latency averages.")
    if no_latency:
        notes.append(
            f"{no_latency} call(s) have no latency_ms "
            "(typically an exception before the model adapter returned)."
        )
    if not notes:
        notes.append("All completed model calls include latency_ms.")
    return notes


def configured_primary_avg_ms(
    summary: list[ModelLatencySummary],
    model_cfg: ModelConfigSnapshot,
) -> float | None:
    """Average latency for the configured primary provider/model if present in summary."""
    prov = model_cfg.configured_provider
    mname = model_cfg.configured_model_name
    for row in summary:
        if row.provider == prov and row.model_name == mname:
            return row.avg_latency_ms
    return None


def write_raw_output_report_md(
    path: Path,
    *,
    run_id: str,
    model_config: ModelConfigSnapshot,
    model_latency_summary: list[ModelLatencySummary],
    timing_notes: list[str],
    total_images_discovered: int,
    total_images_enqueued: int,
    total_success: int,
    total_failed: int,
    total_skipped: int,
) -> None:
    lines: list[str] = [
        "# UI State Extraction — Module 1 (raw outputs) report",
        "",
        "## Model configuration",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Configured provider | `{model_config.configured_provider}` |",
        f"| Configured model | `{model_config.configured_model_name}` |",
        f"| Prompt | `{model_config.prompt_name}` ({model_config.prompt_version}) |",
        f"| Max concurrency | {model_config.max_concurrency} |",
        f"| Run ID | `{run_id}` |",
        "",
    ]
    primary_avg = configured_primary_avg_ms(model_latency_summary, model_config)
    if primary_avg is not None:
        lines.extend(
            [
                f"**Configured model mean latency:** {primary_avg:.2f} ms per request "
                "(among calls attributed to that provider/model).",
                "",
            ]
        )

    lines.extend(
        [
            "## Latency by actual provider/model",
            "",
            "Per-image latency comes from `ModelResponse.latency_ms` (provider round-trip). "
            "If fallback used another model, it appears as a separate row.",
            "",
        ]
    )
    if model_latency_summary:
        lines.extend(
            [
                "| Provider | Model | Calls | Avg ms | Min ms | Max ms |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in model_latency_summary:
            lines.append(
                f"| `{row.provider}` | `{row.model_name}` | {row.call_count} | "
                f"{row.avg_latency_ms:.2f} | {row.min_latency_ms} | {row.max_latency_ms} |"
            )
    else:
        lines.append("_No latency samples (e.g. all skipped or no completed model calls)._")
    lines.append("")

    lines.extend(
        [
            "## Run totals",
            "",
            "| Item | Count |",
            "|---|---:|",
            f"| Images discovered | {total_images_discovered} |",
            f"| Images enqueued | {total_images_enqueued} |",
            f"| Success | {total_success} |",
            f"| Failed | {total_failed} |",
            f"| Skipped | {total_skipped} |",
            "",
            "## Timing notes",
            "",
        ]
    )
    for n in timing_notes:
        lines.append(f"- {n}")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
