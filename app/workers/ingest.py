"""SFTP ingest worker — polls uploads/ and enqueues RQ inference jobs.

Start via:
    python -m app.workers.ingest

Per-file lifecycle:
  1. Download from SFTP
  2. Validate (not zero-byte, valid image format, <= 50 MB)
  3. Upload to MinIO 'documents' bucket
  4. Create Batch + Prediction rows in DB
  5. Enqueue RQ inference job (passes request_id for log correlation)
  6. Move file to SFTP processed/ directory

On validation failure (zero-byte, non-image, > 50 MB):
  - Move to SFTP quarantine/ — DO NOT crash the poller

On infrastructure failure (MinIO or Redis unreachable):
  - Retry 3x with exponential backoff
  - Log structured error — DO NOT quarantine the file
"""

import asyncio

import structlog

from app.config import get_settings

log = structlog.get_logger()

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _validate_file(filename: str, data: bytes) -> str | None:
    """Validate file size and image format.

    Args:
        filename: Original filename — used for extension-based format detection.
        data: Raw file bytes.

    Returns:
        None if the file is valid; a human-readable rejection reason if invalid.
    """
    # TODO: Phase 8 — check zero-byte, PIL.Image.open(), size limit
    return None


async def _poll_once() -> None:
    """Perform one SFTP poll cycle: list uploads/ and process each new file.

    Individual file errors are caught and logged — the loop continues.
    """
    # TODO: Phase 8 — SftpAdapter.list_uploads(), validate, upload, create rows, enqueue
    ...


async def run_ingest_loop() -> None:
    """Main SFTP ingest polling loop — runs until cancelled.

    Polls every settings.sftp_poll_interval_seconds (default 1s) so that
    new SFTP drops are detected within 5 seconds.
    """
    settings = get_settings()
    log.info("ingest.worker.started", poll_interval=settings.sftp_poll_interval_seconds)

    while True:
        try:
            await _poll_once()
        except Exception as exc:
            log.exception("ingest.poll.error", error=str(exc))
        await asyncio.sleep(settings.sftp_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_ingest_loop())
