"""Batch domain model."""

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BatchStatus(enum.StrEnum):
    """Possible lifecycle states of a document classification batch."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class BatchDomain(BaseModel):
    """Read-only view of a batch, returned by the service layer.

    from_attributes=True lets Pydantic construct this from a SQLAlchemy ORM
    instance via BatchDomain.model_validate(orm_batch).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    status: BatchStatus
    created_at: datetime
