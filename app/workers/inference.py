"""RQ inference worker — consumes jobs and runs the ConvNeXt classifier.

Start via:
    rq worker --url redis://redis:6379

The RQ worker is synchronous — RQ runs tasks in threads.  All DB and MinIO
calls inside this module use synchronous drivers (psycopg2 / minio sync).

Per-job lifecycle (run_inference_job):
  1. Download image bytes from MinIO
  2. Run classify_image()
  3. Write prediction result to DB (label, confidence, top5)
  4. Generate annotated overlay PNG (label + confidence bar drawn with Pillow)
  5. Upload overlay PNG to MinIO 'overlays' bucket
  6. Update prediction row with overlay_key
  7. Update batch status to 'completed' (or 'failed' on unrecoverable error)
  8. Invalidate affected caches via service layer
  9. Log structured result including request_id for correlation with ingest logs
"""

import structlog

log = structlog.get_logger()


def run_inference_job(
    batch_id: int,
    prediction_id: int,
    storage_key: str,
    request_id: str,
) -> None:
    """Classify one document and persist the results.

    This function is the RQ job entrypoint.  It is synchronous because RQ
    executes jobs in threads, not coroutines.

    p95 latency targets:
    - Inference step: < 1.0s (CPU, ConvNeXt Tiny)
    - End-to-end (SFTP drop → API response): < 10s

    Args:
        batch_id: Primary key of the owning batch.
        prediction_id: Primary key of the prediction row to update.
        storage_key: MinIO object key for the source document to classify.
        request_id: Propagated from the ingest HTTP request for log correlation.

    Raises:
        Exception: On unrecoverable failure — RQ marks the job as failed.
            Batch status is updated to 'failed' before re-raising.
    """
    structlog.contextvars.bind_contextvars(request_id=request_id)
    log.info(
        "inference.job.started",
        batch_id=batch_id,
        prediction_id=prediction_id,
        storage_key=storage_key,
    )

    # TODO: Phase 8 — implement full job body:
    # 1. download from MinIO
    # 2. classify_image()
    # 3. write prediction result
    # 4. generate overlay PNG
    # 5. upload overlay
    # 6. update rows + invalidate cache
    ...
