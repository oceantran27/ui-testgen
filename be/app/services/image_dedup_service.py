"""Near-duplicate UI screenshots via perceptual hash and SSIM.

A pair counts as duplicate only when **both** conditions hold (avoids false merges
e.g. two different solid-color placeholders that still score high on one metric alone):

- pHash Hamming similarity strictly **>** ``phash_threshold_pct`` (default 95)
- SSIM **>=** ``ssim_threshold`` (default 0.95) on aligned grayscale previews
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import imagehash
except ImportError:  # pragma: no cover
    imagehash = None  # type: ignore

try:
    from skimage.metrics import structural_similarity as skimage_ssim
except ImportError:  # pragma: no cover
    skimage_ssim = None  # type: ignore


def _ensure_rgb(pil: Image.Image) -> Image.Image:
    if pil.mode in ("RGB", "L"):
        if pil.mode == "L":
            return pil.convert("RGB")
        return pil
    if pil.mode in ("RGBA", "P", "PA"):
        if pil.mode in ("P", "PA"):
            pil = pil.convert("RGBA")
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1] if pil.mode == "RGBA" else None)
        return bg
    return pil.convert("RGB")


def _normalized_png_bytes(pil: Image.Image) -> bytes:
    rgb = _ensure_rgb(pil)
    buf = io.BytesIO()
    rgb.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def content_image_id(pil: Image.Image) -> str:
    """Stable sha256 hex id from normalized PNG bytes."""
    return hashlib.sha256(_normalized_png_bytes(pil)).hexdigest()


def _phash_or_none(pil: Image.Image) -> Any:
    if imagehash is None:
        raise RuntimeError("imagehash package is required for image deduplication")
    return imagehash.phash(_ensure_rgb(pil))


def _phash_similarity_pct(hash_a: Any, hash_b: Any) -> float:
    dist = hash_a - hash_b
    bits = int(np.asarray(hash_a.hash).size)
    if bits <= 0:
        bits = 64
    return 100.0 * (1.0 - float(dist) / float(bits))


def _to_gray_float_array(pil: Image.Image, size: int = 256) -> np.ndarray:
    g = _ensure_rgb(pil).convert("L").resize((size, size), Image.Resampling.LANCZOS)
    return np.asarray(g, dtype=np.float64) / 255.0


def _structural_similarity(x: np.ndarray, y: np.ndarray) -> float:
    if x.shape != y.shape:
        raise ValueError("SSIM inputs must have same shape")
    if skimage_ssim is not None:
        return float(skimage_ssim(x, y, data_range=1.0))
    a, b = x.flatten(), y.flatten()
    if np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 1.0 if np.allclose(a, b) else 0.0
    return float(np.corrcoef(a, b)[0, 1])


def images_are_near_duplicate(
    pil_a: Image.Image,
    pil_b: Image.Image,
    *,
    phash_threshold_pct: float = 95.0,
    ssim_threshold: float = 0.95,
) -> bool:
    """True only when both pHash similarity and SSIM meet thresholds (reduces false merges)."""
    ha = _phash_or_none(pil_a)
    hb = _phash_or_none(pil_b)
    ph_ok = _phash_similarity_pct(ha, hb) > phash_threshold_pct
    xa = _to_gray_float_array(pil_a)
    xb = _to_gray_float_array(pil_b)
    ssim_ok = _structural_similarity(xa, xb) >= ssim_threshold
    return ph_ok and ssim_ok


@dataclass
class DedupResult:
    canonical_paths: list[str] = field(default_factory=list)
    canonical_image_ids: list[str] = field(default_factory=list)
    input_path_to_image_id: dict[str, str] = field(default_factory=dict)
    dropped_paths: list[str] = field(default_factory=list)


def dedupe_image_paths(
    paths: list[str],
    *,
    phash_threshold_pct: float = 95.0,
    ssim_threshold: float = 0.95,
) -> DedupResult:
    """
    Greedy deduplication: first path is canonical; later paths matching any
    canonical (pHash similarity > threshold **and** SSIM >= ssim_threshold) map to that id.
    """
    if not paths:
        return DedupResult()
    if imagehash is None:
        raise RuntimeError("imagehash is not installed")

    result = DedupResult()
    canonical_pils: list[Image.Image] = []

    for p in paths:
        try:
            pil = Image.open(p)
            pil.load()
            pil = pil.copy()
        except Exception as exc:
            logger.error("dedupe: failed to open %s: %s", p, exc)
            raise

        matched_id: str | None = None
        for idx, canon in enumerate(canonical_pils):
            try:
                if images_are_near_duplicate(
                    pil,
                    canon,
                    phash_threshold_pct=phash_threshold_pct,
                    ssim_threshold=ssim_threshold,
                ):
                    matched_id = result.canonical_image_ids[idx]
                    break
            except Exception as exc:
                logger.warning("dedupe compare failed for %s vs canonical[%s]: %s", p, idx, exc)

        if matched_id is not None:
            result.input_path_to_image_id[p] = matched_id
            result.dropped_paths.append(p)
            pil.close()
            continue

        cid = content_image_id(pil)
        result.canonical_paths.append(p)
        result.canonical_image_ids.append(cid)
        result.input_path_to_image_id[p] = cid
        canonical_pils.append(pil)

    for im in canonical_pils:
        try:
            im.close()
        except Exception:
            pass

    return result
