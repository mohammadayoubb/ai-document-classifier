"""SFTP polling adapter for the document ingest worker."""

import io
import stat

import paramiko
import structlog

log = structlog.get_logger()


class SftpAdapter:
    """Thin wrapper around paramiko for SFTP file operations.

    Used exclusively by app/workers/ingest.py to poll the uploads directory
    and manage the file lifecycle (move to processed/ or quarantine/).

    All methods are synchronous — call them from asyncio.to_thread() in the
    async ingest worker to avoid blocking the event loop.

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
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def connect(self) -> None:
        """Open the SSH/SFTP connection.

        Uses AutoAddPolicy to trust the server key automatically — acceptable
        for an internal dev/staging environment.

        Raises:
            RuntimeError: If the connection cannot be established.
        """
        ssh = paramiko.SSHClient()
        # AutoAddPolicy is intentional for the internal Docker network
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            timeout=10,
        )
        self._ssh = ssh
        self._sftp = ssh.open_sftp()
        log.info("sftp.connected", host=self._host, port=self._port)

    def disconnect(self) -> None:
        """Close the SSH/SFTP connection gracefully."""
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None
        log.info("sftp.disconnected")

    def list_uploads(self) -> list[str]:
        """Return filenames present in the uploads/ directory.

        Filters out subdirectories (processed/, quarantine/) so the poller
        only sees raw uploaded files.

        Returns:
            A list of bare filenames (not full paths) in uploads/.
        """
        if self._sftp is None:
            raise RuntimeError("SFTP not connected — call connect() first")
        try:
            entries = self._sftp.listdir_attr("uploads")
        except FileNotFoundError:
            return []
        # Exclude subdirectories (processed/, quarantine/) and hidden files
        return [
            e.filename
            for e in entries
            if e.filename and not e.filename.startswith(".")
            and not stat.S_ISDIR(e.st_mode or 0)
        ]

    def download_file(self, filename: str) -> bytes:
        """Download a file from uploads/ and return its raw bytes.

        Args:
            filename: Filename relative to the uploads/ directory.

        Returns:
            Raw file bytes.

        Raises:
            RuntimeError: If not connected.
            FileNotFoundError: If the file no longer exists (already moved).
        """
        if self._sftp is None:
            raise RuntimeError("SFTP not connected — call connect() first")
        buf = io.BytesIO()
        self._sftp.getfo(f"uploads/{filename}", buf)
        return buf.getvalue()

    def move_to_processed(self, filename: str) -> None:
        """Move a successfully ingested file from uploads/ to processed/.

        Creates the processed/ directory if it does not exist.

        Args:
            filename: Filename to move.
        """
        if self._sftp is None:
            raise RuntimeError("SFTP not connected — call connect() first")
        self._ensure_dir("uploads/processed")
        self._sftp.rename(f"uploads/{filename}", f"uploads/processed/{filename}")
        log.info("sftp.file.processed", filename=filename)

    def move_to_quarantine(self, filename: str) -> None:
        """Move a malformed file from uploads/ to quarantine/.

        Creates the quarantine/ directory if it does not exist.

        Args:
            filename: Filename to quarantine.
        """
        if self._sftp is None:
            raise RuntimeError("SFTP not connected — call connect() first")
        self._ensure_dir("uploads/quarantine")
        self._sftp.rename(f"uploads/{filename}", f"uploads/quarantine/{filename}")
        log.warning("sftp.file.quarantined", filename=filename)

    def _ensure_dir(self, path: str) -> None:
        """Create a directory on the SFTP server, ignoring if it already exists."""
        assert self._sftp is not None
        try:
            self._sftp.mkdir(path)
        except OSError:
            pass  # directory already exists
