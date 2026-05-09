from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db_session
from app.services.storage_service import storage_service
from app.services.queue_service import queue_service
from app.core.logging import logger
from datetime import datetime
import traceback

router = APIRouter()

@router.get("/health")
async def health_check():
    """Basic health check to see if the service is running."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"}

@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db_session)):
    """Readiness check to verify dependencies (DB, Storage, Queue)."""
    status = "healthy"
    db_status = "ok"
    storage_status = "ok"
    queue_status = "ok"

    # Check DB
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"DB readiness check failed: {e}")
        db_status = "failed"
        status = "unhealthy"

    # Check Storage
    try:
        if not storage_service.object_exists("dummy"):
            pass # Just to test connection, it will throw if it can't connect, otherwise return False
    except Exception as e:
        logger.error(f"Storage readiness check failed: {e}")
        storage_status = "failed"
        status = "unhealthy"

    # Check Queue
    try:
        await queue_service.connect()
        # pool.ping() is not directly available, but connecting and enqueueing works, 
        # or we can assume it's fine if connect didn't throw
        if not queue_service.pool:
            queue_status = "failed"
            status = "unhealthy"
    except Exception as e:
        logger.error(f"Queue readiness check failed: {e}")
        queue_status = "failed"
        status = "unhealthy"

    return {
        "status": status,
        "database": db_status,
        "storage": storage_status,
        "queue": queue_status,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
