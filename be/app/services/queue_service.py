from arq.connections import RedisSettings, create_pool
from app.core.config import settings
from app.core.errors import QueueEnqueueFailedException
from app.core.logging import logger

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

    async def enqueue_job(self, job_type: str, run_id: str, **kwargs) -> str:
        try:
            if not self.pool:
                await self.connect()
        except Exception as e:
            logger.exception("Failed to connect to Redis for job queue")
            raise QueueEnqueueFailedException(run_id, reason=str(e)) from e
        try:
            job = await self.pool.enqueue_job(job_type, run_id=run_id, **kwargs)
            if not job:
                raise QueueEnqueueFailedException(
                    run_id, reason="enqueue_job returned no job handle"
                )
            logger.info(
                "Enqueued job %s for run %s with job id %s",
                job_type,
                run_id,
                job.job_id,
            )
            return job.job_id
        except QueueEnqueueFailedException:
            raise
        except Exception as e:
            logger.exception("Failed to enqueue job %s", job_type)
            raise QueueEnqueueFailedException(run_id, reason=str(e)) from e


queue_service = QueueService()
