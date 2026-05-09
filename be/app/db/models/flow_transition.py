"""
FlowTransition — SQLAlchemy model for tracking transitions between UI states in a flow.
"""
import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class FlowTransition(Base):
    __tablename__ = "flow_transitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    flow_id: Mapped[str] = mapped_column(String, ForeignKey("flows.id"), index=True)
    
    from_state_id: Mapped[str] = mapped_column(String, index=True)
    to_state_id: Mapped[str] = mapped_column(String, index=True)
    
    transition_type: Mapped[str] = mapped_column(String)
    hypothesized_action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String, default="low")
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    evidence_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    flow = relationship("Flow", back_populates="transitions")
    run = relationship("Run", back_populates="flow_transitions")
