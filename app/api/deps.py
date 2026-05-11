"""FastAPI dependency injection functions shared across all routes.

All Depends() callables live here. Routes declare what they need; this module
delivers it. No route body constructs any collaborator directly.
"""

from typing import Annotated, Any

import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

log = structlog.get_logger()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/jwt/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Any:
    """Decode JWT and return the authenticated user.

    Args:
        token: Bearer token extracted from the Authorization header.
        session: Injected async database session.

    Returns:
        The authenticated UserDomain object (resolved in Phase 4).

    Raises:
        HTTPException: 401 if the token is missing, expired, or invalid.
    """
    # TODO: Phase 4 — decode JWT with app.state.jwt_key, load UserDomain from DB
    raise HTTPException(status_code=401, detail="Authentication not yet implemented")


async def require_admin(
    user: Annotated[Any, Depends(get_current_user)],
) -> Any:
    """Gate access to admin-only endpoints.

    Args:
        user: The authenticated user from get_current_user.

    Returns:
        The user if they hold the admin role.

    Raises:
        HTTPException: 403 if the user lacks the admin role.
    """
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


async def require_reviewer_or_above(
    user: Annotated[Any, Depends(get_current_user)],
) -> Any:
    """Gate access to reviewer-or-admin endpoints.

    Args:
        user: The authenticated user from get_current_user.

    Returns:
        The user if they hold the reviewer or admin role.

    Raises:
        HTTPException: 403 if the user lacks the required role.
    """
    if getattr(user, "role", None) not in ("admin", "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer role required")
    return user


def get_queue(request: Request) -> Any:
    """Return the RQ job queue singleton from application state.

    Args:
        request: The incoming HTTP request.

    Returns:
        The RQ Queue instance stored in app.state.queue (set in lifespan).
    """
    return request.app.state.queue


def get_classifier(request: Request) -> Any:
    """Return the loaded ConvNeXt model from application state.

    Args:
        request: The incoming HTTP request.

    Returns:
        The PyTorch model stored in app.state.classifier (set in lifespan).
    """
    return request.app.state.classifier
