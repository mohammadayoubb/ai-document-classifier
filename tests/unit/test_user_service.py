"""Unit tests for UserService.

These tests focus on business logic only.
They do not use FastAPI routes and they do not require a real database.
"""

from datetime import datetime

import pytest

from app.domain.audit import AuditAction
from app.domain.user import UserRole
from app.services.user_service import CannotDemoteLastAdminError, UserService


class FakeUser:
    """Small fake ORM-like user object for service unit tests."""

    def __init__(self, user_id: int, role: str) -> None:
        self.id = user_id
        self.email = f"user{user_id}@test.com"
        self.role = role
        self.is_active = True
        self.created_at = datetime.now()


class FakeUserRepository:
    """Fake repository that mimics the methods UserService needs."""

    def __init__(self) -> None:
        self.users = {
            1: FakeUser(user_id=1, role="admin"),
            2: FakeUser(user_id=2, role="auditor"),
        }
        self.admin_count = 1

    async def get_by_id(self, user_id: int) -> FakeUser | None:
        """Return a fake user by ID."""
        return self.users.get(user_id)

    async def update_role(self, user_id: int, new_role: str) -> FakeUser | None:
        """Update the fake user's role."""
        user = self.users.get(user_id)

        if user is None:
            return None

        user.role = new_role
        return user

    async def count_by_role(self, role: str) -> int:
        """Count fake users by role."""
        if role == "admin":
            return self.admin_count

        return sum(1 for user in self.users.values() if user.role == role)


class FakeAuditService:
    """Fake audit service used to verify audit logging behavior."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(
        self,
        actor_id: int,
        action: AuditAction,
        target: str,
        metadata: str | None = None,
    ) -> None:
        """Store audit calls in memory."""
        self.records.append(
            {
                "actor_id": actor_id,
                "action": action,
                "target": target,
                "metadata": metadata,
            }
        )


@pytest.mark.asyncio
async def test_admin_can_change_user_role_and_audit_is_written() -> None:
    """Changing a role should update the user and write an audit entry."""
    user_repo = FakeUserRepository()
    audit_service = FakeAuditService()
    service = UserService(user_repo=user_repo, audit_service=audit_service)

    updated_user = await service.change_user_role(
        actor_id=1,
        target_user_id=2,
        new_role=UserRole.REVIEWER,
    )

    assert updated_user.role == UserRole.REVIEWER
    assert len(audit_service.records) == 1
    assert audit_service.records[0]["action"] == AuditAction.ROLE_CHANGE
    assert audit_service.records[0]["target"] == "user:2"


@pytest.mark.asyncio
async def test_last_admin_cannot_demote_themselves() -> None:
    """The service should prevent the only admin from removing their admin role."""
    user_repo = FakeUserRepository()
    user_repo.admin_count = 1

    audit_service = FakeAuditService()
    service = UserService(user_repo=user_repo, audit_service=audit_service)

    with pytest.raises(CannotDemoteLastAdminError):
        await service.change_user_role(
            actor_id=1,
            target_user_id=1,
            new_role=UserRole.AUDITOR,
        )

    # No audit entry should be written because the role change did not happen.
    assert audit_service.records == []