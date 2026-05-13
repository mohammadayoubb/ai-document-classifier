# ruff: noqa: S101, S106
import pytest

from app.config import Settings


class FakeVault:
    def __init__(self, password: str) -> None:
        self.password = password
        self.calls: list[tuple[str, str]] = []

    def get_secret(self, path: str, key: str) -> str:
        self.calls.append((path, key))
        return self.password


def test_database_url_can_be_built_from_vault_postgres_password() -> None:
    settings = Settings(
        vault_root_token="root",
        database_url=None,
        postgres_host="db",
        postgres_db="docclassifier",
        postgres_user="postgres",
        postgres_vault_path="database",
        postgres_vault_key="postgres_password",
        postgres_password="",
    )
    vault = FakeVault("p@ss/word")

    url = settings.build_database_url_from_vault(vault)

    assert vault.calls == [("database", "postgres_password")]
    assert url == "postgresql+asyncpg://postgres:p%40ss%2Fword@db:5432/docclassifier"


def test_missing_postgres_password_without_database_url_raises_clear_error() -> None:
    settings = Settings(
        vault_root_token="root",
        database_url=None,
        postgres_password="",
    )

    with pytest.raises(RuntimeError, match="Postgres password is missing"):
        settings.build_database_url()


def test_database_url_override_is_allowed_for_tests_and_local_fallback() -> None:
    settings = Settings(
        vault_root_token="root",
        database_url="postgresql+asyncpg://user:pw@localhost:5432/test_db",
        postgres_password="",
    )

    assert settings.build_database_url() == settings.database_url
