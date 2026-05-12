from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, JSON, Float
from .base import Base
import datetime
from typing import List, Optional, Any

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    project_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True, default="created")
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    valid_images: Mapped[int] = mapped_column(Integer, default=0)
    invalid_images: Mapped[int] = mapped_column(Integer, default=0)
    canonical_images: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_groups_count: Mapped[int] = mapped_column(Integer, default=0)

    # Phase 4: Graph Execution Tracking
    current_phase: Mapped[str] = mapped_column(String, default="created")
    current_node: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0)
    graph_thread_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    graph_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    graph_started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    graph_completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Phase 7: Input Level Detection
    input_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    input_level_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    input_level_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    submitted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    config_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    images = relationship("Image", back_populates="run", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="run", cascade="all, delete-orphan")
    model_calls = relationship("ModelCall", back_populates="run", cascade="all, delete-orphan")
    ui_states = relationship("UIState", back_populates="run", cascade="all, delete-orphan")
    ui_elements = relationship("UIElement", back_populates="run", cascade="all, delete-orphan")
    flows: Mapped[list["Flow"]] = relationship("Flow", back_populates="run", cascade="all, delete-orphan")
    flow_transitions: Mapped[list["FlowTransition"]] = relationship("FlowTransition", back_populates="run", cascade="all, delete-orphan")
    behaviour_intents: Mapped[list["BehaviourIntent"]] = relationship("BehaviourIntent", back_populates="run", cascade="all, delete-orphan")
    behaviour_scenarios: Mapped[list["BehaviourScenario"]] = relationship("BehaviourScenario", back_populates="run", cascade="all, delete-orphan")
    duplicate_groups = relationship("DuplicateGroup", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
