"""User SQL repository — data access only, no business logic."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    """SQL-only data access for the users table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Look up a user by primary key."""
        statement = select(User).where(User.__table__.c.id == user_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email address."""
        statement = select(User).where(User.__table__.c.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update_role(self, user_id: int, new_role: str) -> User | None:
        """Update a user's role column.

        The repository only performs the update. It does not decide whether
        the role change is allowed.
        """
        user = await self.get_by_id(user_id)

        if user is None:
            return None

        user.role = new_role

        # Flush sends the UPDATE without committing.
        # The session dependency owns commit/rollback.
        await self._session.flush()

        return user

    async def count_by_role(self, role: str) -> int:
        """Count active users holding a specific role."""
        statement = (
            select(func.count())
            .select_from(User)
            .where(
                User.__table__.c.role == role,
                User.__table__.c.is_active.is_(True),
            )
        )

        result = await self._session.execute(statement)
        return int(result.scalar_one())