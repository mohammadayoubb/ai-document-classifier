"""User and audit log SQL repository — data access only, no business logic."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, User


class UserRepository:
    """SQL-only data access for the users and audit_log tables.

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
        # TODO: Phase 4
        return None

    async def get_by_email(self, email: str) -> User | None:
        """Look up a user by email address.

        Args:
            email: The email address to search for.

        Returns:
            The User ORM instance, or None if not found.
        """
        # TODO: Phase 4
        return None

    async def update_role(self, user_id: int, new_role: str) -> User:
        """Update a user's role column.

        Args:
            user_id: The user primary key.
            new_role: The new role string.

        Returns:
            The updated User ORM instance.
        """
        # TODO: Phase 5
        ...  # type: ignore[return-value]

    async def count_by_role(self, role: str) -> int:
        """Count users holding a specific role.

        Used by the service layer to prevent demotion of the last admin.

        Args:
            role: The role string to count.

        Returns:
            The number of active users holding that role.
        """
        # TODO: Phase 5
        return 0

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
        # TODO: Phase 5
        ...  # type: ignore[return-value]

    async def list_audit_log(self) -> list[AuditLog]:
        """Return all audit log rows ordered by timestamp descending.

        Returns:
            A list of AuditLog ORM instances.
        """
        # TODO: Phase 5
        return []
