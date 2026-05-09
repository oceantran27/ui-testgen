from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, ForeignKey, Boolean, JSON, Float
from .base import Base
from typing import Optional

class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String)
    storage_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    thumbnail_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    normalized_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    upload_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    invalid_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preprocessing_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Phase 3: Duplicate Detection
    duplicate_status: Mapped[str] = mapped_column(String, default="not_checked")
    duplicate_group_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("duplicate_groups.id"), nullable=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=True)
    duplicate_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duplicate_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duplicate_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    phash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dhash: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    run = relationship("Run", back_populates="images")
