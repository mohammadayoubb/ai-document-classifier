"""Prediction domain models — Pydantic shapes for classifier output.

Services convert database prediction rows into these models after decoding
JSON fields and calculating review status.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PredictionRead(BaseModel):
    """Read model with decoded top-5 classifier output."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    filename: str
    storage_key: str | None = None
    overlay_key: str | None = None
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    top5_labels: list[str]
    top5_scores: list[float]
    needs_review: bool
    is_relabeled: bool
    relabeled_to: str | None = None
    relabeled_by: int | None = None
    created_at: datetime


class RecentPredictionsResponse(BaseModel):
    """Paginated recent prediction read model."""

    items: list[PredictionRead]
    total: int
    limit: int


PredictionDomain = PredictionRead
