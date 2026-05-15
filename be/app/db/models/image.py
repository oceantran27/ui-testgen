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

    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sha256_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    upload_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    invalid_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    ui_states = relationship("UIState", back_populates="image", cascade="all, delete-orphan")
    ui_elements = relationship("UIElement", back_populates="image", cascade="all, delete-orphan")


    run = relationship("Run", back_populates="images")
