"""Audit log SQL repository — data access only, no business logic."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditRepository:
    """SQL-only data access for the audit_log table.

    This repository must not decide when something should be audited.
    It only inserts and reads audit log rows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
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

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[AuditLog]:
        """Return audit log rows ordered by timestamp descending.

        Args:
            limit: Maximum number of rows to return.
            offset: Number of rows to skip.

        Returns:
            A list of AuditLog ORM instances.
        """
        statement = (
            select(AuditLog)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)
        return list(result.scalars().all())