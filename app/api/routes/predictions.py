"""Prediction routes — recent listing and reviewer relabeling.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_prediction_service, require_reviewer_or_above
from app.domain.prediction import PredictionRead, RecentPredictionsResponse
from app.domain.user import UserDomain
from app.services.prediction_service import PredictionService

log = structlog.get_logger()

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/recent", response_model=RecentPredictionsResponse)
async def list_recent_predictions(
    user: Annotated[UserDomain, Depends(get_current_user)],
    service: Annotated[PredictionService, Depends(get_prediction_service)],
    limit: int = Query(default=20, ge=1, le=100),
    only_needs_review: bool = Query(default=False),
) -> RecentPredictionsResponse:
    """List the most recent predictions across all batches.

    Args:
        user: The authenticated user (any role).
        service: Injected prediction service.
        limit: Maximum number of predictions to return (1–100).
        only_needs_review: When true, return only low-confidence unreviewed items.

    Returns:
        A recent predictions response ordered by creation time descending.
    """
    return await service.list_recent(limit=limit, only_needs_review=only_needs_review)


@router.patch("/{pred_id}/relabel", response_model=PredictionRead)
async def relabel_prediction(
    pred_id: int,
    new_label: str,
    user: Annotated[UserDomain, Depends(require_reviewer_or_above)],
    service: Annotated[PredictionService, Depends(get_prediction_service)],
) -> PredictionRead:
    """Relabel a prediction — reviewer or admin only.

    Relabeling is only allowed when the prediction's top-1 confidence is
    below settings.low_confidence_threshold (0.7). Writes an audit log entry.

    Args:
        pred_id: Primary key of the prediction to relabel.
        new_label: The corrected document class label (must be a configured label).
        user: The authenticated reviewer or admin.
        service: Injected prediction service.

    Returns:
        The updated PredictionRead object.

    Raises:
        HTTPException: 403 if caller lacks reviewer role.
        HTTPException: 404 if the prediction does not exist.
        HTTPException: 422 if confidence >= 0.7 or label is not a known class.
    """
    try:
        return await service.relabel(pred_id, new_label, actor_id=user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
