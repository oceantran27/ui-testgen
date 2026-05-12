"""
Behaviour Scenario model — Phase 11.
Stores draft test scenarios (Gherkin & Structured JSON) generated from UI flows and intents.
"""
import datetime
from typing import Any, Optional
from sqlalchemy import String, ForeignKey, JSON, DateTime, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

class BehaviourScenario(Base):
    __tablename__ = "behaviour_scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True) # BTS_...
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    flow_id: Mapped[str] = mapped_column(String, ForeignKey("flows.id"), index=True)
    intent_id: Mapped[str] = mapped_column(String, ForeignKey("behaviour_intents.id"), index=True)
    path_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    feature: Mapped[str] = mapped_column(String)
    scenario_title: Mapped[str] = mapped_column(String)
    scenario_type: Mapped[str] = mapped_column(String) # positive, negative, etc.
    grounding_mode: Mapped[str] = mapped_column(String) # grounded, inferred, etc.

    gherkin_text: Mapped[str] = mapped_column(String)
    structured_steps_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    bdd_steps_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assumptions_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    initial_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String, default="low")
    
    # Validation Results (Phase 12)
    grounding_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    hallucination_flags_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    validation_issues_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    revision_suggestions_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    final_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    
    final_reliability: Mapped[float] = mapped_column(Float, default=0.0)
    scores_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    step_audits_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    acceptance_decision_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    validated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    # Curation Results (Phase 13)
    final_status: Mapped[str] = mapped_column(String, default="pending") # accepted, rejected, duplicate_removed
    final_priority: Mapped[str] = mapped_column(String, default="P2") # P0, P1, P2, P3
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    priority_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    curation_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duplicate_group_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_canonical_scenario: Mapped[bool] = mapped_column(Boolean, default=True)
    curated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(String, default="draft") # draft, generated
    validation_status: Mapped[str] = mapped_column(String, default="pending") # pending, validated, rejected

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Relationships
    run = relationship("Run", back_populates="behaviour_scenarios")
    flow = relationship("Flow", back_populates="behaviour_scenarios")
    intent = relationship("BehaviourIntent", back_populates="behaviour_scenarios")
