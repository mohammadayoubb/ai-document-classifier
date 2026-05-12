"""FastAPI application entry point and lifespan resource manager."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.config import get_settings
from app.db.session import dispose_engine, init_engine
from app.infra.vault import VaultClient

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle: startup checks then yield, shutdown on exit.

    Startup order (each step raises RuntimeError on failure — no partial starts):
    1. Resolve secrets from Vault
    2. Verify classifier weights (SHA-256 + quality gate)
    3. Verify Casbin policy table is not empty
    4. Initialise Redis cache (fastapi-cache2)
    5. Initialise RQ job queue

    Args:
        app: The FastAPI application instance.

    Raises:
        RuntimeError: If Vault is unreachable, weights are invalid,
            or Casbin policies are missing.
    """
    settings = get_settings()
    vault_client = VaultClient(settings.vault_addr, settings.vault_token)
    if not vault_client.is_reachable():
        raise RuntimeError("Vault is unreachable or the configured token is invalid.")

    database_url = settings.build_database_url_from_vault(vault_client)
    init_engine(database_url)

    # TODO: Phase 4 — vault.get_secret() for jwt_signing_key + minio_secret_key
    # TODO: Phase 7 — load_and_verify(settings) stores model in app.state.classifier
    # TODO: Phase 5 — verify_policies_loaded() for Casbin
    # TODO: Phase 6 — FastAPICache.init(RedisBackend, prefix="docclassifier")
    # TODO: Phase 8 — JobQueue(settings.redis_url) stored in app.state.queue

    log.info("app.startup.complete")
    yield
    await dispose_engine()
    log.info("app.shutdown.complete")


app = FastAPI(
    lifespan=lifespan,
    title="Document Classifier API",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe used by docker-compose healthcheck and CI smoke test.

    Returns:
        A dict with a single "status" key set to "ok".
    """
    return {"status": "ok"}
