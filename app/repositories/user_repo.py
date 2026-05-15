"""User SQL repository — owns only database reads/writes for users.

Role safety rules and audit logging belong in UserService; this file only
executes SQL and returns ORM objects.
"""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    """SQL-only data access for the users and audit_log tables."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLAlchemy session used by user queries.

        Args:
            session: Async SQLAlchemy session owned by the caller.
        """
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Look up a user by primary key.

        Args:
            user_id: User primary key.

        Returns:
            User ORM object, or None when the user does not exist.
        """
        # DB CALL: direct primary-key lookup through SQLAlchemy session.
        return cast(User | None, await self._session.get(User, user_id))

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email address.

        Args:
            email: User email address.

        Returns:
            User ORM object, or None when the email is not registered.
        """
        stmt = select(User).where(User.email == email)

        # DB CALL: enforce email lookup through the repository layer.
        result = await self._session.execute(stmt)
        return cast(User | None, result.scalar_one_or_none())

    async def update_role(self, user_id: int, new_role: str) -> User | None:
        """Update a user's role column.

        Args:
            user_id: User primary key.
            new_role: New role value to persist.

        Returns:
            Updated User ORM object, or None if not found.
        """
        # DB CALL: load row before mutating the role column.
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.role = new_role

        # DB CALL: persist role change and refresh the ORM object.
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def list_all(self) -> list[User]:
        """Return all users ordered by id.

        Returns:
            A list of User ORM rows.
        """
        stmt = select(User).order_by(User.id)

        # DB CALL: load users for the admin user-management table.
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_role(self, role: str) -> int:
        """Count active users holding a specific role.

        Args:
            role: Role value to count.

        Returns:
            Number of active users with the role.
        """
        stmt = select(func.count(User.id)).where(
            User.role == role,
            User.is_active.is_(True),
        )

        # DB CALL: used by service safety rule that protects the last admin.
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
