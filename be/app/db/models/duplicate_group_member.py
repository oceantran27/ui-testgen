from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Float, Integer
from .base import Base
from typing import Optional

class DuplicateGroupMember(Base):
    __tablename__ = "duplicate_group_members"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    duplicate_group_id: Mapped[str] = mapped_column(String, ForeignKey("duplicate_groups.id"), index=True)
    image_id: Mapped[str] = mapped_column(String, ForeignKey("images.id"), index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # canonical, member
    duplicate_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hash_distance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    group = relationship("DuplicateGroup", back_populates="members")
