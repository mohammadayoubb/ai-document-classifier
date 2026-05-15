"""Audit log domain models — Pydantic shapes for governance events.

These models represent audit log data outside the database layer.
They are used as service return types and API response models.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AuditAction(StrEnum):
    """Allowed audit actions in the system.

    Keeping audit actions as an enum prevents random action strings from being
    written to the audit log.
    """

    ROLE_CHANGE = "role_change"
    RELABEL = "relabel"
    BATCH_STATE_CHANGE = "batch_state_change"


class AuditLogDomain(BaseModel):
    """Read-only audit log entry returned by the service layer.

    The API should return this domain model instead of exposing the SQLAlchemy
    AuditLog ORM object directly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int
    action: AuditAction
    target: str
    metadata_: str | None
    timestamp: datetime
