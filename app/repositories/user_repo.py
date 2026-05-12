"""User and audit log SQL repository — data access only, no business logic."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


class UserRepository:
    """SQL-only data access for the users and audit_log tables.

    This repository must not contain HTTP errors, permission checks,
    cache invalidation, or business rules. Those belong in the service layer.

    Args:
        session: Async database session injected via Depends().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Look up a user by primary key.

        Args:
            user_id: The user primary key.

        Returns:
            The User ORM instance, or None if not found.
        """
        statement = select(User).where(User.id == user_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email address.

        Args:
            email: The email address to search for.

        Returns:
            The User ORM instance, or None if not found.
        """
        statement = select(User).where(User.email == email)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def update_role(self, user_id: int, new_role: str) -> User | None:
        """Update a user's role column.

        This method only performs the database update. It does not decide
        whether the role change is allowed.

        Args:
            user_id: The user primary key.
            new_role: The new role string.

        Returns:
            The updated User ORM instance, or None if the user was not found.
        """
        user = await self.get_by_id(user_id)

        if user is None:
            return None

        user.role = new_role

        # Flush sends the UPDATE to the database inside the current transaction.
        # The session dependency still owns the final commit or rollback.
        await self._session.flush()

        return user

    async def count_by_role(self, role: str) -> int:
        """Count users holding a specific role.

        Used by the service layer to prevent demotion of the last admin.
        The repository only counts rows; it does not make the business decision.

        Args:
            role: The role string to count.

        Returns:
            The number of active users holding that role.
        """
        statement = (
            select(func.count())
            .select_from(User)
            .where(User.role == role, User.is_active.is_(True))
        )

        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def create_audit_entry(
        self,
        actor_id: int,
        action: str,
        target: str,
        metadata: str | None,
    ) -> AuditLog:
        """Insert an immutable audit log row.

        Args:
            actor_id: Primary key of the user performing the action.
            action: Event type string.
            target: Human-readable description of what changed.
            metadata: Optional JSON-serialised extra context.

        Returns:
            The newly inserted AuditLog ORM instance.
        """
        audit_entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_=metadata,
        )

        self._session.add(audit_entry)

        # Flush makes generated values such as id and timestamp available
        # before the service converts this ORM object into a domain model.
        await self._session.flush()

        return audit_entry

    async def list_audit_log(self) -> list[AuditLog]:
        """Return all audit log rows ordered by timestamp descending.

        Returns:
            A list of AuditLog ORM instances.
        """
        statement = select(AuditLog).order_by(AuditLog.timestamp.desc())
        result = await self._session.execute(statement)
        return list(result.scalars().all())