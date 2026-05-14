"""Batch listing and detail routes.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile

from app.api.deps import get_batch_service, get_current_user
from app.domain.batch import BatchDetail, BatchDomain, BatchStatus, PaginatedBatchSummary
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


@router.post("/upload", response_model=BatchDomain, status_code=201)
async def upload_document(
    file: UploadFile,
    request: Request,
    user: Annotated[UserDomain, Depends(get_current_user)],
    service: Annotated[BatchService, Depends(get_batch_service)],
) -> BatchDomain:
    """Upload a document directly and enqueue it for classification.

    Accepts any image file (TIFF, PNG, JPEG). Validates size and format,
    uploads to MinIO, creates a Batch row, and enqueues an RQ inference job.
    This bypasses SFTP — useful for manual testing and the UI upload button.

    Args:
        file: The uploaded image file.
        request: FastAPI request (used to access app.state infra).
        user: The authenticated user (any role).
        service: Injected batch service.

    Returns:
        The created BatchDomain with status=pending.

    Raises:
        HTTPException: 400 if the file is empty, too large, or not a valid image.
    """
    data = await file.read()
    filename = file.filename or "upload"
    batch = await service.create_batch_from_upload(
        data=data,
        filename=filename,
        owner_id=user.id,
        blob=request.app.state.blob,
        queue=request.app.state.queue,
    )
    return batch
