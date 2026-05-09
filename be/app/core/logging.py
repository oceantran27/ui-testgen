import logging
import json
from datetime import datetime
from app.core.config import settings
from typing import Optional, Any, Dict

class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service_name": "ui-testgen-backend",
            "environment": settings.ENVIRONMENT,
            "message": record.getMessage(),
        }

        # Include custom fields if passed in 'extra'
        if hasattr(record, "run_id"):
            log_obj["run_id"] = record.run_id
        if hasattr(record, "job_id"):
            log_obj["job_id"] = record.job_id
        if hasattr(record, "node_name"):
            log_obj["node_name"] = record.node_name
        if hasattr(record, "event_name"):
            log_obj["event_name"] = record.event_name
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "error_code"):
            log_obj["error_code"] = record.error_code

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

def setup_logging() -> logging.Logger:
    logger = logging.getLogger("ui-testgen")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        # Use JSON formatter for structured logging
        console_handler.setFormatter(JSONLogFormatter())
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logging()

def log_event(event_name: str, level: int = logging.INFO, **kwargs):
    extra = {"event_name": event_name}
    extra.update(kwargs)
    logger.log(level, f"Event: {event_name}", extra=extra)
