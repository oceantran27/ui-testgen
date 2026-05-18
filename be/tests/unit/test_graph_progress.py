"""Graph progress: pipeline order and Run.current_node updates."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph_progress import PIPELINE_NODE_ORDER, persist_run_graph_progress


def test_persist_run_graph_progress_sets_node_and_commits():
    mock_run = MagicMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_run
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=exec_result)
    mock_db.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *exc):
            return None

    with patch("app.services.graph_progress.AsyncSessionLocal", return_value=_CM()):
        asyncio.run(persist_run_graph_progress("run_1", "joint_screen_understanding_node"))

    assert mock_run.current_node == "joint_screen_understanding_node"
    assert isinstance(mock_run.progress_percentage, int)
    mock_db.commit.assert_awaited_once()


def test_persist_run_graph_progress_respects_agent_alias():
    mock_run = MagicMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_run
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=exec_result)
    mock_db.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *exc):
            return None

    with patch("app.services.graph_progress.AsyncSessionLocal", return_value=_CM()):
        asyncio.run(persist_run_graph_progress("run_1", "joint_screen_understanding"))

    assert mock_run.current_node == "joint_screen_understanding_node"


def test_pipeline_order_includes_joint_screen_understanding():
    assert "joint_screen_understanding_node" in PIPELINE_NODE_ORDER
    assert "ui_state_evidence_extraction_node" not in PIPELINE_NODE_ORDER
