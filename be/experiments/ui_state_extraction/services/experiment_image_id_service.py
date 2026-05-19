from __future__ import annotations

from dataclasses import dataclass

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.services.text_normalization_service import (
    short_hash,
    slug_text,
)


@dataclass(frozen=True)
class ResolvedImageId:
    image_id: str


def build_experiment_image_id(*, relative_path: str, stem: str) -> ResolvedImageId:
    """stable image_id: exp_ + slug(path_without_extension), or shortened with hash."""
    rel_norm = relative_path.replace("\\", "/")
    path_wo_ext: str
    if "." in rel_norm:
        path_wo_ext = rel_norm.rsplit(".", 1)[0]
    else:
        path_wo_ext = rel_norm
    base = "exp_" + slug_text(path_wo_ext)
    if len(base) <= config.IMAGE_ID_MAX_LENGTH:
        return ResolvedImageId(image_id=base)
    stem_part = slug_text(stem) or "img"
    suffix = short_hash(rel_norm, 8)
    short_id = f"exp_{stem_part}_{suffix}"
    if len(short_id) > config.IMAGE_ID_MAX_LENGTH:
        short_id = short_id[: config.IMAGE_ID_MAX_LENGTH].rstrip("_")
    return ResolvedImageId(image_id=short_id)
