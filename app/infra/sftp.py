"""SFTP polling adapter for the document ingest worker."""

from typing import Any

import structlog

log = structlog.get_logger()


class SftpAdapter:
    """Thin wrapper around paramiko for SFTP file operations.

    Used exclusively by app/workers/ingest.py to poll the uploads directory
    and manage the file lifecycle (move to processed/ or quarantine/).

    Args:
        host: SFTP server hostname — "sftp" inside the Docker network.
        port: SFTP port — 22 inside the Docker network.
        username: SFTP login username.
        password: SFTP login password resolved from Vault at startup.
    """

    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: Any = None  # paramiko.SSHClient, connected lazily

    def connect(self) -> None:
        """Open the SSH/SFTP connection.

        Raises:
            RuntimeError: If the connection cannot be established.
        """
        # TODO: Phase 8
        ...

    def disconnect(self) -> None:
        """Close the SSH/SFTP connection gracefully."""
        # TODO: Phase 8
        ...

    def list_uploads(self) -> list[str]:
        """Return filenames present in the uploads/ directory.

        Returns:
            A list of bare filenames (not full paths) in uploads/.
        """
        # TODO: Phase 8
        return []

    def download_file(self, filename: str) -> bytes:
        """Download a file from uploads/ and return its raw bytes.

        Args:
            filename: Filename relative to the uploads/ directory.

        Returns:
            Raw file bytes.
        """
        # TODO: Phase 8
        ...  # type: ignore[return-value]

    def move_to_processed(self, filename: str) -> None:
        """Move a successfully ingested file from uploads/ to processed/.

        Args:
            filename: Filename to move.
        """
        # TODO: Phase 8
        ...

    def move_to_quarantine(self, filename: str) -> None:
        """Move a malformed file from uploads/ to quarantine/.

        Args:
            filename: Filename to quarantine.
        """
        # TODO: Phase 8
        ...
