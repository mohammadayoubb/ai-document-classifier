"""Batch listing and detail routes.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile

from app.api.deps import get_batch_service, get_current_user
from app.domain.batch import BatchDetail, BatchStatus, PaginatedBatchSummary
from app.domain.user import UserDomain
from app.services.batch_service import BatchService

log = structlog.get_logger()

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("", response_model=PaginatedBatchSummary)
async def list_batches(
    user: Annotated[UserDomain, Depends(get_current_user)],
    service: Annotated[BatchService, Depends(get_batch_service)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: BatchStatus | None = Query(default=None),
) -> PaginatedBatchSummary:
    """List all batches visible to the authenticated user.

    Args:
        user: The authenticated user (any role).
        service: Injected batch service.
        limit: Maximum number of batches to return (1–500).
        offset: Number of batches to skip for pagination.
        status: Optional filter by batch lifecycle status.

    Returns:
        A paginated list of batch summaries ordered by creation time descending.
    """
    return await service.list_batches(limit=limit, offset=offset, status=status)


@router.get("/{batch_id}", response_model=BatchDetail)
async def get_batch(
    batch_id: int,
    user: Annotated[UserDomain, Depends(get_current_user)],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchDetail:
    """Return a single batch with its full prediction list.

    Args:
        batch_id: The batch primary key.
        user: The authenticated user (any role).
        service: Injected batch service.

    Returns:
        A BatchDetail object containing all predictions for that batch.

    Raises:
        HTTPException: 404 if no batch with that ID exists.
    """
    detail = await service.get_batch_detail(batch_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return detail


@router.post("/upload", status_code=202)
async def upload_document(
    file: UploadFile,
    request: Request,
    user: Annotated[UserDomain, Depends(get_current_user)],
) -> dict[str, str]:
    """Drop an uploaded file into the SFTP uploads/ folder.

    The file is written into the SFTP server exactly as a scanner would drop
    it. The ingest worker detects it within 1–5 seconds and runs the full
    pipeline: validate → MinIO → Batch row → RQ inference job.

    Args:
        file: The uploaded image file.
        request: FastAPI request (used to access app.state.sftp).
        user: The authenticated user (any role).

    Returns:
        A dict confirming the filename queued for ingest.

    Raises:
        HTTPException: 400 if the file is empty.
        HTTPException: 503 if the SFTP adapter is unavailable.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "upload.tiff"

    try:
        sftp = request.app.state.sftp
        await asyncio.to_thread(sftp.upload_file, filename, data)
    except Exception as exc:
        log.exception("upload.sftp_write_failed", filename=filename, error=str(exc))
        raise HTTPException(status_code=503, detail="Could not write file to SFTP — try again")

    log.info("upload.sftp_dropped", filename=filename, user_id=str(user.id))
    return {"status": "queued", "filename": filename}
