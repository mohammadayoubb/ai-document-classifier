"""User and audit log SQL repository — data access only, no business logic."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


class UserRepository:
    """SQL-only data access for the users and audit_log tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Look up a user by primary key."""
        return cast(User | None, await self._session.get(User, user_id))

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email address."""
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return cast(User | None, result.scalar_one_or_none())

    async def update_role(self, user_id: int, new_role: str) -> User | None:
        """Update a user's role column."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.role = new_role
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def count_by_role(self, role: str) -> int:
        """Count active users holding a specific role."""
        stmt = select(func.count(User.id)).where(
            User.role == role,
            User.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def create_audit_entry(
        self,
        actor_id: int,
        action: str,
        target: str,
        metadata: str | None,
    ) -> AuditLog:
        """Insert an immutable audit log row."""
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_=metadata,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def list_audit_log(self, limit: int = 100, offset: int = 0) -> list[AuditLog]:
        """Return audit log rows ordered by timestamp descending."""
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
