"""
Graph Finalizer Node — Phase 4 LangGraph ending point.
"""
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.db.models.run import Run
from app.db.models.job import Job
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service
from app.services.graph_progress import persist_run_graph_progress
from app.core.pipeline_run_log import is_active, log_node, log_node_return, console_err

NODE_NAME = "graph_finalizer_node"


def _generate_artifact_id() -> str:
    import uuid
    return f"art_{uuid.uuid4().hex[:12]}"

async def graph_finalizer_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Finalizes the graph, writes execution report, and updates run status.
    """
    run_id = state["run_id"]
    job_id = state.get("job_id")
    await persist_run_graph_progress(run_id, NODE_NAME)
    log_event("graph_node_started", run_id=run_id, node_name=NODE_NAME)

    # Ensure any previous failures do not block the session (we just expire_all)
    db.expire_all()

    if is_active():
        log_node(
            NODE_NAME,
            intent_lines=[
                "Persist graph_execution_report artifact; set Run status completed/failed.",
                "routing: END.",
            ],
            state_keys=(
                "run_id",
                "should_stop",
                "stop_reason",
                "final_output",
                "completed_nodes",
                "failed_nodes",
            ),
            state=state,
        )

    # Determine final status (LangGraph packages only; legacy draft_scenarios removed)
    if state.get("should_stop"):
        final_status = "failed"
    elif state.get("final_output"):
        final_status = "completed"
    elif state.get("scenario_draft_package") or state.get("validated_scenario_package"):
        final_status = "completed"
    else:
        final_status = "failed"
        
    completed_at = datetime.now(timezone.utc)
    
    # Build Report
    report = {
        "run_id": run_id,
        "job_id": job_id,
        "graph_status": final_status,
        "started_at": state.get("started_at"),
        "completed_at": completed_at.isoformat(),
        "completed_nodes": state.get("completed_nodes", []),
        "failed_nodes": state.get("failed_nodes", []),
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
        "metrics": state.get("metrics", {}),
        "config_snapshot": state.get("config", {}),
    }
    
    # Save Artifact
    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    report_key = f"artifacts/{run_id}/graph/graph_execution_report.json"
    report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")
    
    artifact = Artifact(
        id=_generate_artifact_id(),
        run_id=run_id,
        artifact_type="graph_execution_report",
        node_name=NODE_NAME,
        storage_uri=report_uri,
        metadata_json={"status": final_status},
    )
    db.add(artifact)
    
    # Update Run
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if run:
        run.graph_status = final_status
        run.graph_completed_at = completed_at
        if final_status == "failed":
            run.status = "failed"
            run.error_message = state.get("stop_reason", "GRAPH_EXECUTION_FAILED")
        else:
            run.current_phase = "pipeline_completed_v1"
            run.progress_percentage = 100
            run.status = "completed"
    
    # Update Job
    if job_id:
        j_result = await db.execute(select(Job).where(Job.id == job_id))
        job = j_result.scalar_one_or_none()
        if job:
            job.status = final_status if final_status == "failed" else "completed"
            job.completed_at = completed_at
            job.error_message = state.get("stop_reason")

    await db.commit()

    log_event("graph_node_completed", run_id=run_id, node_name=NODE_NAME)

    out = {
        "current_node": NODE_NAME,
        "graph_status": final_status,
        "completed_at": completed_at.isoformat(),
        "completed_nodes": [NODE_NAME],
        "artifacts": [{"type": "graph_execution_report", "uri": report_uri}]
    }
    if is_active():
        log_node_return(NODE_NAME, [f"status={final_status}"], out)
    return out
