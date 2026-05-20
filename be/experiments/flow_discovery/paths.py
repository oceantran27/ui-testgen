"""Centralized filesystem paths under the flow_discovery experiment package."""

from __future__ import annotations

from pathlib import Path

from experiments.flow_discovery.config import PACKAGE_ROOT

OUTPUTS_DIR = PACKAGE_ROOT / "outputs"
RAW_CAPTURE_DIR = OUTPUTS_DIR / "raw_capture"
GT_DIR = OUTPUTS_DIR / "ground_truth"
EVAL_DIR = OUTPUTS_DIR / "evaluation"
FIXTURES_DIR = PACKAGE_ROOT / "fixtures"

DEFAULT_RAW_CAPTURE_BASENAME = "raw_model_output.json"
DEFAULT_GROUND_TRUTH_REVIEWED_BASENAME = "ground_truth.reviewed.json"
EVALUATION_ARTIFACT_SUBDIR = "evaluation"
INPUT_BUILDER_SUBDIR = "input_builder"
GT_CONVERTER_SUBDIR = "gt_converter"
DEFAULT_GT_DRAFT_BASENAME = "ground_truth.draft.json"


def path_for_manifest(path: Path) -> str:
    """Path relative to this package root (POSIX, portable manifests)."""
    try:
        return path.relative_to(PACKAGE_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def raw_output_path(app_id: str, *, basename: str = "raw_flow_discovery_experiment_package.json") -> Path:
    return RAW_CAPTURE_DIR / app_id / basename


def ground_truth_draft_path(app_id: str) -> Path:
    return GT_DIR / app_id / "ground_truth.draft.json"


def ground_truth_reviewed_path(app_id: str) -> Path:
    return GT_DIR / app_id / "ground_truth.reviewed.json"


def evaluation_result_path(app_id: str) -> Path:
    return EVAL_DIR / app_id / "evaluation_result.json"


def work_dir_raw_output_path(work_dir: Path, *, basename: str = DEFAULT_RAW_CAPTURE_BASENAME) -> Path:
    return Path(work_dir) / basename


def work_dir_ground_truth_reviewed_path(work_dir: Path, *, basename: str = DEFAULT_GROUND_TRUTH_REVIEWED_BASENAME) -> Path:
    return Path(work_dir) / basename


def work_dir_evaluation_dir(work_dir: Path) -> Path:
    return Path(work_dir) / EVALUATION_ARTIFACT_SUBDIR


def work_dir_input_builder_dir(work_dir: Path) -> Path:
    return Path(work_dir) / INPUT_BUILDER_SUBDIR


def work_dir_gt_converter_dir(work_dir: Path) -> Path:
    return Path(work_dir) / GT_CONVERTER_SUBDIR


def input_builder_compressed_catalog_path(out_dir: Path) -> Path:
    return Path(out_dir) / "compressed_catalog_package.json"


def resolve_path_under_package(rel_or_abs: str | Path) -> Path:
    """Resolve a manifest or CLI path: absolute unchanged; otherwise relative to this package root."""
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p.resolve()
    return (PACKAGE_ROOT / p).resolve()
