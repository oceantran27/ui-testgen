"""Backward-compatible import path for :mod:`app.services.pipeline_output_assembly_service`."""

from __future__ import annotations

from app.services.pipeline_output_assembly_service import (
    run_pipeline_output_assembly as run_research_output_assembly,
)

__all__ = ["run_research_output_assembly"]
