"""Tests for CLIP + ChromaDB image deduplication."""

import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.services.image_dedup_service import content_image_id, dedupe_image_paths


def test_dedupe_identical_file_twice_with_mock_encoder():
    """Same bytes => same content id; mock CLIP returns identical embedding => one canonical."""
    tmp = Path(tempfile.mkdtemp())
    try:
        p = tmp / "a.png"
        Image.new("RGB", (40, 40), color=(10, 20, 30)).save(p)
        p2 = tmp / "b.png"
        shutil.copy(p, p2)
        fixed = np.random.randn(512).astype(np.float32)
        fixed = fixed / np.linalg.norm(fixed)

        def _enc(_pil: Image.Image) -> np.ndarray:
            return fixed.copy()

        r = dedupe_image_paths([str(p), str(p2)], encode_fn=_enc, cosine_threshold=0.92)
        assert len(r.canonical_paths) == 1
        assert r.canonical_image_ids[0] == r.input_path_to_image_id[str(p2)]
        dropped = str(p2) if str(p2) in r.dropped_paths else str(p)
        assert r.dropped_match_reason[dropped] == "clip_cosine"
        assert r.dropped_metrics[dropped]["cosine_similarity"] > 0.92
        assert "cosine_similarity" in r.dropped_metrics[dropped]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dedupe_two_distinct_mock_embeddings_keeps_both():
    tmp = Path(tempfile.mkdtemp())
    try:
        p1 = tmp / "a.png"
        p2 = tmp / "b.png"
        Image.new("RGB", (20, 20), color=(255, 0, 0)).save(p1)
        Image.new("RGB", (20, 20), color=(0, 0, 255)).save(p2)
        a = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(512, dtype=np.float32)
        b[1] = 1.0
        seq = iter([a, b])

        def _enc(_pil: Image.Image) -> np.ndarray:
            return next(seq).copy()

        r = dedupe_image_paths([str(p1), str(p2)], encode_fn=_enc, cosine_threshold=0.92)
        assert len(r.canonical_paths) == 2
        assert len(r.dropped_paths) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dedupe_orthogonal_vectors_not_dropped_at_high_threshold():
    tmp = Path(tempfile.mkdtemp())
    try:
        p1 = tmp / "a.png"
        p2 = tmp / "b.png"
        Image.new("RGB", (10, 10), color=(1, 2, 3)).save(p1)
        Image.new("RGB", (10, 10), color=(4, 5, 6)).save(p2)
        a = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(512, dtype=np.float32)
        b[1] = 1.0
        seq = iter([a.copy(), b.copy()])

        def _enc(_pil: Image.Image) -> np.ndarray:
            return next(seq).copy()

        r = dedupe_image_paths([str(p1), str(p2)], encode_fn=_enc, cosine_threshold=0.9999)
        assert len(r.canonical_paths) == 2
        assert len(r.dropped_paths) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dedupe_nearly_parallel_vectors_dropped_at_defaultish_threshold():
    tmp = Path(tempfile.mkdtemp())
    try:
        p1 = tmp / "a.png"
        p2 = tmp / "b.png"
        Image.new("RGB", (10, 10), color=(1, 2, 3)).save(p1)
        Image.new("RGB", (10, 10), color=(4, 5, 6)).save(p2)
        v = np.zeros(512, dtype=np.float32)
        v[0] = 1.0
        w = v + 1e-6
        w = w / np.linalg.norm(w)
        seq = iter([v.copy(), w.copy()])

        def _enc(_pil: Image.Image) -> np.ndarray:
            return next(seq).copy()

        r = dedupe_image_paths([str(p1), str(p2)], encode_fn=_enc, cosine_threshold=0.92)
        assert len(r.canonical_paths) == 1
        assert len(r.dropped_paths) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_content_image_id_stable():
    im = Image.new("RGB", (10, 10), color=(255, 0, 0))
    id1 = content_image_id(im)
    id2 = content_image_id(im)
    assert id1 == id2
