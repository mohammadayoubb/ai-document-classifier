"""Seed Vault KV v2 with application secrets.

Run once after `docker compose up vault`:
    python scripts/vault_seed.py

Secrets written to secret/data/app:
    jwt_signing_key   — fastapi-users JWT signing
    postgres_password — database connection
    minio_secret_key  — MinIO blob storage
    sftp_password     — SFTP ingest worker
"""

import os
import secrets

import hvac  # type: ignore[import-untyped]

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.environ.get("VAULT_ROOT_TOKEN", "root")


def seed_vault() -> None:
    """Enable KV v2 and write randomly generated secrets to secret/data/app.

    Re-running overwrites all secrets with new random values.
    """
    client: hvac.Client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)

    try:
        client.sys.enable_secrets_engine(
            backend_type="kv",
            path="secret",
            options={"version": "2"},
        )
        print("KV v2 engine enabled at secret/")
    except Exception:
        print("KV v2 already enabled at secret/ (skipping)")

    secret_data = {
        "jwt_signing_key": secrets.token_hex(32),
        "postgres_password": secrets.token_urlsafe(24),
        "minio_secret_key": secrets.token_urlsafe(24),
        "sftp_password": secrets.token_urlsafe(16),
    }

    client.secrets.kv.v2.create_or_update_secret(path="app", secret=secret_data)
    print("Secrets written to secret/data/app")
    print("Keys seeded:", list(secret_data.keys()))


if __name__ == "__main__":
    seed_vault()
