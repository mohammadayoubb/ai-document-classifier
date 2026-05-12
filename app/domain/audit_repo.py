"""Audit log repository.

This repository owns SQL operations for the audit_log table only.
It does not contain business logic, HTTP exceptions, or cache invalidation.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditRepository:
    """SQL-only repository for audit log records."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the request-scoped database session.

        Args:
            session: Async SQLAlchemy session injected by the dependency layer.
        """
        self._session = session

    async def create(
        self,
        actor_id: int,
        action: str,
        target: str,
        metadata_: str | None = None,
    ) -> AuditLog:
        """Insert a new audit log row.

        This method only writes data. It does not decide whether an action
        should be audited; that decision belongs in the service layer.
        """
        audit_log = AuditLog(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_=metadata_,
        )

        self._session.add(audit_log)

        # Flush sends the INSERT to the DB so generated fields like id/timestamp
        # are available before the service converts the ORM object to a domain model.
        await self._session.flush()

        return audit_log

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[AuditLog]:
        """Return recent audit log entries.

        Sorting is query construction, not business logic, so it is allowed here.
        """
        statement = (
            select(AuditLog)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self._session.execute(statement)
        return list(result.scalars().all())