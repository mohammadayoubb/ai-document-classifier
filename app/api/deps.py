"""API dependency wiring.

This file centralizes FastAPI Depends() helpers.
Routes should receive repositories, services, and current users through these
dependencies instead of constructing objects inside route functions.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.domain.user import UserDomain, UserRole
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.user_service import UserService


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide one database session per request.

    The dependency owns the session lifecycle:
    open session -> yield to route/service -> commit on success -> rollback on error.

    Routes should never manually commit, rollback, or close the session.
    """
    async with SessionLocal() as session:
        try:
            yield session

            # Commit happens here after the route/service finishes successfully.
            await session.commit()
        except Exception:
            # Rollback protects the DB from partial writes if anything fails.
            await session.rollback()
            raise


def get_user_repository(
    session: AsyncSession = Depends(get_session),
) -> UserRepository:
    """Create a user repository for the current request.

    The repository receives the request-scoped session and performs SQL only.
    """
    return UserRepository(session=session)


def get_audit_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> AuditService:
    """Create the audit service.

    AuditService uses the repository to write/read audit log records.
    Business decisions about when to audit belong in services, not routes.
    """
    return AuditService(user_repo=user_repo)


def get_user_service(
    user_repo: UserRepository = Depends(get_user_repository),
    audit_service: AuditService = Depends(get_audit_service),
) -> UserService:
    """Create the user service.

    UserService owns role-change business rules and calls AuditService when
    a role change must be recorded.
    """
    return UserService(
        user_repo=user_repo,
        audit_service=audit_service,
    )


async def get_current_user() -> UserDomain:
    """Return the authenticated user.

    This is a temporary placeholder until fastapi-users JWT auth is wired.
    Replace this with real JWT-based user loading in the authentication phase.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is not wired yet",
    )


async def require_admin(
    current_user: UserDomain = Depends(get_current_user),
) -> UserDomain:
    """Require the current user to be an admin.

    401 is handled by get_current_user.
    403 is returned here when the user is authenticated but lacks permission.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return current_user


async def require_reviewer_or_above(
    current_user: UserDomain = Depends(get_current_user),
) -> UserDomain:
    """Require reviewer or admin access.

    Reviewers and admins can perform review actions.
    Auditors are read-only and should fail this check.
    """
    if current_user.role not in {UserRole.ADMIN, UserRole.REVIEWER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer role required",
        )

    return current_user