"""Resolve pipeline screen-understanding mode from Run.config_json."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.graph_progress import resolve_screen_understanding_mode


def test_resolve_screen_understanding_mode_run_override(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SCREEN_UNDERSTANDING_MODE", "separated", raising=False)

    mock_run = MagicMock()
    mock_run.config_json = {"screen_understanding_mode": "joint"}
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_run
    db = AsyncMock()
    db.execute = AsyncMock(return_value=exec_result)

    async def _run():
        return await resolve_screen_understanding_mode(db, "run_1")

    mode = asyncio.run(_run())
    assert mode == "joint"


def test_resolve_screen_understanding_mode_settings_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SCREEN_UNDERSTANDING_MODE", "joint", raising=False)

    mock_run = MagicMock()
    mock_run.config_json = {}
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_run
    db = AsyncMock()
    db.execute = AsyncMock(return_value=exec_result)

    async def _run():
        return await resolve_screen_understanding_mode(db, "run_2")

    mode = asyncio.run(_run())
    assert mode == "joint"
