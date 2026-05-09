"""Load paired ground-truth / generated JSON files by image_id."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from experiments.intent_coverage_judge.schemas import GeneratedScreenFile, GroundTruthScreenFile

logger = logging.getLogger(__name__)

GROUND_TRUTH_BUNDLE_FILENAME = "ground_truth.json"


def parse_ground_truth_bundle(path: Path) -> dict[str, GroundTruthScreenFile]:
    """
    Load ``GROUND_TRUTH_BUNDLE_FILENAME``-shaped bundle: root object with ``screens`` array.

    Each entry must validate as ``GroundTruthScreenFile`` (extra keys allowed). Duplicate
    ``image_id`` in the array: earlier wins after warning.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        logger.warning("Bundle %s: root must be object", path)
        return {}
    screens = raw.get("screens")
    if not isinstance(screens, list):
        logger.warning("Bundle %s: missing or invalid screens array", path)
        return {}
    out: dict[str, GroundTruthScreenFile] = {}
    for idx, row in enumerate(screens):
        if not isinstance(row, dict):
            logger.warning("Bundle %s: skip screens[%d] not an object", path, idx)
            continue
        iid = row.get("image_id")
        if not iid or not isinstance(iid, str):
            logger.warning("Bundle %s: skip screens[%d] missing string image_id", path, idx)
            continue
        if iid in out:
            logger.warning(
                "Bundle %s: duplicate image_id %s in screens[%d] (keeping first)",
                path,
                iid,
                idx,
            )
            continue
        try:
            out[iid] = GroundTruthScreenFile.model_validate(row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bundle %s: skip GT image_id=%s: %s", path, iid, exc)
    return out


def _load_json_files(directory: Path) -> dict[str, dict]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Not a directory: {directory}")
    by_id: dict[str, dict] = {}
    for p in sorted(directory.glob("*.json")):
        if p.name == GROUND_TRUTH_BUNDLE_FILENAME:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skip %s: %s", p, exc)
            continue
        if not isinstance(data, dict):
            logger.warning("Skip %s: root must be object", p)
            continue
        iid = data.get("image_id")
        if not iid or not isinstance(iid, str):
            logger.warning("Skip %s: missing string image_id", p)
            continue
        if iid in by_id:
            logger.warning("Duplicate image_id %s in %s (earlier file wins)", iid, p)
            continue
        by_id[iid] = data
    return by_id


def load_ground_truth_dir(directory: Path) -> dict[str, GroundTruthScreenFile]:
    bundle_path = directory / GROUND_TRUTH_BUNDLE_FILENAME
    if bundle_path.is_file():
        return parse_ground_truth_bundle(bundle_path)

    raw = _load_json_files(directory)
    out: dict[str, GroundTruthScreenFile] = {}
    for iid, data in raw.items():
        try:
            out[iid] = GroundTruthScreenFile.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip GT image_id=%s: %s", iid, exc)
    return out


def load_generated_dir(directory: Path) -> dict[str, GeneratedScreenFile]:
    raw = _load_json_files(directory)
    out: dict[str, GeneratedScreenFile] = {}
    for iid, data in raw.items():
        try:
            out[iid] = GeneratedScreenFile.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip generated image_id=%s: %s", iid, exc)
    return out


def pair_screens(
    gt_by_id: dict[str, GroundTruthScreenFile],
    gen_by_id: dict[str, GeneratedScreenFile],
    *,
    strict: bool,
    skip_unpaired: bool,
) -> tuple[list[str], list[str]]:
    """
    Return (paired_image_ids, error_messages).

    If ``strict``, any mismatch between key sets appends errors (unless skip_unpaired
    drops unpaired ids and logs only).
    """
    errors: list[str] = []
    gt_keys = set(gt_by_id.keys())
    gen_keys = set(gen_by_id.keys())
    only_gt = gt_keys - gen_keys
    only_gen = gen_keys - gt_keys
    if only_gt or only_gen:
        msg = (
            f"GT-only image_ids ({len(only_gt)}): {sorted(only_gt)[:20]}"
            f"{'...' if len(only_gt) > 20 else ''}; "
            f"generated-only ({len(only_gen)}): {sorted(only_gen)[:20]}"
            f"{'...' if len(only_gen) > 20 else ''}"
        )
        if strict and not skip_unpaired:
            errors.append(msg)
        else:
            logger.warning(msg)
    paired = sorted(gt_keys & gen_keys)
    if skip_unpaired:
        return paired, errors
    if strict and (only_gt or only_gen):
        return [], errors
    return paired, errors
