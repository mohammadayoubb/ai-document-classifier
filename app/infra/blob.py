"""MinIO S3-compatible blob storage adapter.

All MinIO access in the application goes through this class.
"""

import io
from datetime import timedelta

import structlog
from miniopy_async import Minio  # type: ignore[import-untyped]

log = structlog.get_logger()


class BlobStorage:
    """Async MinIO adapter — upload, download, and pre-signed URL generation.

    Args:
        endpoint: MinIO host:port — e.g. "minio:9000".
        access_key: MinIO access key (root user in dev).
        secret_key: MinIO secret key resolved from Vault at startup.
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str) -> None:
        self._client: Minio = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """Upload bytes to a MinIO bucket.

        Args:
            bucket: Target bucket name — "documents" or "overlays".
            key: Object key (path within the bucket).
            data: Raw bytes to store.
            content_type: MIME type — e.g. "image/tiff" or "image/png".
        """
        stream = io.BytesIO(data)
        await self._client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=stream,
            length=len(data),
            content_type=content_type,
        )
        log.info("blob.upload.ok", bucket=bucket, key=key, size_bytes=len(data))

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object from MinIO and return its raw bytes.

        Args:
            bucket: Source bucket name.
            key: Object key to retrieve.

        Returns:
            The raw object bytes.

        Raises:
            Exception: If the object does not exist or MinIO is unreachable.
        """
        response = await self._client.get_object(bucket_name=bucket, object_name=key)
        try:
            data: bytes = await response.read()
        finally:
            response.close()
        log.info("blob.download.ok", bucket=bucket, key=key, size_bytes=len(data))
        return data

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_seconds: int = 3600,
    ) -> str:
        """Generate a pre-signed GET URL for temporary object access.

        Args:
            bucket: Bucket name.
            key: Object key.
            expires_seconds: How long the URL stays valid (default 1 hour).

        Returns:
            A time-limited URL string for direct object download.
        """
        url: str = await self._client.presigned_get_object(
            bucket_name=bucket,
            object_name=key,
            expires=timedelta(seconds=expires_seconds),
        )
        return url
