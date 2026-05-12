"""Seed Vault KV v2 with application secrets.

Run once after Vault is running:

    python scripts/vault_seed.py

Secrets written to secret/data/app:
    jwt_signing_key   — fastapi-users JWT signing
    postgres_password — database connection secret
    minio_secret_key  — MinIO blob storage secret
    sftp_password     — SFTP ingest worker secret

This script is for local development. The application reads these secrets
from Vault during startup and refuses to start if Vault is unreachable.
"""

import os
import secrets

import hvac  # type: ignore[import-untyped]

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.environ.get("VAULT_ROOT_TOKEN", "root")


def seed_vault() -> None:
    """Enable KV v2 and write generated local-development secrets.

    Re-running this script rotates all generated secrets. That is acceptable
    during local development, but the stack should be restarted afterward so
    services read the new values from Vault.
    """
    client: hvac.Client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)

    # Fail early if Vault is unreachable or the token is invalid.
    # This mirrors the API startup rule from CLAUDE.md.
    if not client.is_authenticated():
        raise RuntimeError("Vault authentication failed. Check VAULT_ADDR and VAULT_ROOT_TOKEN.")

    try:
        # Vault dev mode may already mount KV at secret/.
        # If it does not exist, we create it as KV v2.
        client.sys.enable_secrets_engine(
            backend_type="kv",
            path="secret",
            options={"version": "2"},
        )
        print("KV v2 engine enabled at secret/")
    except hvac.exceptions.InvalidRequest:
        # This usually means the secret/ engine is already enabled.
        # We skip instead of failing so the script remains idempotent.
        print("KV v2 already enabled at secret/ (skipping)")

    secret_data = {
        # JWT signing key must never be hardcoded in source code.
        "jwt_signing_key": secrets.token_hex(32),

        # These are stored in Vault so .env can stay limited to Vault token + ports.
        "postgres_password": secrets.token_urlsafe(24),
        "minio_secret_key": secrets.token_urlsafe(24),
        "sftp_password": secrets.token_urlsafe(16),
    }

    client.secrets.kv.v2.create_or_update_secret(
        path="app",
        secret=secret_data,
    )

    print("Secrets written to secret/data/app")
    print("Keys seeded:", list(secret_data.keys()))


if __name__ == "__main__":
    seed_vault()