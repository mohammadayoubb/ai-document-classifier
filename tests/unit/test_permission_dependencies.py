"""Unit tests for role permission dependencies.

These tests call dependency functions directly.
They verify the project role rules without needing a running FastAPI app.
"""

from datetime import datetime

import pytest
from fastapi import HTTPException

from app.api.deps import require_admin, require_admin_or_auditor, require_reviewer_or_above
from app.domain.user import UserDomain, UserRole


def make_user(role: UserRole) -> UserDomain:
    """Build a UserDomain object with the requested role."""
    return UserDomain(
        id=1,
        email="user@test.com",
        role=role,
        is_active=True,
        created_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_admin_dependency_allows_admin() -> None:
    """Admin-only dependency should allow admins."""
    user = make_user(UserRole.ADMIN)

    result = await require_admin(user)

    assert result.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_admin_dependency_rejects_auditor() -> None:
    """Admin-only dependency should reject auditors."""
    user = make_user(UserRole.AUDITOR)

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_reviewer_or_above_allows_reviewer() -> None:
    """Reviewer dependency should allow reviewers."""
    user = make_user(UserRole.REVIEWER)

    result = await require_reviewer_or_above(user)

    assert result.role == UserRole.REVIEWER


@pytest.mark.asyncio
async def test_reviewer_or_above_rejects_auditor() -> None:
    """Reviewer dependency should reject auditors."""
    user = make_user(UserRole.AUDITOR)

    with pytest.raises(HTTPException) as exc_info:
        await require_reviewer_or_above(user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_access_allows_auditor() -> None:
    """Audit log access should allow auditors."""
    user = make_user(UserRole.AUDITOR)

    result = await require_admin_or_auditor(user)

    assert result.role == UserRole.AUDITOR


@pytest.mark.asyncio
async def test_audit_log_access_rejects_reviewer() -> None:
    """Audit log access should reject reviewers."""
    user = make_user(UserRole.REVIEWER)

    with pytest.raises(HTTPException) as exc_info:
        await require_admin_or_auditor(user)

    assert exc_info.value.status_code == 403