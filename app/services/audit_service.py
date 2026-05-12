"""Audit log service.

This service owns audit-log business operations.
Routes should not create audit log rows directly.
"""

from app.domain.audit import AuditLogDomain
from app.repositories.user_repo import UserRepository


class AuditService:
    """Service layer for audit log operations.

    The repository performs the SQL work, while this service controls how
    audit entries are created and exposed to the API layer.
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def record(
        self,
        actor_id: int,
        action: str,
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
        audit_entry = await self._user_repo.create_audit_entry(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata=metadata,
        )

        # Convert ORM object into a domain model before returning upward.
        return AuditLogDomain.model_validate(audit_entry)

    async def list_audit_log(self) -> list[AuditLogDomain]:
        """Return audit log entries ordered from newest to oldest.

        Returns:
            Audit log entries converted into domain models.
        """
        entries = await self._user_repo.list_audit_log()

        # Services return domain models, not raw SQLAlchemy ORM objects.
        return [AuditLogDomain.model_validate(entry) for entry in entries]