"""User domain model.

This file contains Pydantic models used by the service and API layers.
It must stay separate from SQLAlchemy ORM models.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRole(StrEnum):
    """Allowed roles in the system."""

    ADMIN = "admin"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"


class UserDomain(BaseModel):
    """Read-only view of a user returned by the service layer."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class UserRoleUpdateRequest(BaseModel):
    """Request body for changing a user's role.

    Role changes must go through the admin-only route so they can be audited.
    """

    new_role: UserRole