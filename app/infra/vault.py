"""HashiCorp Vault KV v2 adapter for secret resolution at startup."""

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
            RuntimeError: If the path does not exist or the key is absent.
        """
        response = self._client.secrets.kv.v2.read_secret_version(path=path)
        data: dict[str, str] = response["data"]["data"]
        if key not in data:
            raise RuntimeError(f"Vault secret '{path}/{key}' not found")
        return data[key]

    def is_reachable(self) -> bool:
        """Check whether Vault is reachable and the token is authenticated.

        Returns:
            True if Vault responds and the token is valid; False otherwise.
        """
        try:
            return bool(self._client.is_authenticated())
        except Exception:
            return False
