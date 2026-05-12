"""Unit tests for the MinIO BlobStorage adapter.

All MinIO network calls are mocked — no real MinIO instance required.
Tests verify that BlobStorage calls the underlying client with the correct
arguments and handles the response correctly.
"""

import io
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infra.blob import BlobStorage


@pytest.fixture()
def blob() -> BlobStorage:
    """Return a BlobStorage instance with a fresh (un-called) Minio client."""
    return BlobStorage(
        endpoint="minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
    )


# ---------------------------------------------------------------------------
# upload()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_calls_put_object_with_correct_bucket(blob: BlobStorage) -> None:
    """upload() must target the bucket name passed by the caller."""
    # Arrange
    blob._client.put_object = AsyncMock()

    # Act
    await blob.upload("documents", "key.tif", b"data", "image/tiff")

    # Assert
    call_kwargs = blob._client.put_object.call_args.kwargs
    assert call_kwargs["bucket_name"] == "documents"


@pytest.mark.asyncio
async def test_upload_calls_put_object_with_correct_key(blob: BlobStorage) -> None:
    """upload() must use the exact object key provided."""
    # Arrange
    blob._client.put_object = AsyncMock()

    # Act
    await blob.upload("documents", "path/to/scan.tif", b"data", "image/tiff")

    # Assert
    call_kwargs = blob._client.put_object.call_args.kwargs
    assert call_kwargs["object_name"] == "path/to/scan.tif"


@pytest.mark.asyncio
async def test_upload_sends_correct_content_length(blob: BlobStorage) -> None:
    """upload() must report the exact byte length so MinIO stores it correctly."""
    # Arrange
    blob._client.put_object = AsyncMock()
    data = b"hello world"

    # Act
    await blob.upload("documents", "file.tif", data, "image/tiff")

    # Assert
    call_kwargs = blob._client.put_object.call_args.kwargs
    assert call_kwargs["length"] == len(data)


@pytest.mark.asyncio
async def test_upload_wraps_data_in_bytes_io_stream(blob: BlobStorage) -> None:
    """upload() must wrap raw bytes in a BytesIO stream for the MinIO client."""
    # Arrange
    blob._client.put_object = AsyncMock()
    data = b"raw bytes"

    # Act
    await blob.upload("documents", "file.tif", data, "image/tiff")

    # Assert
    call_kwargs = blob._client.put_object.call_args.kwargs
    assert isinstance(call_kwargs["data"], io.BytesIO)


@pytest.mark.asyncio
async def test_upload_sets_content_type(blob: BlobStorage) -> None:
    """upload() must forward the content_type so objects are served correctly."""
    # Arrange
    blob._client.put_object = AsyncMock()

    # Act
    await blob.upload("overlays", "overlay.png", b"png data", "image/png")

    # Assert
    call_kwargs = blob._client.put_object.call_args.kwargs
    assert call_kwargs["content_type"] == "image/png"


# ---------------------------------------------------------------------------
# download()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_returns_response_bytes(blob: BlobStorage) -> None:
    """download() must return the raw bytes read from the MinIO response."""
    # Arrange
    expected_bytes = b"document content"
    mock_response = AsyncMock()
    mock_response.read = AsyncMock(return_value=expected_bytes)
    mock_response.close = MagicMock()
    blob._client.get_object = AsyncMock(return_value=mock_response)

    # Act
    result = await blob.download("documents", "scan.tif")

    # Assert
    assert result == expected_bytes


@pytest.mark.asyncio
async def test_download_closes_response_after_read(blob: BlobStorage) -> None:
    """download() must close the HTTP response to release the connection."""
    # Arrange
    mock_response = AsyncMock()
    mock_response.read = AsyncMock(return_value=b"data")
    mock_response.close = MagicMock()
    blob._client.get_object = AsyncMock(return_value=mock_response)

    # Act
    await blob.download("documents", "scan.tif")

    # Assert
    mock_response.close.assert_called_once()


@pytest.mark.asyncio
async def test_download_calls_get_object_with_correct_bucket_and_key(blob: BlobStorage) -> None:
    """download() must address the exact bucket and key provided."""
    # Arrange
    mock_response = AsyncMock()
    mock_response.read = AsyncMock(return_value=b"data")
    mock_response.close = MagicMock()
    blob._client.get_object = AsyncMock(return_value=mock_response)

    # Act
    await blob.download("documents", "uploads/invoice.tif")

    # Assert
    blob._client.get_object.assert_called_once_with(
        bucket_name="documents", object_name="uploads/invoice.tif"
    )


# ---------------------------------------------------------------------------
# get_presigned_url()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_presigned_url_returns_string(blob: BlobStorage) -> None:
    """get_presigned_url() must return a plain string URL."""
    # Arrange
    blob._client.presigned_get_object = AsyncMock(
        return_value="http://minio:9000/documents/scan.tif?X-Amz-Expires=3600"
    )

    # Act
    url = await blob.get_presigned_url("documents", "scan.tif")

    # Assert
    assert isinstance(url, str)


@pytest.mark.asyncio
async def test_get_presigned_url_passes_timedelta_expiry(blob: BlobStorage) -> None:
    """get_presigned_url() must translate expires_seconds into a timedelta."""
    # Arrange
    blob._client.presigned_get_object = AsyncMock(return_value="http://example.com/url")

    # Act
    await blob.get_presigned_url("documents", "scan.tif", expires_seconds=1800)

    # Assert
    call_kwargs = blob._client.presigned_get_object.call_args.kwargs
    assert call_kwargs["expires"] == timedelta(seconds=1800)


@pytest.mark.asyncio
async def test_get_presigned_url_default_expiry_is_one_hour(blob: BlobStorage) -> None:
    """Default expiry must be 3600 seconds (1 hour) when not specified."""
    # Arrange
    blob._client.presigned_get_object = AsyncMock(return_value="http://example.com/url")

    # Act
    await blob.get_presigned_url("documents", "scan.tif")

    # Assert
    call_kwargs = blob._client.presigned_get_object.call_args.kwargs
    assert call_kwargs["expires"] == timedelta(seconds=3600)
