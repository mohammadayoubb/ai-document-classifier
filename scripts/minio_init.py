"""Create required MinIO buckets.

Run once after `docker compose up minio`:
    python scripts/minio_init.py

Buckets created:
    documents — raw document uploads from SFTP
    overlays  — annotated PNG overlays from the inference worker
"""

import os

import structlog
from minio import Minio  # type: ignore[import-untyped]

log = structlog.get_logger()

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

REQUIRED_BUCKETS = ["documents", "overlays"]


def init_buckets() -> None:
    """Create the required MinIO buckets if they do not already exist."""
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )

    for bucket in REQUIRED_BUCKETS:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            log.info("minio.bucket.created", bucket=bucket)
        else:
            log.info("minio.bucket.exists", bucket=bucket)


if __name__ == "__main__":
    init_buckets()
