"""fastapi-users user manager.

This file connects fastapi-users to our SQLAlchemy user table and controls
registration/password validation behavior.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, IntegerIDMixin, InvalidPasswordException, schemas
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import User
from app.db.session import get_session

log = structlog.get_logger()


async def get_user_db(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, int], None]:
    """Provide the fastapi-users database adapter.

    This adapter is the bridge between fastapi-users and our SQLAlchemy User ORM
    model. It stays in the auth package instead of route files.
    """
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Application user manager for fastapi-users.

    This class controls auth-specific behavior such as password validation and
    post-registration hooks. RBAC role changes are still handled by UserService.
    """

    def __init__(self, user_db: SQLAlchemyUserDatabase[User, int]) -> None:
        super().__init__(user_db)

        settings = get_settings()

        # fastapi-users uses these secrets for password reset / verification flows.
        # We reuse the Vault-resolved JWT signing key so no auth secret is hardcoded.
        self.reset_password_token_secret = settings.jwt_signing_key
        self.verification_token_secret = settings.jwt_signing_key

    async def validate_password(
        self,
        password: str,
        user: schemas.BaseUserCreate | User,
    ) -> None:
        """Validate password strength during registration.

        Args:
            password: Plain-text password submitted by the registering user.
            user: Optional user creation payload.

      The signature matches fastapi-users' expected override.
        """
        _ = user

        if len(password) < 8:
            raise InvalidPasswordException(
                reason="Password must be at least 8 characters long."
            )

        if password.isdigit():
            raise InvalidPasswordException(
                reason="Password cannot contain only numbers."
            )

    async def on_after_register(
        self,
        user: User,
        request: Request | None = None,
    ) -> None:
        """Log a successful registration without exposing sensitive data."""
        _ = request

        log.info(
            "auth.user_registered",
            user_id=user.id,
            email=user.email,
            role=user.role,
        )


async def get_user_manager(
    user_db: Annotated[SQLAlchemyUserDatabase[User, int], Depends(get_user_db)],
) -> AsyncGenerator[UserManager, None]:
    """Provide the fastapi-users user manager."""
    yield UserManager(user_db)