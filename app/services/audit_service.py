"""Audit log service.

This service owns audit-log business operations.
Routes should not create audit log rows directly.
"""

from app.domain.audit import AuditAction, AuditLogDomain
from app.repositories.audit_repo import AuditRepository


class AuditService:
    """Service layer for audit log operations.

    The repository performs the SQL work, while this service controls how
    audit entries are created and exposed to the API layer.
    """

    def __init__(self, audit_repo: AuditRepository) -> None:
        """Store the audit repository dependency.

        Args:
            audit_repo: Repository responsible for audit_log SQL.
        """
        self._audit_repo = audit_repo

    async def record(
        self,
        actor_id: int,
        action: AuditAction,
        target: str,
        metadata: str | None = None,
    ) -> AuditLogDomain:
        """Create an audit log entry.

        Args:
            actor_id: ID of the user performing the action.
            action: Type of action being audited.
            target: Human-readable target of the action.
            metadata: Optional JSON string with extra context.

        Returns:
            The created audit entry as a domain model.
        """
        # REPOSITORY CALL: persist immutable audit event.
        audit_entry = await self._audit_repo.create(
            actor_id=actor_id,
            action=action.value,
            target=target,
            metadata=metadata,
        )

        # Services return domain models, not raw SQLAlchemy ORM objects.
        return AuditLogDomain.model_validate(audit_entry)

    async def list_audit_log(self) -> list[AuditLogDomain]:
        """Return audit log entries ordered from newest to oldest.

        Returns:
            Audit log entries converted into domain models.
        """
        # REPOSITORY CALL: load recent audit rows for admin/auditor views.
        entries = await self._audit_repo.list_recent()

        # Convert each ORM row into a Pydantic domain model before returning.
        return [AuditLogDomain.model_validate(entry) for entry in entries]
