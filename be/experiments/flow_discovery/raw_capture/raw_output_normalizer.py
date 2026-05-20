"""Bridge to adapter-side normalization helpers (imports ``app`` only inside adapters/)."""

from __future__ import annotations

from experiments.flow_discovery.adapters.model_readonly_adapter import (
    empty_global_flow_discovery_shell,
    normalize_global_flow_discovery_llm_response as normalize_llm_discovery_response,
)

__all__ = ["empty_global_flow_discovery_shell", "normalize_llm_discovery_response"]
