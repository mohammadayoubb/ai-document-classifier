"""fastapi-users schemas.

These schemas are used only by fastapi-users auth/register routes.
They are separate from our domain models so authentication concerns do not
leak into the rest of the app.
"""

from datetime import datetime

from fastapi_users import schemas

from app.domain.user import UserRole


class AuthUserRead(schemas.BaseUser[int]):
    """Public user shape returned by fastapi-users routes.

    hashed_password is intentionally not included because password hashes must
    never appear in API responses or logs.
    """

    role: UserRole
    created_at: datetime


class AuthUserCreate(schemas.BaseUserCreate):
    """Registration request schema.

    We intentionally do not expose a role field here. New registered users
    should receive the database default role: auditor.
    """


class AuthUserUpdate(schemas.BaseUserUpdate):
    """User update schema used by fastapi-users.

    Role changes should not happen through this schema. Role changes are handled
    by our explicit admin-only role-toggle endpoint so they can be audited.
    """