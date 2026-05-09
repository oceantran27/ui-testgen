from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, JSON
from .base import Base
from typing import Optional, Any

class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("runs.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String)
    node_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    run = relationship("Run", back_populates="artifacts")
