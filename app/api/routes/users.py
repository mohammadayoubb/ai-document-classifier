"""User API routes.

Routes are HTTP-only:
- receive dependencies with Depends()
- call service methods
- convert service errors into HTTP responses
- return domain models
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_user_service, require_admin
from app.domain.user import UserDomain, UserRoleUpdateRequest
from app.services.user_service import (
    CannotDemoteLastAdminError,
    UserNotFoundError,
    UserService,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserDomain])
async def list_users(
    current_user: Annotated[UserDomain, Depends(require_admin)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> list[UserDomain]:
    """Return all registered users. Admin only."""
    return await user_service.list_users()


@router.get("/me", response_model=UserDomain)
async def get_me(
    current_user: Annotated[UserDomain, Depends(get_current_user)],
) -> UserDomain:
    """Return the current authenticated user.

    This endpoint is for any authenticated user, not only admins.
    """
    return current_user


@router.put("/{user_id}/role", response_model=UserDomain)
async def update_user_role(
    user_id: int,
    payload: UserRoleUpdateRequest,
    current_user: Annotated[UserDomain, Depends(require_admin)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserDomain:
    """Update a user's role.

    Only admins can call this route. The route delegates business rules to
    UserService, including the last-admin safety check.
    """
    try:
        return await user_service.change_user_role(
            actor_id=current_user.id,
            target_user_id=user_id,
            new_role=payload.new_role,
        )
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    except CannotDemoteLastAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote the last active admin",
        ) from exc