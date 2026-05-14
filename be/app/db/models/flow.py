"""
Flow — SQLAlchemy model for tracking discovered UI flows.
"""
import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class Flow(Base):
    __tablename__ = "flows"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    flow_type: Mapped[str] = mapped_column(String)  # linear_flow, branched_flow, single_state_pseudo_flow
    input_level: Mapped[str] = mapped_column(String)
    user_goal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    start_state_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ordered_state_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON)  # List of state IDs
    paths_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)  # For branched flows
    
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String, default="low")
    
    # Phase 9: Missing Step Analysis
    completeness_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scenario_eligibility: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    missing_step_penalty: Mapped[float] = mapped_column(Float, default=0.0)
    adjusted_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    missing_step_warnings_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    flow_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_state_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    terminal_state_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    state_sequence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    flow_completeness_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    intent_readiness_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    flow_evidence_package_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    warnings_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    # Relationships
    run: Mapped["Run"] = relationship("Run", back_populates="flows")
    behaviour_intents: Mapped[list["BehaviourIntent"]] = relationship("BehaviourIntent", back_populates="flow", cascade="all, delete-orphan")
    behaviour_scenarios: Mapped[list["BehaviourScenario"]] = relationship("BehaviourScenario", back_populates="flow", cascade="all, delete-orphan")
    transitions = relationship("FlowTransition", back_populates="flow", cascade="all, delete-orphan")
