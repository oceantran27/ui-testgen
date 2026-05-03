"""Standalone P-TEXT pipeline: Stage B+C (vision+text per capture) → Stage A (text-only flow clustering)."""

from __future__ import annotations

from ptext_behavior_pipeline.pipeline import run_ptext_pipeline, run_ptext_pipeline_async

__all__ = ["run_ptext_pipeline", "run_ptext_pipeline_async", "__version__"]

__version__ = "1.0.0"
