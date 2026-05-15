"""User service.

This service owns user-related business logic such as role changes,
audit logging, and safety checks.
"""

import json

from app.domain.audit import AuditAction
from app.domain.user import UserDomain, UserRole
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService


class UserNotFoundError(Exception):
    """Raised when a requested user does not exist."""


class CannotDemoteLastAdminError(Exception):
    """Raised when the last active admin tries to remove their own admin role."""


class UserService:
    """Service layer for user operations.

    This class contains business rules. Repositories only perform SQL queries,
    while routes only translate service results/errors into HTTP responses.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        audit_service: AuditService,
    ) -> None:
        """Store service dependencies.

        Args:
            user_repo: Repository responsible for user SQL.
            audit_service: Service responsible for audit log writes.
        """
        self._user_repo = user_repo
        self._audit_service = audit_service

    async def list_users(self) -> list[UserDomain]:
        """Return all registered users.

        Returns:
            All users converted to domain models.
        """
        # REPOSITORY CALL: load admin user-management table rows.
        users = await self._user_repo.list_all()

        # DOMAIN MAP: services expose Pydantic models, not ORM objects.
        return [UserDomain.model_validate(u) for u in users]

    async def get_user_by_id(self, user_id: int) -> UserDomain:
        """Return a user by ID.

        Args:
            user_id: User primary key.

        Returns:
            The user as a domain model.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        # REPOSITORY CALL: load one user before mapping to domain model.
        user = await self._user_repo.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError(f"User {user_id} was not found")

        return UserDomain.model_validate(user)

    async def change_user_role(
        self,
        *,
        actor_id: int,
        target_user_id: int,
        new_role: UserRole,
    ) -> UserDomain:
        """Change a user's role and write an audit log entry.

        Args:
            actor_id: ID of the admin performing the change.
            target_user_id: ID of the user whose role is being changed.
            new_role: New role to assign.

        Returns:
            Updated user as a domain model.

        Raises:
            UserNotFoundError: If the target user does not exist.
            CannotDemoteLastAdminError: If the last active admin tries to
                demote themselves.
        """
        # REPOSITORY CALL: load target user before applying role rules.
        target_user = await self._user_repo.get_by_id(target_user_id)

        if target_user is None:
            raise UserNotFoundError(f"User {target_user_id} was not found")

        old_role = UserRole(target_user.role)

        # Safety rule: the system must always keep at least one active admin.
        # This prevents the only admin from locking the team out of role management.
        if (
            actor_id == target_user_id
            and old_role == UserRole.ADMIN
            and new_role != UserRole.ADMIN
        ):
            # REPOSITORY CALL: enforce "at least one admin" safety rule.
            admin_count = await self._user_repo.count_by_role(UserRole.ADMIN.value)

            if admin_count <= 1:
                raise CannotDemoteLastAdminError(
                    "The last active admin cannot demote themselves"
                )

        # REPOSITORY CALL: persist the role change.
        updated_user = await self._user_repo.update_role(
            user_id=target_user_id,
            new_role=new_role.value,
        )

        if updated_user is None:
            raise UserNotFoundError(f"User {target_user_id} was not found")

        # AUDIT CALL: role changes are audit-able events and must always be recorded.
        await self._audit_service.record(
            actor_id=actor_id,
            action=AuditAction.ROLE_CHANGE,
            target=f"user:{target_user_id}",
            metadata=json.dumps(
                {
                    "old_role": old_role.value,
                    "new_role": new_role.value,
                }
            ),
        )

        # TODO: Inject CacheAdapter later and invalidate the target user's /users/me cache.
        # Cache invalidation belongs here in the service layer, never in routes or repositories.

        # DOMAIN MAP: return a service/domain model to the route layer.
        return UserDomain.model_validate(updated_user)
