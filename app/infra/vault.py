"""HashiCorp Vault KV v2 adapter for secret resolution at startup."""

from typing import Any

import hvac  # type: ignore[import-untyped]
import structlog

log = structlog.get_logger()


class VaultClient:
    """Thin wrapper around hvac for KV v2 secret resolution.

    Args:
        addr: Vault server URL — e.g. "http://vault:8200".
        token: Root or service token for Vault authentication.
    """

    def __init__(self, addr: str, token: str) -> None:
        self._client: hvac.Client = hvac.Client(url=addr, token=token)

    def get_secret(self, path: str, key: str) -> str:
        """Read a single key from the KV v2 secret engine.

        Args:
            path: Path within the 'secret/' mount — e.g. "app".
            key: Key name within that secret — e.g. "jwt_signing_key".

        Returns:
            The secret value as a plain string.

        Raises:
            RuntimeError: If the path does not exist, the key is absent,
                or the value is not a non-empty string.
        """
        try:
            response: dict[str, Any] = self._client.secrets.kv.v2.read_secret_version(
                path=path,
            )
            data = response["data"]["data"]
        except Exception as exc:
            log.exception("vault.secret_read_failed", path=path, key=key)
            raise RuntimeError(f"Vault secret path '{path}' could not be read") from exc

        if key not in data:
            raise RuntimeError(f"Vault secret '{path}/{key}' not found")

        value = data[key]
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Vault secret '{path}/{key}' is empty or invalid")

        return value

    def is_reachable(self) -> bool:
        """Check whether Vault is reachable and the token is authenticated.

        Returns:
            True if Vault responds and the token is valid; False otherwise.
        """
        try:
            return bool(self._client.is_authenticated())
        except Exception:
            log.exception("vault.unreachable")
            return False