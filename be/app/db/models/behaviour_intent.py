"""
Behaviour Intent model — Phase 10.
Stores inferred user intentions and goals from UI flows.
"""
import datetime
from typing import Any, Optional
from sqlalchemy import String, ForeignKey, Float, JSON, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

class BehaviourIntent(Base):
    __tablename__ = "behaviour_intents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    flow_id: Mapped[str] = mapped_column(String, ForeignKey("flows.id"), index=True)
    
    # Traceability
    source_flow_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_flow_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_transition_indexes_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_outcome_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    source_group_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_screen_intent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_transition_ids_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Core Intent
    behaviour_name: Mapped[str] = mapped_column(String, index=True)
    intent_type: Mapped[str] = mapped_column(String)  # positive | negative | ...
    test_path: Mapped[str] = mapped_column(String)    # happy_path | negative_path | ...
    user_intent: Mapped[str] = mapped_column(String)
    business_goal: Mapped[str] = mapped_column(String)
    
    # State mapping
    start_state: Mapped[str] = mapped_column(String)
    end_state: Mapped[str] = mapped_column(String)

    # Detailed Behaviour
    trigger_action_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preconditions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    test_data_requirements_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    user_actions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_result: Mapped[str] = mapped_column(String)
    expected_ui_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    negative_expectations_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Metadata
    confidence: Mapped[str] = mapped_column(String, default="low")
    assumptions_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    raw_result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Relationships
    run = relationship("Run", back_populates="behaviour_intents")
    flow = relationship("Flow", back_populates="behaviour_intents")
    behaviour_scenarios: Mapped[list["BehaviourScenario"]] = relationship("BehaviourScenario", back_populates="intent", cascade="all, delete-orphan")
