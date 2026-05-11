"""User and audit log business logic — role management and event recording."""

from typing import Any

import structlog

log = structlog.get_logger()


class UserService:
    """Manages user role changes, audit logging, and user cache invalidation.

    Args:
        repo: The UserRepository for SQL operations.
        cache: The CacheAdapter for invalidating user profile caches.
    """

    def __init__(self, repo: Any, cache: Any) -> None:
        self._repo = repo
        self._cache = cache

    async def toggle_role(self, user_id: int, new_role: str, actor_id: int) -> Any:
        """Change a user's role, update Casbin policy, and write an audit log entry.

        Guards against demoting the last admin — raises ValueError in that case.
        Invalidates the affected user's profile cache so the change takes effect
        on their next request without requiring re-login.

        Args:
            user_id: Primary key of the user whose role will change.
            new_role: The new role — one of "admin", "reviewer", "auditor".
            actor_id: Primary key of the admin performing the change.

        Returns:
            The updated UserDomain instance.

        Raises:
            LookupError: If the target user does not exist.
            ValueError: If this would demote the only remaining admin.
        """
        # TODO: Phase 5
        ...  # type: ignore[return-value]

    async def record_audit(
        self,
        actor_id: int,
        action: str,
        target: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write an immutable audit log entry.

        Called from services only — never invoked from routes.

        Args:
            actor_id: Primary key of the user performing the action.
            action: Event type — "role_change", "relabel", or "batch_state_change".
            target: Human-readable description of what changed.
            metadata: Optional JSON-serialisable extra context (e.g., old/new role).
        """
        # TODO: Phase 5
        ...

    async def list_audit_log(self) -> list[Any]:
        """Return all audit log entries ordered by timestamp descending.

        Returns:
            A list of AuditLogDomain instances.
        """
        # TODO: Phase 5
        return []
