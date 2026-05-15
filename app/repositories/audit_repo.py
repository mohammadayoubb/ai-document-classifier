"""Audit log SQL repository — owns only database reads/writes for audit rows.

Services decide when an action is audit-worthy. This repository only persists
and reads immutable audit records.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditRepository:
    """SQL-only data access for the audit_log table.

    This repository must not decide when something should be audited.
    It only inserts and reads audit log rows.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLAlchemy session used by audit queries.

        Args:
            session: Async SQLAlchemy session owned by the caller.
        """
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

        # DB WRITE: stage immutable audit row in the current transaction.
        self._session.add(audit_entry)

        # DB CALL: flush makes id/timestamp available before domain mapping.
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

        # DB CALL: read recent audit rows for admin/auditor views.
        result = await self._session.execute(statement)
        return list(result.scalars().all())
