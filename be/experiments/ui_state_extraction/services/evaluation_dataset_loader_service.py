"""Pair module-1 raw outputs with module-2 temp ground truth for evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import ExperimentRawOutputDocument
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import TempGroundTruthDocument
from experiments.ui_state_extraction.services.ground_truth_loader_service import load_temp_ground_truth
from experiments.ui_state_extraction.services.raw_output_persistence_service import path_for_manifest


def normalize_pair_key_relative_path(relative_path: str) -> str:
    return (relative_path or "").replace("\\", "/").strip()


def discover_raw_output_paths(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.rglob("*.raw.json"), key=lambda p: p.as_posix().lower())


def discover_temp_gt_paths(gt_dir: Path) -> list[Path]:
    return sorted(gt_dir.rglob("*.temp_gt.json"), key=lambda p: p.as_posix().lower())


def load_raw_output_document(path: Path) -> tuple[ExperimentRawOutputDocument | None, str | None]:
    try:
        import json

        with open(path, encoding="utf-8") as f:
            payload: dict[str, Any] = json.load(f)
        return ExperimentRawOutputDocument.model_validate(payload), None
    except Exception as exc:  # noqa: BLE001 — surface as skip reason
        return None, str(exc)


@dataclass
class EvaluablePair:
    raw_path: Path
    raw_doc: ExperimentRawOutputDocument
    ground_truth: TempGroundTruthDocument
    gt_path: Path


@dataclass
class DatasetLoadResult:
    pairs: list[EvaluablePair]
    skipped: list[dict[str, Any]]
    total_raw_outputs: int
    total_ground_truth_files: int
    total_matched_pairs: int


@dataclass(frozen=True)
class _GtEntry:
    doc: TempGroundTruthDocument
    path: Path


def _index_ground_truths(
    gt_paths: list[Path],
    *,
    skipped: list[dict[str, Any]],
) -> tuple[dict[str, _GtEntry], dict[str, _GtEntry]]:
    by_rel: dict[str, _GtEntry] = {}
    by_image_id: dict[str, _GtEntry] = {}
    for p in gt_paths:
        gt, err = load_temp_ground_truth(p)
        if gt is None:
            skipped.append(
                {
                    "reason": "ground_truth_invalid",
                    "relative_path": path_for_manifest(p),
                    "detail": err or "",
                }
            )
            continue
        entry = _GtEntry(doc=gt, path=p)
        rel_k = normalize_pair_key_relative_path(gt.image.relative_path)
        if rel_k:
            by_rel[rel_k] = entry
        iid = (gt.image.image_id or "").strip()
        if iid:
            by_image_id[iid] = entry
    return by_rel, by_image_id


def load_evaluation_dataset(
    *,
    raw_dir: Path,
    gt_dir: Path,
) -> DatasetLoadResult:
    """
    Pair raw outputs with temp GT. Only pairs that pass eligibility are in ``pairs``;
    others are listed in ``skipped`` with structured reasons.
    """
    skipped: list[dict[str, Any]] = []
    raw_paths = discover_raw_output_paths(raw_dir)
    gt_paths = discover_temp_gt_paths(gt_dir)
    by_rel, by_image_id = _index_ground_truths(gt_paths, skipped=skipped)

    pairs: list[EvaluablePair] = []
    matched = 0

    for raw_path in raw_paths:
        raw_doc, err = load_raw_output_document(raw_path)
        rel_manifest = path_for_manifest(raw_path)
        if raw_doc is None:
            skipped.append(
                {
                    "reason": "raw_output_invalid",
                    "relative_path": rel_manifest,
                    "detail": err or "",
                }
            )
            continue

        rel_k = normalize_pair_key_relative_path(raw_doc.image.relative_path)
        iid = (raw_doc.image.image_id or "").strip()

        entry: _GtEntry | None = None
        if rel_k and rel_k in by_rel:
            entry = by_rel[rel_k]
        elif iid and iid in by_image_id:
            entry = by_image_id[iid]

        if entry is None:
            skipped.append(
                {
                    "reason": "no_ground_truth_file",
                    "image_id": raw_doc.image.image_id,
                    "relative_path": raw_doc.image.relative_path,
                    "raw_output_path": rel_manifest,
                }
            )
            continue

        gt = entry.doc
        gt_path = entry.path
        matched += 1

        if raw_doc.model_call.status != "success":
            skipped.append(
                {
                    "reason": "raw_output_failed",
                    "image_id": raw_doc.image.image_id,
                    "relative_path": raw_doc.image.relative_path,
                    "raw_output_path": rel_manifest,
                }
            )
            continue
        if raw_doc.raw_model_output is None:
            skipped.append(
                {
                    "reason": "raw_output_missing_payload",
                    "image_id": raw_doc.image.image_id,
                    "relative_path": raw_doc.image.relative_path,
                    "raw_output_path": rel_manifest,
                }
            )
            continue

        pairs.append(
            EvaluablePair(
                raw_path=raw_path,
                raw_doc=raw_doc,
                ground_truth=gt,
                gt_path=gt_path,
            )
        )

    return DatasetLoadResult(
        pairs=pairs,
        skipped=skipped,
        total_raw_outputs=len(raw_paths),
        total_ground_truth_files=len(gt_paths),
        total_matched_pairs=matched,
    )


def dry_run_stats(
    *,
    raw_dir: Path,
    gt_dir: Path,
) -> dict[str, Any]:
    """Counts only (no metric computation)."""
    raw_paths = discover_raw_output_paths(raw_dir)
    gt_paths = discover_temp_gt_paths(gt_dir)
    skipped: list[dict[str, Any]] = []
    by_rel, by_image_id = _index_ground_truths(gt_paths, skipped=skipped)

    matched = 0
    for raw_path in raw_paths:
        raw_doc, err = load_raw_output_document(raw_path)
        if raw_doc is None:
            continue
        rel_k = normalize_pair_key_relative_path(raw_doc.image.relative_path)
        iid = (raw_doc.image.image_id or "").strip()
        entry: _GtEntry | None = None
        if rel_k and rel_k in by_rel:
            entry = by_rel[rel_k]
        elif iid and iid in by_image_id:
            entry = by_image_id[iid]
        if entry is not None:
            matched += 1

    return {
        "total_raw_outputs": len(raw_paths),
        "total_ground_truth_files": len(gt_paths),
        "total_matched_pairs": matched,
        "invalid_ground_truth_files": sum(1 for s in skipped if s.get("reason") == "ground_truth_invalid"),
    }
