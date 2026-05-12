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
    path_id: Mapped[Optional[str]] = mapped_column(String, nullable=True) # For branched flows

    intent_name: Mapped[str] = mapped_column(String, index=True) # e.g. "login_success"
    behaviour_domain: Mapped[str] = mapped_column(String) # e.g. "authentication"
    behaviour_outcome: Mapped[str] = mapped_column(String) # e.g. "success"
    user_goal: Mapped[str] = mapped_column(String) # e.g. "User logs in successfully"
    
    intent_scope: Mapped[str] = mapped_column(String, default="end_to_end")
    observable_precondition_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    main_user_action_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observable_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounding_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    grounding_level: Mapped[str] = mapped_column(String, default="grounded")
    ambiguity_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Scenario hints for Phase 11
    scenario_type_hint: Mapped[str] = mapped_column(String) # e.g. "positive_behaviour"
    expected_grounding: Mapped[str] = mapped_column(String) # e.g. "grounded"
    should_generate: Mapped[bool] = mapped_column(Boolean, default=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String, default="low")

    # Evidence
    evidence_state_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_element_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence_transition_ids_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
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
