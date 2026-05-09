from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Float
from .base import Base
from typing import Optional

class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    canonical_image_id: Mapped[str] = mapped_column(String, ForeignKey("images.id"))
    duplicate_type: Mapped[str] = mapped_column(String)  # exact, near_visual, semantic
    group_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    run = relationship("Run", back_populates="duplicate_groups")
    members = relationship("DuplicateGroupMember", back_populates="group", cascade="all, delete-orphan")
