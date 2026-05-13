"""Casbin authorization adapter.

This module owns Casbin setup and policy verification.
It belongs in app/infra because Casbin is an external authorization system.
"""

from pathlib import Path

import casbin  # type: ignore[import-untyped]
import structlog
from casbin_sqlalchemy_adapter import Adapter  # type: ignore[import-untyped]

from app.config import get_settings

log = structlog.get_logger()

# The Casbin model file defines how subjects, objects, and actions are matched.
CASBIN_MODEL_PATH = Path("app/infra/casbin_model.conf")

# Casbin enforcer is cached per process because loading policies repeatedly
# would add unnecessary database reads.
_enforcer: casbin.Enforcer | None = None


def _get_sync_database_url(database_url: str) -> str:
    """Convert async SQLAlchemy URLs into sync URLs for Casbin's adapter.

    The main app uses async SQLAlchemy, commonly with postgresql+asyncpg.
    The Casbin SQLAlchemy adapter is synchronous, so it needs a sync-style URL.

    Args:
        database_url: Application database URL from Settings.

    Returns:
        A database URL compatible with the Casbin SQLAlchemy adapter.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


def get_enforcer() -> casbin.Enforcer:
    """Return the process-level Casbin enforcer.

    Returns:
        A Casbin enforcer loaded with the configured model and DB-backed policy.
    """
    global _enforcer

    if _enforcer is None:
        settings = get_settings()
        # settings.database_url is None when the URL was built from Vault components;
        # build_database_url() assembles the URL from resolved parts regardless.
        sync_database_url = _get_sync_database_url(settings.build_database_url())

        # The adapter stores policies in the casbin_rule table.
        adapter = Adapter(sync_database_url)

        _enforcer = casbin.Enforcer(str(CASBIN_MODEL_PATH), adapter)

        # Policies must be loaded before the enforcer can make decisions.
        _enforcer.load_policy()

        log.info("casbin.enforcer_loaded")

    return _enforcer


def reload_policy() -> None:
    """Reload Casbin policies from the database.

    This should be called after policy changes so the cached enforcer does not
    keep stale authorization rules.
    """
    enforcer = get_enforcer()
    enforcer.load_policy()

    log.info("casbin.policy_reloaded")


def verify_policies_loaded() -> None:
    """Verify that the Casbin policy table is not empty.

    The project contract requires the app to refuse startup if the Casbin policy
    table is empty. Empty policies would mean authorization is not configured.

    Raises:
        RuntimeError: If no Casbin policies are loaded.
    """
    enforcer = get_enforcer()
    policies = enforcer.get_policy()

    if not policies:
        raise RuntimeError("Casbin policy table is empty. Refusing to start.")

    log.info("casbin.policy_verified", policy_count=len(policies))