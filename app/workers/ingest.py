"""SFTP ingest worker — polls uploads/ and enqueues RQ inference jobs.

Start via:
    python -m app.workers.ingest

Per-file lifecycle:
  1. Download from SFTP
  2. Validate (not zero-byte, valid image format, <= 50 MB)
  3. Upload to MinIO 'documents' bucket
  4. Create Batch row in DB
  5. Enqueue RQ inference job (passes filename + request_id for correlation)
  6. Move file to SFTP processed/ directory

On validation failure (zero-byte, non-image, > 50 MB):
  - Move to SFTP quarantine/ — DO NOT crash the poller

On infrastructure failure (MinIO or Redis unreachable):
  - Retry 3x with exponential backoff
  - Log structured error — DO NOT quarantine the file

Design note: the Batch row is created here; the Prediction row is created by
the inference worker after classification, so it carries real label/confidence
values from the start rather than placeholder values.

SYSTEM_USER_ID = 1 is used as the batch owner — the first registered admin.
Ensure at least one user is registered before dropping SFTP files (see RUNBOOK).
"""

import asyncio
import uuid

import structlog
from PIL import Image
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.db.models import BatchStatus
from app.db.session import SessionLocal
from app.infra.blob import BlobStorage
from app.infra.logging_setup import configure_logging
from app.infra.queue import JobQueue
from app.infra.sftp import SftpAdapter
from app.infra.vault import VaultClient
from app.db.session import init_engine
from app.repositories.batch_repo import BatchRepository

log = structlog.get_logger()

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
SYSTEM_USER_ID = 1  # batch owner for SFTP-originated uploads; see module docstring


def _validate_file(filename: str, data: bytes) -> str | None:
    """Validate file size and image format.

    Args:
        filename: Original filename — used for logging context only.
        data: Raw file bytes.

    Returns:
        None if the file is valid; a human-readable rejection reason if invalid.
    """
    if len(data) == 0:
        return "empty_file"
    if len(data) > MAX_FILE_SIZE_BYTES:
        return "file_too_large"
    try:
        import io
        img = Image.open(io.BytesIO(data))
        img.verify()  # raises if not a valid image
    except Exception:
        return "invalid_format"
    return None


async def _upload_with_retry(blob: BlobStorage, bucket: str, key: str, data: bytes, content_type: str) -> None:
    """Upload to MinIO with 3 retries on transient failures.

    Raises:
        RetryError: After 3 failed attempts.
    """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _attempt() -> None:
        await blob.upload(bucket, key, data, content_type)

    await _attempt()


async def _enqueue_with_retry(queue: JobQueue, batch_id: int, filename: str, storage_key: str, request_id: str) -> str:
    """Enqueue an RQ job with 3 retries on transient Redis failures.

    Returns:
        The RQ job ID.

    Raises:
        RetryError: After 3 failed attempts.
    """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _attempt() -> str:
        return queue.enqueue_inference(batch_id, filename, storage_key, request_id)

    return await asyncio.to_thread(_attempt)


async def _process_file(
    filename: str,
    sftp: SftpAdapter,
    blob: BlobStorage,
    queue: JobQueue,
) -> None:
    """Download, validate, upload, persist, and enqueue one file.

    On validation failure: quarantines the file and returns.
    On MinIO/Redis failure: logs and re-raises (caller continues the loop).

    Args:
        filename: Bare filename in uploads/.
        sftp: Connected SFTP adapter.
        blob: MinIO blob storage adapter.
        queue: RQ job queue adapter.
    """
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id, filename=filename)

    # 1. Download from SFTP (sync paramiko — run in thread)
    try:
        data = await asyncio.to_thread(sftp.download_file, filename)
    except Exception as exc:
        log.error("ingest.error.sftp_download", error=str(exc))
        return

    # 2. Validate
    rejection_reason = _validate_file(filename, data)
    if rejection_reason is not None:
        log.warning(
            f"ingest.error.{rejection_reason}",
            filename=filename,
            size_bytes=len(data),
        )
        await asyncio.to_thread(sftp.move_to_quarantine, filename)
        return

    # 3. Upload to MinIO 'documents' bucket
    storage_key = f"documents/{filename}"
    try:
        await _upload_with_retry(blob, "documents", storage_key, data, "image/tiff")
    except (RetryError, Exception) as exc:
        log.error("ingest.error.blob_unreachable", filename=filename, error=str(exc))
        return  # do NOT quarantine — infrastructure failure, not a bad file

    # 4. Create Batch row in DB
    async with SessionLocal() as session:
        batch_repo = BatchRepository(session)
        batch = await batch_repo.create(owner_id=SYSTEM_USER_ID)
        await session.commit()
        batch_id = batch.id

    log.info("ingest.batch.created", batch_id=batch_id, filename=filename)

    # 5. Enqueue inference job
    try:
        job_id = await _enqueue_with_retry(queue, batch_id, filename, storage_key, request_id)
    except (RetryError, Exception) as exc:
        log.error("ingest.error.queue_unreachable", filename=filename, error=str(exc))
        # Batch was created but job not enqueued — mark it failed so it isn't orphaned
        async with SessionLocal() as session:
            batch_repo = BatchRepository(session)
            await batch_repo.update_status(batch_id, BatchStatus.failed)
            await session.commit()
        return

    log.info("ingest.job.enqueued", batch_id=batch_id, job_id=job_id)

    # 6. Move to processed/ on SFTP — failure here is non-fatal; the job is
    # already enqueued so we log and continue rather than leaving the file to
    # be re-picked-up on the next poll.
    try:
        await asyncio.to_thread(sftp.move_to_processed, filename)
    except Exception as exc:
        log.error("ingest.error.sftp_move", filename=filename, error=str(exc))

    structlog.contextvars.unbind_contextvars("request_id", "filename")


async def _poll_once(
    sftp: SftpAdapter,
    blob: BlobStorage,
    queue: JobQueue,
) -> None:
    """Perform one SFTP poll cycle: list uploads/ and process each new file.

    Individual file errors are caught and logged — the loop always continues.

    Args:
        sftp: Connected SFTP adapter.
        blob: MinIO blob storage adapter.
        queue: RQ job queue adapter.
    """
    filenames = await asyncio.to_thread(sftp.list_uploads)
    for filename in filenames:
        try:
            await _process_file(filename, sftp, blob, queue)
        except Exception as exc:
            log.exception("ingest.file.error", filename=filename, error=str(exc))


async def run_ingest_loop() -> None:
    """Main SFTP ingest polling loop — runs until cancelled.

    Resolves secrets from Vault at startup, then polls every
    settings.sftp_poll_interval_seconds (default 1 s) so that new SFTP
    drops are detected within 5 seconds.
    """
    configure_logging()
    settings = get_settings()

    # Resolve secrets from Vault — refuse to start if unreachable
    vault = VaultClient(addr=settings.vault_addr, token=settings.vault_token)
    if not vault.is_reachable():
        raise RuntimeError("Vault is unreachable — ingest worker refusing to start")
    sftp_password = vault.get_secret("app", "sftp_password")
    minio_secret_key = vault.get_secret("app", "minio_secret_key")
    settings.postgres_password = vault.get_secret("app", "postgres_password")
    init_engine(settings.build_database_url())

    sftp = SftpAdapter(
        host=settings.sftp_host,
        port=settings.sftp_port,
        username=settings.sftp_user,
        password=sftp_password,
    )
    blob = BlobStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=minio_secret_key,
    )
    queue = JobQueue(redis_url=settings.redis_url)

    await asyncio.to_thread(sftp.connect)
    log.info(
        "ingest.worker.started",
        sftp_host=settings.sftp_host,
        poll_interval=settings.sftp_poll_interval_seconds,
    )

    try:
        while True:
            try:
                await _poll_once(sftp, blob, queue)
            except Exception as exc:
                log.exception("ingest.poll.error", error=str(exc))
            await asyncio.sleep(settings.sftp_poll_interval_seconds)
    finally:
        await asyncio.to_thread(sftp.disconnect)
        log.info("ingest.worker.stopped")


if __name__ == "__main__":
    asyncio.run(run_ingest_loop())
