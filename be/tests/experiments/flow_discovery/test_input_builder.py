from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.flow_discovery.adapters import system_readonly_adapter
from experiments.flow_discovery.input_builder.joint_raw_loader import JointRawLoader, iter_joint_input_json_paths
from experiments.flow_discovery.input_builder.joint_raw_normalizer import JointRawNormalizer
from experiments.flow_discovery.schemas.input_builder_schema import JointRawFileRecord


def test_iter_joint_input_json_skips_summary(tmp_path: Path) -> None:
    (tmp_path / "a.raw.json").write_text("{}", encoding="utf-8")
    (tmp_path / "summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "compressed_catalog_package.json").write_text("{}", encoding="utf-8")
    paths = iter_joint_input_json_paths(tmp_path)
    assert [p.name for p in paths] == ["a.raw.json"]


def test_loader_parse_failure_non_strict(tmp_path: Path) -> None:
    (tmp_path / "bad.raw.json").write_text("{not json", encoding="utf-8")
    recs, warns = JointRawLoader().load_dir(str(tmp_path), strict=False)
    assert recs == []
    assert any("RAW_JSON_PARSE_FAILED" in w for w in warns)


def test_loader_image_map_source_id(tmp_path: Path) -> None:
    (tmp_path / "x.raw.json").write_text(
        json.dumps({"ui_state": {}, "screen_intents": {}}),
        encoding="utf-8",
    )
    meta = tmp_path / "meta"
    meta.mkdir()
    mpath = meta / "im.json"
    mpath.write_text(
        json.dumps({"x.raw.json": {"source_image_id": "mapped_id", "original_filename": "a.png"}}),
        encoding="utf-8",
    )
    recs, _ = JointRawLoader().load_dir(str(tmp_path), str(mpath))
    assert len(recs) == 1
    assert recs[0].source_image_id == "mapped_id"
    assert recs[0].original_filename == "a.png"


def test_normalizer_shapes() -> None:
    norm = JointRawNormalizer()
    base_ui = {"screen_purpose": "p", "domain": "d", "screen_type": "form"}
    base_si = {"screen_behaviour_intents": [], "unresolved_screen_groups": []}

    r1 = norm.normalize(
        JointRawFileRecord(
            raw_file_path="/x",
            raw_file_name="f.json",
            source_image_id="s1",
            raw_payload={"ui_state": base_ui, "screen_intents": base_si},
        ),
    )
    assert r1.ui_state.get("screen_purpose") == "p"

    r2 = norm.normalize(
        JointRawFileRecord(
            raw_file_path="/x",
            raw_file_name="f.json",
            source_image_id="s1",
            raw_payload={"parsed_output": {"ui_state": base_ui, "screen_intents": base_si}},
        ),
    )
    assert r2.ui_state.get("domain") == "d"

    inner = json.dumps({"ui_state": base_ui, "screen_intents": base_si})
    r3 = norm.normalize(
        JointRawFileRecord(
            raw_file_path="/x",
            raw_file_name="f.json",
            source_image_id="s1",
            raw_payload={"raw_text": inner},
        ),
    )
    assert r3.screen_intents.get("screen_behaviour_intents") == []

    r4 = norm.normalize(
        JointRawFileRecord(
            raw_file_path="/x",
            raw_file_name="f.json",
            source_image_id="s1",
            raw_payload={"ui_state": {}},
        ),
    )
    assert "MISSING_SCREEN_INTENTS" in r4.warnings


def test_input_build_runner_end_to_end(fixture_demoauth_dir: Path, tmp_path: Path) -> None:
    from experiments.flow_discovery.input_builder.input_build_runner import FlowDiscoveryInputBuildRunner

    raw_dir = fixture_demoauth_dir / "raw_joint_outputs"
    assert raw_dir.is_dir()
    out = tmp_path / "ib"
    runner = FlowDiscoveryInputBuildRunner()
    res = runner.run(app_id="demoauth", raw_joint_dir=str(raw_dir), out_dir=str(out))
    assert res.compressed_catalog_package.get("catalog_version") == "compressed_catalog_v3"
    assert res.compressed_catalog_package.get("catalog_purpose") == "global_flow_discovery_input"
    cards = res.compressed_catalog_package.get("compressed_catalog") or []
    assert len(cards) == 3
    ok, err = system_readonly_adapter.validate_discovery_catalog_dimensions(res.compressed_catalog_package)
    assert ok and err is None
    assert (out / "build_report.json").is_file()


def test_run_one_from_joint_raw_mock_llm(
    fixture_demoauth_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from app.model_providers.base import ModelCallStatus
    from app.model_providers.schemas import GlobalFlowDiscoveryResult

    from experiments.flow_discovery.pipeline_runner import run_one_from_joint_raw_async
    from experiments.flow_discovery.raw_capture import raw_flow_discovery_runner as rmod

    async def fake_caller(**_kwargs: object):
        class R:
            status = ModelCallStatus.SUCCESS
            parsed_output = GlobalFlowDiscoveryResult()
            provider = "stub"
            model_name = "stub"
            latency_ms = 1
            error = None

        return R()

    monkeypatch.setattr(rmod, "default_model_caller", fake_caller)
    raw_dir = fixture_demoauth_dir / "raw_joint_outputs"

    async def _run() -> None:
        outcome = await run_one_from_joint_raw_async(
            app_id="demoauth",
            raw_joint_dir=raw_dir,
            work_dir=tmp_path,
            validate_screen_count=True,
        )
        assert outcome.ok, outcome.error_message
        assert outcome.raw_path.is_file()
        assert outcome.ground_truth_draft_path.is_file()

    asyncio.run(_run())


def test_build_compressed_cli_main(fixture_demoauth_dir: Path, tmp_path: Path) -> None:
    from experiments.flow_discovery.cli import main

    raw_dir = fixture_demoauth_dir / "raw_joint_outputs"
    out = tmp_path / "out"
    code = main(
        [
            "build-compressed",
            "--app-id",
            "demoauth",
            "--raw-joint-dir",
            str(raw_dir),
            "--out-dir",
            str(out),
        ],
    )
    assert code == 0
    assert (out / "compressed_catalog_package.json").is_file()


def test_cli_build_compressed_uses_config_defaults(
    fixture_demoauth_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from experiments.flow_discovery import config as cfg
    from experiments.flow_discovery.cli import main

    out = tmp_path / "from_config"
    monkeypatch.setattr(cfg, "CLI_APP_ID", "demoauth")
    monkeypatch.setattr(cfg, "CLI_RAW_JOINT_DIR", str((fixture_demoauth_dir / "raw_joint_outputs").resolve()))
    monkeypatch.setattr(cfg, "CLI_INPUT_BUILDER_OUT_DIR", str(out.resolve()))
    monkeypatch.setattr(cfg, "CLI_IMAGE_MAP_PATH", None)
    monkeypatch.setattr(cfg, "CLI_INPUT_BUILDER_STRICT", False)

    assert main(["build-compressed"]) == 0
    assert (out / "compressed_catalog_package.json").is_file()


def test_print_config_cli_exits_zero() -> None:
    from experiments.flow_discovery.cli import main

    assert main(["print-config"]) == 0
