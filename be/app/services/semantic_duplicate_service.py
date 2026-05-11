"""
Semantic Duplicate Adjudication Service — Phase Research v1.
Uses LLM/VLM to determine semantic duplicates based on structured UI state.
"""
import time
import json
from typing import Any, Dict, List, Literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.model_providers import model_adapter
from app.model_providers.schemas import SemanticDuplicateOutput

async def run_semantic_duplicate_adjudication(
    db: AsyncSession, 
    run_id: str, 
    state_catalog: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calls LLM to identify semantic duplicates among the extracted states.
    """
    start_time = time.time()
    log_event("semantic_duplicate_adjudication_started", run_id=run_id)

    if not state_catalog:
        return {
            "semantic_duplicate_groups": [],
            "canonical_state_catalog": [],
            "report": {"reason": "NO_STATES"}
        }

    # For research mode, we pass the structured state info to LLM
    # If the catalog is too large, it might need batching (handled in LLM prompt/batch logic later)
    
    system_instruction = (
        "You are a Senior UI Analyst. Your task is to identify semantic duplicates from a list of UI states.\n"
        "Two states are semantic duplicates if they represent the same observable UI behavior.\n"
        "Rules:\n"
        "- Do NOT merge if behavior changes (e.g., new error message, success toast, modal, data change relevant to business logic).\n"
        "- Ignore minor visual variations like cursor position or hover states if they don't affect behavior.\n"
        "- Identify a 'canonical' state for each group.\n"
        "- Cite evidence and provide a reason for each merge decision.\n"
    )

    user_instruction = (
        f"Analyze the following {len(state_catalog)} UI states and group duplicates:\n"
        f"{json.dumps(state_catalog, indent=2)}\n"
    )

    response = await model_adapter.call_text_structured(
        task_name="semantic_duplicate_adjudication",
        run_id=run_id,
        node_name="semantic_duplicate_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=SemanticDuplicateOutput,
        prompt_name="semantic_duplicate_prompt",
        prompt_version="v1",
        provider_override=settings.SEMANTIC_DUPLICATE_MODEL_PROVIDER,
        model_name_override=settings.SEMANTIC_DUPLICATE_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Semantic Duplicate Adjudication failed: {response.error}")
        # Fallback: all states are canonical
        return {
            "semantic_duplicate_groups": [],
            "canonical_state_catalog": state_catalog,
            "report": {"error": str(response.error)}
        }

    result: SemanticDuplicateOutput = response.parsed_output
    
    # Filter the catalog to keep only canonical states
    canonical_state_ids = set()
    for group in result.duplicate_groups:
        if group.should_merge:
            canonical_state_ids.add(group.canonical_state_id)
    
    # Also add non-duplicate states as canonical
    canonical_state_ids.update(result.non_duplicate_state_ids)
    
    # If the model missed some states in its output, we keep them as canonical by default
    all_processed_ids = set()
    for group in result.duplicate_groups:
        all_processed_ids.add(group.canonical_state_id)
        all_processed_ids.update(group.duplicate_state_ids)
    all_processed_ids.update(result.non_duplicate_state_ids)
    
    input_state_ids = {s["state_id"] for s in state_catalog}
    missing_ids = input_state_ids - all_processed_ids
    canonical_state_ids.update(missing_ids)

    canonical_state_catalog = [s for s in state_catalog if s["state_id"] in canonical_state_ids]

    report = {
        "input_state_count": len(state_catalog),
        "duplicate_group_count": len(result.duplicate_groups),
        "canonical_state_count": len(canonical_state_catalog),
        "warnings": result.warnings
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("semantic_duplicate_adjudication_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "semantic_duplicate_groups": [g.model_dump() for g in result.duplicate_groups],
        "canonical_state_catalog": canonical_state_catalog,
        "report": report
    }
