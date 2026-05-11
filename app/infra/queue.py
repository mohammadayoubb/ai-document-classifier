"""RQ (Redis Queue) adapter for enqueueing inference jobs."""

import structlog
from redis import Redis
from rq import Queue

log = structlog.get_logger()


class JobQueue:
    """Thin RQ wrapper — enqueue inference jobs and inspect queue state.

    Args:
        redis_url: Redis connection URL — e.g. "redis://redis:6379".
    """

    def __init__(self, redis_url: str) -> None:
        self._redis: Redis[bytes] = Redis.from_url(redis_url)
        self._queue: Queue = Queue(connection=self._redis)

    def enqueue_inference(
        self,
        batch_id: int,
        prediction_id: int,
        storage_key: str,
        request_id: str,
    ) -> str:
        """Enqueue an inference job for a single document.

        The job function is app.workers.inference.run_inference_job.
        request_id is forwarded so worker logs can be correlated with the
        originating HTTP request.

        Args:
            batch_id: Primary key of the owning batch.
            prediction_id: Primary key of the prediction row to update.
            storage_key: MinIO object key for the document to classify.
            request_id: Propagated from the ingest HTTP request for log correlation.

        Returns:
            The RQ job ID string.
        """
        job = self._queue.enqueue(
            "app.workers.inference.run_inference_job",
            batch_id,
            prediction_id,
            storage_key,
            request_id,
            job_timeout=30,
        )
        return str(job.id)
