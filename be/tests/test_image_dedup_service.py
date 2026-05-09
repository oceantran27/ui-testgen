"""Tests for pHash / SSIM image deduplication."""

import shutil
import tempfile
from pathlib import Path

from PIL import Image

from app.services.image_dedup_service import content_image_id, dedupe_image_paths, images_are_near_duplicate


def test_dedupe_identical_file_twice():
    tmp = Path(tempfile.mkdtemp())
    try:
        p = tmp / "a.png"
        Image.new("RGB", (40, 40), color=(10, 20, 30)).save(p)
        p2 = tmp / "b.png"
        shutil.copy(p, p2)
        r = dedupe_image_paths([str(p), str(p2)])
        assert len(r.canonical_paths) == 1
        assert r.canonical_image_ids[0] == r.input_path_to_image_id[str(p2)]
        assert str(p2) in r.dropped_paths or str(p) in r.dropped_paths
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_dedupe_two_visually_distinct_keeps_both():
    tmp = Path(tempfile.mkdtemp())
    try:
        p1 = tmp / "a.png"
        p2 = tmp / "b.png"
        Image.new("RGB", (200, 200), color=(255, 0, 0)).save(p1)
        Image.new("RGB", (200, 200), color=(0, 0, 255)).save(p2)
        r = dedupe_image_paths([str(p1), str(p2)])
        assert len(r.canonical_paths) == 2
        assert len(r.dropped_paths) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_content_image_id_stable():
    im = Image.new("RGB", (10, 10), color=(255, 0, 0))
    id1 = content_image_id(im)
    id2 = content_image_id(im)
    assert id1 == id2


def test_same_image_self_duplicate():
    im = Image.new("RGB", (64, 64), color=(128, 128, 128))
    assert images_are_near_duplicate(im, im.copy()) is True
