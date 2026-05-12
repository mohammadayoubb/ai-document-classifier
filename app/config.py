"""Application configuration — single source of truth for all env-driven settings.

All environment variables are declared here as typed fields.
os.getenv() is forbidden everywhere else in the codebase.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and the .env file.

    Secrets (jwt_signing_key, minio_secret_key, sftp_password) are resolved
    from Vault at startup in app/main.py lifespan and injected here after the
    fact.  They start as empty strings so Settings() can be constructed before
    Vault is reachable; lifespan refuses to proceed if Vault is unreachable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Resolved at runtime from Vault — empty default, overridden in lifespan
    jwt_signing_key: str = ""

    # Infrastructure URLs injected by docker-compose environment section
    database_url: str = Field(..., min_length=1)
    redis_url: str = "redis://localhost:6379"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""  # resolved from Vault
    vault_addr: str = "http://localhost:8200"
    # Accepts VAULT_TOKEN (injected by docker-compose) or VAULT_ROOT_TOKEN (set in .env directly)
    vault_token: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("vault_token", "vault_root_token"),
    )

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

    # Docker Compose port vars — present in .env for compose, not used at runtime
    api_port: int = 8000
    minio_port: int = 9000
    minio_console_port: int = 9001
    vault_port: int = 8200

    # Redis cache TTLs (seconds)
    cache_ttl_me: int = 300
    cache_ttl_batches: int = 60
    cache_ttl_batch: int = 30
    cache_ttl_recent: int = 15


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Returns:
        The application settings instance.
    """
    return Settings()
