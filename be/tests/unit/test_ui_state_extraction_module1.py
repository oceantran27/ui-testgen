"""Unit tests for experiments.ui_state_extraction (module 1 helpers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.ui_state_extraction.services.experiment_image_id_service import (
    build_experiment_image_id,
)
from experiments.ui_state_extraction.services.image_discovery_service import (
    ImageDiscoveryError,
    discover_images,
)
from experiments.ui_state_extraction.config import PACKAGE_ROOT
from experiments.ui_state_extraction.services.raw_output_persistence_service import (
    path_for_manifest,
    raw_output_file_path,
)
from experiments.ui_state_extraction.services.text_normalization_service import (
    short_hash,
    slug_text,
)


def test_slug_text_basic() -> None:
    assert slug_text("auth/login/File Name.PNG") == "auth_login_file_name_png"


def test_short_hash_stable() -> None:
    assert short_hash("auth/login/x.png", 8) == short_hash("auth/login/x.png", 8)


def test_build_experiment_image_id_short_relative_path() -> None:
    rid = build_experiment_image_id(relative_path="auth/login/login_001.png", stem="login_001")
    assert rid.image_id == "exp_auth_login_login_001"


def test_build_experiment_image_id_collides_when_max_len(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "experiments.ui_state_extraction.services.experiment_image_id_service.config.IMAGE_ID_MAX_LENGTH",
        28,
    )
    rel = "a/" * 30 + "dup.png"
    rid = build_experiment_image_id(relative_path=rel, stem="dup")
    assert rid.image_id.startswith("exp_dup_")
    assert len(rid.image_id) <= 28
    assert "_" in rid.image_id


def test_discover_local_skips_hidden_and_orders(tmp_path: Path) -> None:
    (tmp_path / "auth" / "login").mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n\x00"
    (tmp_path / "auth" / "login" / "z.png").write_bytes(png)
    (tmp_path / "auth" / "login" / "a.png").write_bytes(png)
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "x.png").write_bytes(png)

    found = discover_images(str(tmp_path), [".png"])
    rels = [r["relative_path"] for r in found]
    assert rels == ["auth/login/a.png", "auth/login/z.png"]


def test_discover_local_rejects_missing() -> None:
    with pytest.raises(ImageDiscoveryError, match="does not exist"):
        discover_images("/nonexistent/path/that/should/not/exist", [".png"])


def test_raw_output_file_path_mirror() -> None:
    p = raw_output_file_path(Path("/out"), "auth/login/x.png", "x")
    assert p.as_posix().endswith("auth/login/x.raw.json")


def test_path_for_manifest_relative_to_package() -> None:
    f = PACKAGE_ROOT / "raw_outputs" / "a.raw.json"
    assert path_for_manifest(f) == "raw_outputs/a.raw.json"
