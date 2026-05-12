"""Application configuration — single source of truth for all env-driven settings.

All environment variables are declared here as typed fields.
os.getenv() is forbidden everywhere else in the codebase.
"""

from functools import lru_cache
from typing import Protocol
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretReader(Protocol):
    """Minimal contract expected from the teammate-owned Vault adapter."""

    def get_secret(self, path: str, key: str) -> str:
        """Return one secret value from a Vault path/key pair."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables and the .env file.

    Secrets (jwt_signing_key, minio_secret_key, sftp_password, postgres_password)
    are resolved from Vault at startup in app/main.py lifespan and injected here
    after the fact. They start as empty strings so Settings() can be constructed
    before Vault is reachable; lifespan refuses to proceed if Vault is unreachable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Resolved at runtime from Vault — empty default, overridden in lifespan
    jwt_signing_key: str = ""

    # Database connection. DATABASE_URL is intentionally a local/test override;
    # production composes the URL after Vault has resolved postgres_password.
    database_url: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "docclassifier"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_vault_path: str = "app"
    postgres_vault_key: str = "postgres_password"

    # Infrastructure URLs injected by docker-compose environment section
    redis_url: str = "redis://localhost:6379"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""  # resolved from Vault
    vault_addr: str = "http://localhost:8200"
    vault_token: str = Field(..., min_length=1)

    # SFTP
    sftp_host: str = "localhost"
    sftp_port: int = 2222
    sftp_user: str = "uploader"
    sftp_password: str = ""  # resolved from Vault
    sftp_poll_interval_seconds: int = 1

    # Classifier
    model_weights_path: str = "app/classifier/models/classifier.pt"
    model_card_path: str = "app/classifier/models/model_card.json"
    min_test_top1: float = 0.90

    # Application behaviour
    classifier_labels: list[str] = [
        "letter",
        "form",
        "email",
        "handwritten",
        "advertisement",
        "scientific_report",
        "scientific_publication",
        "specification",
        "file_folder",
        "news_article",
        "budget",
        "invoice",
        "presentation",
        "questionnaire",
        "resume",
        "memo",
    ]
    low_confidence_threshold: float = 0.7

    # Redis cache TTLs (seconds)
    cache_ttl_me: int = 300
    cache_ttl_batches: int = 60
    cache_ttl_batch: int = 30
    cache_ttl_recent: int = 15

    def resolve_postgres_password(self, vault_client: SecretReader) -> str:
        """Fetch and store the Postgres password from the configured Vault path."""
        password = vault_client.get_secret(
            self.postgres_vault_path,
            self.postgres_vault_key,
        )
        if not password:
            raise RuntimeError(
                "Vault did not return a postgres_password; cannot build database URL."
            )
        self.postgres_password = password
        return password

    def build_database_url(self) -> str:
        """Build the async SQLAlchemy URL after secrets have been resolved."""
        if self.database_url:
            return self.database_url

        if not self.postgres_password:
            raise RuntimeError(
                "Postgres password is missing. Set DATABASE_URL for tests/local "
                "fallback, or resolve postgres_password from Vault before startup."
            )

        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        database = quote_plus(self.postgres_db)
        return (
            f"postgresql+asyncpg://{user}:{password}@"
            f"{self.postgres_host}:{self.postgres_port}/{database}"
        )

    def build_database_url_from_vault(self, vault_client: SecretReader) -> str:
        """Resolve the Vault secret if needed, then return the async DB URL."""
        if not self.database_url and not self.postgres_password:
            self.resolve_postgres_password(vault_client)
        return self.build_database_url()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Returns:
        The application settings instance.
    """
    return Settings()
