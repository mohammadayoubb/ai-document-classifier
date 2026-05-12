"""Seed initial Casbin RBAC policies.

This script loads the Casbin model and writes the required policies into the
database-backed Casbin adapter.

Run after the database migrations have created the casbin_rule table:

    python scripts/casbin_seed.py

The API refuses to start if the Casbin policy table is empty, so this script
must run before starting the API in a fresh local environment.
"""

import os
from pathlib import Path

import casbin
from casbin_sqlalchemy_adapter import Adapter  # type: ignore[import-untyped]

CASBIN_MODEL_PATH = Path("app/infra/casbin_model.conf")


def get_sync_database_url(database_url: str) -> str:
    """Convert the async database URL into a sync URL for Casbin.

    The application uses async SQLAlchemy with postgresql+asyncpg.
    Casbin's SQLAlchemy adapter is synchronous, so we remove the async driver.
    """
    return database_url.replace("postgresql+asyncpg://", "postgresql://")


def main() -> None:
    """Seed the required role policies into Casbin."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/docclassifier",
    )

    adapter = Adapter(get_sync_database_url(database_url))
    enforcer = casbin.Enforcer(str(CASBIN_MODEL_PATH), adapter)

    # Load existing policies so the script can be run multiple times safely.
    enforcer.load_policy()

    policies = [
        # Admin permissions.
        ("admin", "/users", "POST"),
        ("admin", "/users/role", "PUT"),
        ("admin", "/audit", "GET"),

        # Reviewer permissions.
        ("reviewer", "/batches", "GET"),
        ("reviewer", "/batches/detail", "GET"),
        ("reviewer", "/predictions/relabel", "PATCH"),

        # Auditor permissions.
        ("auditor", "/batches", "GET"),
        ("auditor", "/batches/detail", "GET"),
        ("auditor", "/audit", "GET"),
    ]

    for subject, object_path, action in policies:
        # add_policy returns False if the policy already exists.
        # That makes this seed script idempotent.
        enforcer.add_policy(subject, object_path, action)

    enforcer.save_policy()

    print("Casbin policies seeded")


if __name__ == "__main__":
    main()