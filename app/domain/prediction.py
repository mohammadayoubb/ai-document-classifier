"""Prediction domain model."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PredictionDomain(BaseModel):
    """Read-only view of a prediction result, returned by the service layer.

    confidence is always in [0.0, 1.0].  top5_labels and top5_scores are
    stored as JSON array strings in the database and decoded by the caller.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    batch_id: int
    filename: str
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    top5_labels: str  # JSON array string — e.g. '["invoice", "form", ...]'
    top5_scores: str  # JSON array string — e.g. '[0.97, 0.02, ...]'
    is_relabeled: bool
    relabeled_to: str | None
    overlay_key: str | None
    created_at: datetime
