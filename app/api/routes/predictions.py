"""Prediction routes — recent listing and reviewer relabeling.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_reviewer_or_above

log = structlog.get_logger()

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/recent")
async def list_recent_predictions(
    user: Annotated[Any, Depends(get_current_user)],
) -> list[Any]:
    """List the most recent predictions across all batches.

    Returns:
        A list of PredictionDomain objects ordered by creation time descending.
    """
    # TODO: Phase 6 — @cache(expire=settings.cache_ttl_recent), call prediction_service.list_recent()
    return []


@router.patch("/{pred_id}/relabel")
async def relabel_prediction(
    pred_id: int,
    new_label: str,
    user: Annotated[Any, Depends(require_reviewer_or_above)],
) -> Any:
    """Relabel a prediction — reviewer or admin only.

    Relabeling is only allowed when the prediction's top-1 confidence is
    below settings.low_confidence_threshold (0.7). Writes an audit log entry.

    Args:
        pred_id: Primary key of the prediction to relabel.
        new_label: The corrected document class label.
        user: The authenticated reviewer or admin.

    Returns:
        The updated PredictionDomain object.

    Raises:
        HTTPException: 403 if caller lacks reviewer role.
        HTTPException: 404 if the prediction does not exist.
        HTTPException: 422 if confidence >= 0.7 (high-confidence predictions
            are not eligible for relabeling).
    """
    # TODO: Phase 6 — call prediction_service.relabel(pred_id, new_label, user.id)
    raise HTTPException(status_code=501, detail="Not implemented")
