from pydantic import BaseModel
from typing import Any, Dict, Optional
from datetime import datetime

class AnalysisRequest(BaseModel):
    # This schema might not be directly used if we are uploading files via Form data,
    # but good to have for structure if we pass metadata.
    pass

class AnalysisResponse(BaseModel):
    scenario: Dict[str, Any]

class AnalysisRecordBase(BaseModel):
    image_path: str
    scenario_json: str

class AnalysisRecordCreate(AnalysisRecordBase):
    pass

class AnalysisRecordUpdate(BaseModel):
    image_path: Optional[str] = None
    scenario_json: Optional[str] = None

class AnalysisRecordInDB(AnalysisRecordBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
