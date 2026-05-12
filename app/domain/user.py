"""User domain model.

This file contains Pydantic models used by the service and API layers.
It must stay separate from SQLAlchemy ORM models.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRole(StrEnum):
    """Allowed roles in the system.

    Keeping roles as an enum prevents invalid role strings from spreading
    through the codebase, such as "Admin", "manager", or "review".
    """

    ADMIN = "admin"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"


class UserDomain(BaseModel):
    """Read-only view of a user, returned by the service layer.

    hashed_password is intentionally excluded because it must never appear
    in API responses, logs, or cached response payloads.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime