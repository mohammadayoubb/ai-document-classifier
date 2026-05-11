"""User management routes — profile, role toggle, and audit log.

Layer contract: one service call per endpoint, return a domain model.
No SQLAlchemy imports, no cache operations, no business logic.
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_admin

log = structlog.get_logger()

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(
    user: Annotated[Any, Depends(get_current_user)],
) -> Any:
    """Return the authenticated user's own profile.

    Returns:
        The current user's UserDomain model.
    """
    # TODO: Phase 6 — @cache(expire=settings.cache_ttl_me), return UserDomain
    return user


@router.put("/{user_id}/role")
async def toggle_role(
    user_id: int,
    new_role: str,
    current_user: Annotated[Any, Depends(require_admin)],
) -> Any:
    """Toggle a user's role — admin only.

    Updates the Casbin policy and writes an audit log entry.
    The affected user's permissions change on their next request, no re-login needed.

    Args:
        user_id: Primary key of the user whose role will change.
        new_role: Target role — one of "admin", "reviewer", "auditor".
        current_user: The authenticated admin performing this action.

    Returns:
        The updated UserDomain model.

    Raises:
        HTTPException: 403 if caller lacks admin role.
        HTTPException: 404 if target user does not exist.
        HTTPException: 409 if demoting the only remaining admin.
    """
    # TODO: Phase 5 — call user_service.toggle_role(user_id, new_role, current_user.id)
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/audit")
async def list_audit_log(
    user: Annotated[Any, Depends(get_current_user)],
) -> list[Any]:
    """Return the full audit log.

    Accessible by admin and auditor roles; reviewer is excluded.
    Casbin policy enforcement is added in Phase 5.

    Returns:
        A list of AuditLogDomain models ordered by timestamp descending.
    """
    # TODO: Phase 5 — enforce admin-or-auditor via Casbin, call user_service.list_audit_log()
    return []
