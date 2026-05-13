"""Shared pytest configuration.

Unit tests should not depend on a real .env file or Docker services.
These environment variables allow modules that import Settings to load safely
during test collection.

The values are test-only placeholders. They do not connect to real services
unless a specific integration test starts those services.
"""

import os

# Settings requires DATABASE_URL because the real app must fail fast if DB config
# is missing. For unit tests, we provide a safe placeholder.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/docclassifier_test",
)

# Settings requires VAULT_TOKEN because the real app resolves secrets from Vault.
# Unit tests do not contact Vault unless they explicitly test Vault integration.
os.environ.setdefault("VAULT_TOKEN", "test-token")

# Some scripts/configs may read the dev-mode root token name.
os.environ.setdefault("VAULT_ROOT_TOKEN", "test-token")

# Use localhost in tests unless an integration test overrides it.
os.environ.setdefault("VAULT_ADDR", "http://localhost:8200")
