"""Persist RawFlowDiscoveryExperimentPackage as JSON."""

from __future__ import annotations

from pathlib import Path

from experiments.flow_discovery.io_utils import write_json_document
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def write_package(path: Path | str, package: RawFlowDiscoveryExperimentPackage) -> None:
    """Write canonical experiment envelope (single file contains raw + repaired payloads)."""

    write_json_document(Path(path), package.model_dump(mode="json", round_trip=True))


def write_sidecar_slices(
    base_out_path: Path | str,
    package: RawFlowDiscoveryExperimentPackage,
) -> tuple[Path, Path]:
    """Optional auxiliary JSON files for reviewers (raw-only + repaired-only)."""

    base = Path(base_out_path)
    stem = base.stem if base.suffix else base.name
    parent = base.parent
    raw_p = parent / f"{stem}.raw_slice.json"
    rep_p = parent / f"{stem}.repaired_slice.json"
    write_json_document(raw_p, package.raw_model_output)
    if package.repaired_model_output is not None:
        write_json_document(rep_p, package.repaired_model_output)
    return raw_p, rep_p
