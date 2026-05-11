"""User domain model."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserDomain(BaseModel):
    """Read-only view of a user, returned by the service layer.

    hashed_password is intentionally excluded — it must never appear in
    API responses or logs.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
