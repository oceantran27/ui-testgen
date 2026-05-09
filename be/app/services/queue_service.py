from arq.connections import RedisSettings, create_pool
from app.core.config import settings
from app.core.logging import logger
from typing import Optional

redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)

class QueueService:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if not self.pool:
            self.pool = await create_pool(redis_settings)
            logger.info("Connected to Redis Queue")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Disconnected from Redis Queue")

    async def enqueue_job(self, job_type: str, run_id: str, **kwargs) -> Optional[str]:
        if not self.pool:
            await self.connect()
        try:
            job = await self.pool.enqueue_job(job_type, run_id=run_id, **kwargs)
            if job:
                logger.info(f"Enqueued job {job_type} for run {run_id} with job id {job.job_id}")
                return job.job_id
            return None
        except Exception as e:
            logger.error(f"Failed to enqueue job {job_type}: {e}")
            return None

queue_service = QueueService()
