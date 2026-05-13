"""JWT authentication backend for fastapi-users.

The JWT signing key is resolved from Vault during FastAPI lifespan startup.
This module refuses to create JWT tokens if that key was not loaded.
"""

from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy

from app.config import get_settings
from app.db.models import User

# Generated login route will be POST /auth/jwt/login.
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy[User, int]:
    """Create the JWT strategy using the Vault-resolved signing key.

    Raises:
        RuntimeError: If the JWT signing key was not loaded from Vault.
    """
    settings = get_settings()

    if not settings.jwt_signing_key:
        raise RuntimeError("JWT signing key is missing. Vault startup resolution failed.")

    return JWTStrategy(
        secret=settings.jwt_signing_key,
        lifetime_seconds=settings.jwt_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)