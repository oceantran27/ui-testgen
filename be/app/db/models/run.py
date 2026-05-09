from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, JSON
from .base import Base
import datetime
from typing import List, Optional, Any

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    project_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True, default="created")
    input_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    total_images: Mapped[int] = mapped_column(Integer, default=0)
    valid_images: Mapped[int] = mapped_column(Integer, default=0)
    invalid_images: Mapped[int] = mapped_column(Integer, default=0)
    canonical_images: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_groups_count: Mapped[int] = mapped_column(Integer, default=0)
    
    submitted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    config_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    images = relationship("Image", back_populates="run", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
    duplicate_groups = relationship("DuplicateGroup", back_populates="run", cascade="all, delete-orphan")
