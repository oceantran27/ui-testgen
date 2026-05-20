"""Call production compressed catalog builder (read-only)."""

from __future__ import annotations

from typing import Any

from experiments.flow_discovery.adapters import system_readonly_adapter


class ExperimentCompressedCatalogBuilder:
    def build(
        self,
        experiment_run_id: str,
        state_catalog: list[dict[str, Any]],
        screen_intent_package: dict[str, Any],
        ui_state_package: dict[str, Any],
        *,
        validation_warnings: list[str] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        warnings = list(validation_warnings or [])
        pkg = system_readonly_adapter.run_build_compressed_catalog(
            run_id=experiment_run_id,
            state_catalog=state_catalog,
            screen_intent_pkg=screen_intent_package,
            ui_state_package=ui_state_package,
        )
        cats = pkg.get("compressed_catalog") or []
        if not cats:
            warnings.append("EMPTY_COMPRESSED_CATALOG")
        trace = pkg.get("trace_index") or {}
        for row in state_catalog:
            sid = str(row.get("state_id") or "")
            if sid and sid not in trace:
                warnings.append(f"MISSING_TRACE_INDEX_ROW:{sid}")
        for card in cats:
            if not isinstance(card, dict):
                continue
            if not card.get("state_id"):
                warnings.append("MISSING_CARD_STATE_ID")
            tax = card.get("taxonomy")
            if not isinstance(tax, dict):
                warnings.append("MISSING_TAXONOMY")
        stats = pkg.get("compression_stats")
        if not isinstance(stats, dict):
            warnings.append("MISSING_COMPRESSION_STATS")
        base_warn = pkg.get("warnings")
        if isinstance(base_warn, list):
            merged = [str(w) for w in base_warn] + warnings
            pkg["warnings"] = merged
        else:
            pkg["warnings"] = warnings
        return pkg, warnings


__all__ = ["ExperimentCompressedCatalogBuilder"]
