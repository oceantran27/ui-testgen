from typing import Optional

from pydantic import BaseModel

from app.modules.evaluator_rationalizer.models import ScenarioEvaluationScores


class AnalyzeByImageRequest(BaseModel):
    image_url: str
    file_key: Optional[str] = None
    model: Optional[str] = "gemini-2.5-flash"


class Module2ScenarioResponse(BaseModel):
    scenario_id: str
    user_goal: str
    rationale: str
    scores: ScenarioEvaluationScores


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
