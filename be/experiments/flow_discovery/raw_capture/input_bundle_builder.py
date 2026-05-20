"""Load compressed_catalog_package.json and build LLM-facing discovery catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from experiments.flow_discovery.adapters import system_readonly_adapter
from experiments.flow_discovery.io_utils import read_json_document
from experiments.flow_discovery.paths import path_for_manifest


@dataclass
class DiscoveryInputBundle:
    compressed_catalog_package: Dict[str, Any]
    llm_discovery_catalog: Dict[str, Any]
    input_refs: Dict[str, Any]


def load_compressed_catalog_package(path: Path | str) -> Dict[str, Any]:
    """Load JSON dict from disk (catalog root object)."""

    resolved = Path(path).resolve()
    return read_json_document(resolved)


def build_discovery_input_bundle(
    compressed_catalog_path: Path | str,
    *,
    validate_screen_count: bool = True,
    max_screens: Optional[int] = None,
) -> DiscoveryInputBundle:
    """
    Produce ``compressed_catalog_package`` plus ``llm_discovery_catalog``.
    Validates structural input and optionally screen cardinality (production parity).
    """

    resolved = Path(compressed_catalog_path).resolve()
    pkg = load_compressed_catalog_package(resolved)

    if validate_screen_count:
        ok_size, sz_err = system_readonly_adapter.validate_discovery_catalog_dimensions(
            pkg, max_screens=max_screens
        )
        if not ok_size:
            raise ValueError(sz_err or "INVALID_COMPRESSED_CATALOG_SIZE")

    llm_catalog = system_readonly_adapter.build_llm_discovery_catalog(pkg)
    ok_in, input_errs = system_readonly_adapter.validate_discovery_input(llm_catalog)
    if not ok_in:
        joined = ";".join(input_errs)
        raise ValueError(f"DISCOVERY_INPUT_INVALID:{joined}")

    input_refs: Dict[str, Any] = {"compressed_catalog_path": path_for_manifest(resolved)}
    return DiscoveryInputBundle(
        compressed_catalog_package=pkg,
        llm_discovery_catalog=llm_catalog,
        input_refs=input_refs,
    )
