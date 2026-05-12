"""Unit tests for the SFTP paramiko adapter.

All SSH/SFTP network calls are mocked — no real SFTP server required.
Tests verify that SftpAdapter orchestrates paramiko correctly and handles
the uploads/ directory lifecycle (list, download, move) as documented.
"""

import stat
from unittest.mock import MagicMock, call, patch

import pytest

from app.infra.sftp import SftpAdapter


@pytest.fixture()
def adapter() -> SftpAdapter:
    """Return an SftpAdapter with no active connection."""
    return SftpAdapter(
        host="sftp",
        port=22,
        username="uploader",
        password="password",
    )


@pytest.fixture()
def connected_adapter() -> SftpAdapter:
    """Return an SftpAdapter with mocked SSH and SFTP clients already connected."""
    a = SftpAdapter(host="sftp", port=22, username="uploader", password="password")
    a._ssh = MagicMock()
    a._sftp = MagicMock()
    return a


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


def test_connect_sets_auto_add_policy() -> None:
    """connect() must accept the server host key automatically (internal network)."""
    # Arrange
    with patch("app.infra.sftp.paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = MagicMock()
        adapter = SftpAdapter("sftp", 22, "uploader", "password")

        # Act
        adapter.connect()

        # Assert
        mock_ssh.set_missing_host_key_policy.assert_called_once()
        policy_arg = mock_ssh.set_missing_host_key_policy.call_args[0][0]
        assert isinstance(policy_arg, type(mock_ssh.set_missing_host_key_policy.call_args[0][0]))


def test_connect_opens_sftp_channel() -> None:
    """connect() must open an SFTP channel on top of the SSH connection."""
    # Arrange
    with patch("app.infra.sftp.paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        adapter = SftpAdapter("sftp", 22, "uploader", "password")

        # Act
        adapter.connect()

        # Assert
        mock_ssh.open_sftp.assert_called_once()
        assert adapter._sftp is mock_sftp


def test_connect_passes_correct_credentials() -> None:
    """connect() must forward host, port, username, and password to paramiko."""
    # Arrange
    with patch("app.infra.sftp.paramiko.SSHClient") as mock_ssh_class:
        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.open_sftp.return_value = MagicMock()
        adapter = SftpAdapter("sftp-host", 2222, "scanner", "secret")

        # Act
        adapter.connect()

        # Assert
        mock_ssh.connect.assert_called_once_with(
            hostname="sftp-host",
            port=2222,
            username="scanner",
            password="secret",
            timeout=10,
        )


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


def test_disconnect_closes_sftp_channel(connected_adapter: SftpAdapter) -> None:
    """disconnect() must close the SFTP channel before closing SSH."""
    # Arrange — capture reference before disconnect() nulls it
    mock_ssh = connected_adapter._ssh

    # Act
    connected_adapter.disconnect()

    # Assert
    mock_ssh.close.assert_called_once()  # type: ignore[union-attr]


def test_disconnect_clears_internal_references(connected_adapter: SftpAdapter) -> None:
    """disconnect() must set _ssh and _sftp to None to prevent stale use."""
    # Act
    connected_adapter.disconnect()

    # Assert
    assert connected_adapter._ssh is None
    assert connected_adapter._sftp is None


# ---------------------------------------------------------------------------
# list_uploads()
# ---------------------------------------------------------------------------


def _make_sftp_entry(name: str, is_dir: bool = False) -> MagicMock:
    """Build a mock paramiko SFTPAttributes entry."""
    entry = MagicMock()
    entry.filename = name
    entry.st_mode = stat.S_IFDIR | 0o755 if is_dir else stat.S_IFREG | 0o644
    return entry


def test_list_uploads_returns_regular_file_names(connected_adapter: SftpAdapter) -> None:
    """list_uploads() must return bare filenames of regular files in uploads/."""
    # Arrange
    connected_adapter._sftp.listdir_attr.return_value = [  # type: ignore[union-attr]
        _make_sftp_entry("invoice.tif"),
        _make_sftp_entry("letter.tif"),
    ]

    # Act
    files = connected_adapter.list_uploads()

    # Assert
    assert files == ["invoice.tif", "letter.tif"]


def test_list_uploads_excludes_subdirectories(connected_adapter: SftpAdapter) -> None:
    """list_uploads() must skip processed/ and quarantine/ subdirectories."""
    # Arrange
    connected_adapter._sftp.listdir_attr.return_value = [  # type: ignore[union-attr]
        _make_sftp_entry("scan.tif"),
        _make_sftp_entry("processed", is_dir=True),
        _make_sftp_entry("quarantine", is_dir=True),
    ]

    # Act
    files = connected_adapter.list_uploads()

    # Assert
    assert files == ["scan.tif"]


def test_list_uploads_returns_empty_list_when_directory_missing(
    connected_adapter: SftpAdapter,
) -> None:
    """list_uploads() must return [] if uploads/ does not exist yet."""
    # Arrange
    connected_adapter._sftp.listdir_attr.side_effect = FileNotFoundError  # type: ignore[union-attr]

    # Act
    files = connected_adapter.list_uploads()

    # Assert
    assert files == []


def test_list_uploads_excludes_hidden_files(connected_adapter: SftpAdapter) -> None:
    """list_uploads() must skip dot-files (e.g. .keep, .DS_Store)."""
    # Arrange
    connected_adapter._sftp.listdir_attr.return_value = [  # type: ignore[union-attr]
        _make_sftp_entry(".keep"),
        _make_sftp_entry("real_scan.tif"),
    ]

    # Act
    files = connected_adapter.list_uploads()

    # Assert
    assert files == ["real_scan.tif"]


# ---------------------------------------------------------------------------
# move_to_processed() and move_to_quarantine()
# ---------------------------------------------------------------------------


def test_move_to_processed_renames_file_into_processed_directory(
    connected_adapter: SftpAdapter,
) -> None:
    """move_to_processed() must rename the file from uploads/ to uploads/processed/."""
    # Arrange
    connected_adapter._sftp.mkdir.side_effect = OSError("already exists")  # type: ignore[union-attr]

    # Act
    connected_adapter.move_to_processed("invoice.tif")

    # Assert
    connected_adapter._sftp.rename.assert_called_once_with(  # type: ignore[union-attr]
        "uploads/invoice.tif", "uploads/processed/invoice.tif"
    )


def test_move_to_quarantine_renames_file_into_quarantine_directory(
    connected_adapter: SftpAdapter,
) -> None:
    """move_to_quarantine() must rename the file from uploads/ to uploads/quarantine/."""
    # Arrange
    connected_adapter._sftp.mkdir.side_effect = OSError("already exists")  # type: ignore[union-attr]

    # Act
    connected_adapter.move_to_quarantine("bad_file.tif")

    # Assert
    connected_adapter._sftp.rename.assert_called_once_with(  # type: ignore[union-attr]
        "uploads/bad_file.tif", "uploads/quarantine/bad_file.tif"
    )


def test_move_to_processed_creates_directory_if_absent(
    connected_adapter: SftpAdapter,
) -> None:
    """move_to_processed() must create uploads/processed/ if it doesn't exist yet."""
    # Arrange
    connected_adapter._sftp.mkdir.side_effect = None  # type: ignore[union-attr]  # mkdir succeeds

    # Act
    connected_adapter.move_to_processed("scan.tif")

    # Assert
    connected_adapter._sftp.mkdir.assert_called_once_with("uploads/processed")  # type: ignore[union-attr]


def test_move_to_quarantine_tolerates_existing_directory(
    connected_adapter: SftpAdapter,
) -> None:
    """move_to_quarantine() must not crash if uploads/quarantine/ already exists."""
    # Arrange — mkdir raises OSError (directory already exists)
    connected_adapter._sftp.mkdir.side_effect = OSError("File exists")  # type: ignore[union-attr]

    # Act / Assert — must not raise
    connected_adapter.move_to_quarantine("scan.tif")
