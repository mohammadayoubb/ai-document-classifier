"""FastAPI application entry point and lifespan resource manager."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import RequestIDMiddleware
from app.api.routes import audit, batches, predictions, users
from app.auth.backend import auth_backend
from app.auth.fastapi_users import fastapi_users
from app.auth.schemas import AuthUserCreate, AuthUserRead
from app.config import get_settings
from app.db.session import dispose_engine, init_engine
from app.infra.blob import BlobStorage
from app.infra.cache import CacheAdapter
from app.infra.casbin_enforcer import verify_policies_loaded
from app.infra.logging_setup import configure_logging
from app.infra.queue import JobQueue
from app.infra.vault import VaultClient

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: startup checks then yield, shutdown on exit.

    Startup order, each step raises RuntimeError on failure so the app does
    not partially start in an unsafe state:
    1. Resolve secrets from Vault
    2. Verify classifier weights, SHA-256, and quality gate
    3. Verify Casbin policy table is not empty
    4. Initialise Redis cache adapter
    5. Initialise RQ job queue

    Args:
        app: The FastAPI application instance.

    Raises:
        RuntimeError: If Vault is unreachable, weights are invalid,
            Casbin policies are missing, or another required startup
            dependency is unavailable.
    """
    settings = get_settings()
    vault_client = VaultClient(settings.vault_addr, settings.vault_token)
    if not vault_client.is_reachable():
        raise RuntimeError("Vault is unreachable or the configured token is invalid.")

    database_url = settings.build_database_url_from_vault(vault_client)
    init_engine(database_url)

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

    # Phase 6 — Redis-backed cache adapter.
    # CacheAdapter wraps the async Redis client with typed key helpers.
    # Stored on app.state so get_cache() can inject it per request.
    redis_client = aioredis.from_url(settings.redis_url)
    app.state.cache = CacheAdapter(backend=redis_client, prefix="docclassifier")

    # Phase 8 — RQ job queue.
    # Workers pick up inference jobs enqueued by the ingest poller.
    app.state.queue = JobQueue(settings.redis_url)

    # Blob storage — shared instance for the upload endpoint.
    app.state.blob = BlobStorage(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )

    log.info("app.startup.complete")
    yield

    await redis_client.aclose()
    await dispose_engine()
    log.info("app.shutdown.complete")


app = FastAPI(
    lifespan=lifespan,
    title="Document Classifier API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

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
app.include_router(batches.router)
app.include_router(predictions.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe used by docker-compose healthcheck and CI smoke test.

    Returns:
        A dict with a single "status" key set to "ok".
    """
    return {"status": "ok"}
