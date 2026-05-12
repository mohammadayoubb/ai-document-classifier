"""Shared pytest configuration and fixtures.

Environment variables are set at module level (before any app import)
because app.db.session calls get_settings() on import, and Settings
requires DATABASE_URL and VAULT_TOKEN to be present.
"""

import os

# Must happen before any `from app...` import in any test module.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/docclassifier",
)
os.environ.setdefault("VAULT_TOKEN", "root")
