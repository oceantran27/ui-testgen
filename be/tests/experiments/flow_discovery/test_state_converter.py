from __future__ import annotations

from pathlib import Path

from experiments.flow_discovery.gt_converter.state_converter import build_states_from_compressed_catalog
from experiments.flow_discovery.io_utils import read_json_document


def test_fixture_catalog_maps_catalog_ids_to_stable_gt_suffixes(fixture_demoauth_dir: Path) -> None:
    compressed_path = fixture_demoauth_dir / "compressed_catalog_package.json"
    pkg = read_json_document(compressed_path)
    states, catalog_to_gt, _index = build_states_from_compressed_catalog("demoauth", pkg)

    assert len(states) == len(catalog_to_gt) == len(pkg["compressed_catalog"])
    for st in states:
        assert str(st.gt_state_id).startswith("gt_s_demoauth_")
        assert st.catalog_state_id in catalog_to_gt
        bucket = getattr(st.visible_evidence, "headings", None)
        texts = getattr(st.visible_evidence, "texts", None)
        assert bucket is not None and texts is not None

