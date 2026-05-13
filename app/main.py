"""FastAPI application entry point and lifespan resource manager."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.routes import audit, users
from app.auth.backend import auth_backend
from app.auth.fastapi_users import fastapi_users
from app.auth.schemas import AuthUserCreate, AuthUserRead
from app.config import get_settings
from app.infra.casbin_enforcer import verify_policies_loaded
from app.infra.vault import VaultClient

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: startup checks then yield, shutdown on exit.

    Startup order, each step raises RuntimeError on failure so the app does
    not partially start in an unsafe state:
    1. Resolve secrets from Vault
    2. Verify classifier weights, SHA-256, and quality gate
    3. Verify Casbin policy table is not empty
    4. Initialise Redis cache with fastapi-cache2
    5. Initialise RQ job queue

    Args:
        app: The FastAPI application instance.

    Raises:
        RuntimeError: If Vault is unreachable, weights are invalid,
            Casbin policies are missing, or another required startup
            dependency is unavailable.
    """
    settings = get_settings()

    # Phase 4 — Vault startup contract.
    # Secrets must come from Vault, not hardcoded environment variables.
    vault = VaultClient(
        addr=settings.vault_addr,
        token=settings.vault_token,
    )

    if not vault.is_reachable():
        raise RuntimeError("Vault is unreachable. Refusing to start.")

    # Store the Vault client for later startup/runtime integrations.
    app.state.vault = vault

    # Resolve secrets after Vault connectivity is confirmed.
    # These fields start empty in Settings so the app can construct Settings()
    # before Vault is available, then lifespan fills them securely.
    settings.jwt_signing_key = vault.get_secret("app", "jwt_signing_key")
    settings.minio_secret_key = vault.get_secret("app", "minio_secret_key")
    settings.sftp_password = vault.get_secret("app", "sftp_password")

    # Keep the JWT key on app.state so auth/debug integrations can inspect
    # whether startup loaded the expected secret.
    app.state.jwt_signing_key = settings.jwt_signing_key

    # TODO: Phase 7 — load_and_verify(settings) stores model in app.state.classifier.
    # Do not add a fake classifier here. The app should only pass this check
    # after the real classifier artifact integration exists.

    # Phase 5 — Casbin startup contract.
    # The app must refuse to start if RBAC policies are missing.
    verify_policies_loaded()

    # TODO: Phase 6 — FastAPICache.init(RedisBackend, prefix="docclassifier").
    # TODO: Phase 8 — JobQueue(settings.redis_url) stored in app.state.queue.

    log.info("app.startup.complete")
    yield
    log.info("app.shutdown.complete")


app = FastAPI(
    lifespan=lifespan,
    title="Document Classifier API",
    version="0.1.0",
)

# fastapi-users generated routes.
# POST /auth/jwt/login returns a JWT access token.
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# POST /auth/register creates a new user.
# New users should default to auditor through the User ORM role default.
app.include_router(
    fastapi_users.get_register_router(AuthUserRead, AuthUserCreate),
    prefix="/auth",
    tags=["auth"],
)

# Project routes.
# Route files stay HTTP-only and do not construct the FastAPI app themselves.
app.include_router(users.router)
app.include_router(audit.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe used by docker-compose healthcheck and CI smoke test.

    Returns:
        A dict with a single "status" key set to "ok".
    """
    return {"status": "ok"}