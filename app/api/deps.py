"""API dependency wiring.

This file centralizes FastAPI Depends() helpers.
Routes should receive repositories, services, and current users through these
dependencies instead of constructing objects inside route functions.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.fastapi_users import fastapi_users
from app.db.session import get_session
from app.domain.user import UserDomain, UserRole
from app.infra.cache import CacheAdapter
from app.repositories.audit_repo import AuditRepository
from app.repositories.batch_repo import BatchRepository
from app.repositories.prediction_repo import PredictionRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService
from app.services.batch_service import BatchService
from app.services.prediction_service import PredictionService
from app.services.user_service import UserService

# Create the fastapi-users dependency once at module level.
# This avoids calling current_user(...) repeatedly inside route signatures.
_current_active_user = fastapi_users.current_user(active=True)


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    """Create a user repository for the current request.

    The repository receives the request-scoped session and performs SQL only.
    """
    return UserRepository(session=session)


def get_audit_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditRepository:
    """Create an audit repository for the current request.

    AuditRepository performs SQL only for the audit_log table.
    """
    return AuditRepository(session=session)


def get_audit_service(
    audit_repo: Annotated[AuditRepository, Depends(get_audit_repository)],
) -> AuditService:
    """Create the audit service.

    AuditService delegates SQL work to AuditRepository.
    """
    return AuditService(audit_repo=audit_repo)


def get_user_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> UserService:
    """Create the user service.

    UserService owns role-change business rules and audit logging.
    """
    return UserService(
        user_repo=user_repo,
        audit_service=audit_service,
    )


async def get_current_user(
    current_user: Annotated[object, Depends(_current_active_user)],
) -> UserDomain:
    """Return the authenticated user as a domain model.

    fastapi-users loads the authenticated ORM user from the Bearer JWT.
    We immediately convert it to UserDomain so route files never expose or
    return the SQLAlchemy ORM object directly.
    """
    return UserDomain.model_validate(current_user)


async def require_admin(
    current_user: Annotated[UserDomain, Depends(get_current_user)],
) -> UserDomain:
    """Require the current user to be an admin.

    401 is handled by get_current_user when the JWT is missing or invalid.
    403 is returned here when the user is authenticated but lacks permission.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return current_user


async def require_reviewer_or_above(
    current_user: Annotated[UserDomain, Depends(get_current_user)],
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


async def require_admin_or_auditor(
    current_user: Annotated[UserDomain, Depends(get_current_user)],
) -> UserDomain:
    """Require permission to read the audit log.

    According to the project roles, admins and auditors can view audit logs.
    Reviewers cannot.
    """
    if current_user.role not in {UserRole.ADMIN, UserRole.AUDITOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit log access required",
        )

    return current_user


def get_cache(request: Request) -> CacheAdapter:
    """Return the process-level CacheAdapter from app.state."""
    return request.app.state.cache  # type: ignore[no-any-return]


def get_batch_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRepository:
    """Create a batch repository for the current request."""
    return BatchRepository(session=session)


def get_prediction_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PredictionRepository:
    """Create a prediction repository for the current request."""
    return PredictionRepository(session=session)


def get_batch_service(
    repo: Annotated[BatchRepository, Depends(get_batch_repository)],
    cache: Annotated[CacheAdapter, Depends(get_cache)],
) -> BatchService:
    """Create the batch service with injected repo and cache."""
    return BatchService(repo=repo, cache=cache)


def get_prediction_service(
    repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
    cache: Annotated[CacheAdapter, Depends(get_cache)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> PredictionService:
    """Create the prediction service with injected repo, cache, and audit."""
    return PredictionService(repo=repo, cache=cache, audit=audit)