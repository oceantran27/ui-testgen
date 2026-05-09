from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ──────────────────────────────────────────────
# Single image item in upload response
# ──────────────────────────────────────────────

class ImageUploadItem(BaseModel):
    """Result for a single file within a batch upload."""
    image_id: Optional[str] = None
    original_filename: str
    format: Optional[str] = None
    file_size: Optional[int] = None
    storage_uri: Optional[str] = None
    upload_status: str  # "success" | "failed"
    error_message: Optional[str] = None


# ──────────────────────────────────────────────
# Upload response
# ──────────────────────────────────────────────

class UploadImagesResponse(BaseModel):
    """Response for POST /runs/{run_id}/images"""
    run_id: str
    uploaded_count: int = 0
    failed_count: int = 0
    image_items: List[ImageUploadItem] = []
    warnings: List[str] = []


# ──────────────────────────────────────────────
# Image query response
# ──────────────────────────────────────────────

class ImageResponse(BaseModel):
    """Single image record returned by GET /runs/{run_id}/images"""
    image_id: str
    original_filename: str
    format: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    upload_order: Optional[int] = None
    storage_uri: Optional[str] = None
    quality_status: Optional[str] = None
    sha256_hash: Optional[str] = None
    
    # Phase 3: Duplicate Detection
    duplicate_status: Optional[str] = None
    duplicate_group_id: Optional[str] = None
    is_canonical: Optional[bool] = None
    duplicate_type: Optional[str] = None
    duplicate_reason: Optional[str] = None
    phash: Optional[str] = None
    dhash: Optional[str] = None

    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ImageListResponse(BaseModel):
    """Response for GET /runs/{run_id}/images"""
    run_id: str
    total: int
    images: List[ImageResponse]
