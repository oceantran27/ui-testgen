from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyzeByImageRequest(BaseModel):
    image_url: str
    file_key: Optional[str] = None
    model: Optional[str] = "gemini-2.5-flash"


class Module3RankedScenarioResponse(BaseModel):
    scenario_id: str
    user_goal: str
    conflict_resolution_summary: str
    BA_score: int
    QA_score: int
    UX_score: int
    final_score: float
    rank_position: int


class DebateEventResponse(BaseModel):
    event_id: str
    sequence: int
    timestamp: str
    request_id: str
    batch_id: Optional[str] = None
    scenario_id: Optional[str] = None
    role: str
    event_type: str
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebateEventsPollResponse(BaseModel):
    request_id: str
    batch_id: Optional[str] = None
    next_seq: int
    completed: bool
    status: str
    events: list[DebateEventResponse]


class UploadSessionPayload(BaseModel):
    session_id: str
    file_key: str
    file_url: str
    original_name: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None


class DefaultInputCreate(BaseModel):
    image_url: str
    file_key: Optional[str] = None


class DefaultInputUpdate(BaseModel):
    image_url: Optional[str] = None
    file_key: Optional[str] = None


class PresignedUploadRequest(BaseModel):
    file_name: str
    file_type: str
    input_type: Optional[str] = "user"
