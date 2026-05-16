"""Async SQLAlchemy session for the current graph/model call (set by GraphExecutionService)."""
from contextvars import ContextVar
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

model_call_db_session: ContextVar[Optional[AsyncSession]] = ContextVar(
    "model_call_db_session", default=None
)

model_call_job_id: ContextVar[Optional[str]] = ContextVar(
    "model_call_job_id", default=None
)
