"""
ModelCall — SQLAlchemy model for tracking model API calls.

Stores usage metadata for tracing, cost estimation, and debugging.
Raw prompts and raw images are NOT stored here; only artifact references.
"""
import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    node_name: Mapped[str] = mapped_column(String)
    task_name: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    model_name: Mapped[str] = mapped_column(String)
    request_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)    # success | failed | retried | timeout | schema_mismatch
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_output_artifact_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("artifacts.id"), nullable=True)
    extra_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    run = relationship("Run", back_populates="model_calls")
