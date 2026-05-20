"""Aggregate build_report.json for input_builder."""

from __future__ import annotations

from typing import Any


def build_final_report(
    *,
    app_id: str,
    experiment_run_id: str,
    raw_file_count: int,
    normalized_output_count: int,
    state_count: int,
    screen_intent_count: int,
    unresolved_screen_group_count: int,
    invalid_raw_file_count: int,
    state_build_warning_count: int,
    screen_intent_warning_count: int,
    warnings: list[str],
    compressed_catalog_package: dict[str, Any],
) -> dict[str, Any]:
    stats = compressed_catalog_package.get("compression_stats")
    comp_stats_out: dict[str, Any]
    if isinstance(stats, dict):
        comp_stats_out = {
            "screen_count": stats.get("screen_count", state_count),
            "intent_row_count": stats.get("intent_row_count", screen_intent_count),
            "char_count": stats.get("char_count", 0),
            "token_estimate_div4": stats.get("token_estimate_div4", 0),
        }
    else:
        comp_stats_out = {
            "screen_count": state_count,
            "intent_row_count": screen_intent_count,
            "char_count": 0,
            "token_estimate_div4": 0,
        }
    return {
        "app_id": app_id,
        "experiment_run_id": experiment_run_id,
        "raw_file_count": raw_file_count,
        "normalized_output_count": normalized_output_count,
        "state_count": state_count,
        "screen_intent_count": screen_intent_count,
        "unresolved_screen_group_count": unresolved_screen_group_count,
        "invalid_raw_file_count": invalid_raw_file_count,
        "state_build_warning_count": state_build_warning_count,
        "screen_intent_warning_count": screen_intent_warning_count,
        "warnings": list(warnings),
        "compression_stats": comp_stats_out,
    }


__all__ = ["build_final_report"]
