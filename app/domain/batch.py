"""Batch domain models."""

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.prediction import PredictionRead


class BatchStatus(enum.StrEnum):
    """Possible lifecycle states of a document classification batch."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class BatchDomain(BaseModel):
    """Read-only view of a batch returned by the service layer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    status: BatchStatus
    created_at: datetime
    updated_at: datetime


class BatchSummary(BatchDomain):
    """Batch list item with aggregate prediction counts."""

    prediction_count: int = Field(ge=0)
    needs_review_count: int = Field(ge=0)


class PaginatedBatchSummary(BaseModel):
    """Paginated batch list response."""

    items: list[BatchSummary]
    total: int = Field(ge=0)
    limit: int = Field(gt=0)
    offset: int = Field(ge=0)


class BatchDetail(BatchSummary):
    """Batch detail using the current Batch -> Prediction schema."""

    predictions: list[PredictionRead]
