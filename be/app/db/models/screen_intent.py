"""
Screen Behaviour Intent model — Phase 2 v2.
Stores local user intents inferred from interaction groups on a single screen.
"""
import datetime
from typing import Any, Optional
from sqlalchemy import String, ForeignKey, Float, JSON, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base

class ScreenBehaviourIntent(Base):
    __tablename__ = "screen_behaviour_intents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    state_id: Mapped[str] = mapped_column(String, ForeignKey("ui_states.id"), index=True)
    
    source_group_id: Mapped[str] = mapped_column(String)
    intent_name: Mapped[str] = mapped_column(String)
    intent_kind: Mapped[str] = mapped_column(String)
    local_user_goal: Mapped[str] = mapped_column(String)
    
    primary_action_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    required_input_groups_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    confidence: Mapped[str] = mapped_column(String, default="low")
    raw_result_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    # Relationships
    run = relationship("Run", back_populates="screen_behaviour_intents")
    ui_state = relationship("UIState")
