"""
UIElement — SQLAlchemy model for tracking UI elements within a UI state.
"""
import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Boolean, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class UIElement(Base):
    __tablename__ = "ui_elements"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    state_id: Mapped[str] = mapped_column(String, ForeignKey("ui_states.id"), index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    image_id: Mapped[str] = mapped_column(String, ForeignKey("images.id"), index=True)
    
    type: Mapped[str] = mapped_column(String)
    label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    placeholder: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    bbox_xmin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_ymin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_xmax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_ymax: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    actionable: Mapped[bool] = mapped_column(Boolean, default=False)
    action_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    semantic_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    visibility: Mapped[str] = mapped_column(String, default="fully_visible")
    
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    
    is_feedback: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    ui_state = relationship("UIState", back_populates="ui_elements")
    run = relationship("Run", back_populates="ui_elements")
    image = relationship("Image", back_populates="ui_elements")
