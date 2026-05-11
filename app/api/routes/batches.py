"""Batch listing routes.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("")
async def list_batches(
    user: Annotated[Any, Depends(get_current_user)],
) -> list[Any]:
    """List all batches visible to the authenticated user.

    Returns:
        A list of BatchDomain objects ordered by creation time descending.
    """
    # TODO: Phase 6 — @cache(expire=settings.cache_ttl_batches), call batch_service.list_all()
    return []


@router.get("/{batch_id}")
async def get_batch(
    batch_id: int,
    user: Annotated[Any, Depends(get_current_user)],
) -> Any:
    """Return a single batch by primary key.

    Args:
        batch_id: The batch primary key.
        user: The authenticated user (any role).

    Returns:
        A BatchDomain object.

    Raises:
        HTTPException: 404 if no batch with that ID exists.
    """
    # TODO: Phase 6 — @cache(expire=settings.cache_ttl_batch), call batch_service.get_by_id()
    raise HTTPException(status_code=404, detail="Not implemented")
