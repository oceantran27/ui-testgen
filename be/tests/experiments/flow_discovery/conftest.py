from __future__ import annotations

from pathlib import Path

import pytest

from experiments.flow_discovery.config import PACKAGE_ROOT

FIXTURE_DEMOAUTH = PACKAGE_ROOT / "fixtures" / "demoauth"


@pytest.fixture
def fixture_demoauth_dir() -> Path:
    assert FIXTURE_DEMOAUTH.is_dir(), f"missing_fixture_dir:{FIXTURE_DEMOAUTH.as_posix()}"
    return FIXTURE_DEMOAUTH


@pytest.fixture
def fixture_demoauth_raw(fixture_demoauth_dir: Path) -> Path:
    p = fixture_demoauth_dir / "raw_model_output.json"
    assert p.is_file(), f"missing:{p}"
    return p


@pytest.fixture
def fixture_demoauth_gt(fixture_demoauth_dir: Path) -> Path:
    p = fixture_demoauth_dir / "ground_truth.reviewed.sample.json"
    assert p.is_file(), f"missing:{p}"
    return p
