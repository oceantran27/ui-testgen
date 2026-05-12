"""
UIState — SQLAlchemy model for tracking extracted UI states.
"""
import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base


class UIState(Base):
    __tablename__ = "ui_states"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    image_id: Mapped[str] = mapped_column(String, ForeignKey("images.id"), index=True)
    
    page_type: Mapped[str] = mapped_column(String)
    state_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state_signature: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_label: Mapped[str] = mapped_column(String, default="low")
    
    has_form: Mapped[bool] = mapped_column(Boolean, default=False)
    has_table: Mapped[bool] = mapped_column(Boolean, default=False)
    has_modal: Mapped[bool] = mapped_column(Boolean, default=False)
    has_feedback: Mapped[bool] = mapped_column(Boolean, default=False)
    
    extraction_status: Mapped[str] = mapped_column(String, default="success") # success, failed, needs_review
    extraction_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_extraction_artifact_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    state_quality: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False)
    canonical_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    run = relationship("Run", back_populates="ui_states")
    image = relationship("Image", back_populates="ui_states")
    ui_elements = relationship("UIElement", back_populates="ui_state", cascade="all, delete-orphan")
