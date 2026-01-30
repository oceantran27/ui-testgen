from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.session import engine
from app.models.analysis_record import AnalysisRecord # Ensure all models are imported

def init_db():
    # Create all tables in the database
    Base.metadata.create_all(bind=engine)
