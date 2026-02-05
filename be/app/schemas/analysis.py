from pydantic import BaseModel
from typing import Any, Dict, Optional, List
from datetime import datetime

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
