from sqlalchemy.orm import Session
from app.models.analysis_record import AnalysisRecord
from app.schemas.analysis import AnalysisRecordCreate
import json

class AnalysisRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, obj_in: AnalysisRecordCreate) -> AnalysisRecord:
        db_obj = AnalysisRecord(
            image_path=obj_in.image_path,
            scenario_json=obj_in.scenario_json
        )
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj

    def get(self, id: int) -> AnalysisRecord | None:
        return self.db.query(AnalysisRecord).filter(AnalysisRecord.id == id).first()

    def get_multi(self, skip: int = 0, limit: int = 100) -> list[AnalysisRecord]:
        return self.db.query(AnalysisRecord).offset(skip).limit(limit).all()

    def delete(self, id: int) -> AnalysisRecord | None:
        obj = self.db.query(AnalysisRecord).filter(AnalysisRecord.id == id).first()
        if obj:
            self.db.delete(obj)
            self.db.commit()
        return obj
