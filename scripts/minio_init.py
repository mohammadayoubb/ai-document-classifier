"""Create required MinIO buckets.

Run once after `docker compose up minio`:
    python scripts/minio_init.py

Buckets created:
    documents — raw document uploads from SFTP (private)
    overlays  — annotated PNG overlays from the inference worker (public-read)
"""

import asyncio
import json
import os

import structlog
from miniopy_async import Minio  # type: ignore[import-untyped]

log = structlog.get_logger()

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

REQUIRED_BUCKETS = ["documents", "overlays"]

# Allow anonymous GET on overlays so the React frontend can display images directly.
_OVERLAYS_PUBLIC_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": "*"},
        "Action": ["s3:GetObject"],
        "Resource": ["arn:aws:s3:::overlays/*"],
    }],
})


async def init_buckets() -> None:
    """Create the required MinIO buckets if they do not already exist."""
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )

    for bucket in REQUIRED_BUCKETS:
        exists = await client.bucket_exists(bucket)
        if not exists:
            await client.make_bucket(bucket)
            log.info("minio.bucket.created", bucket=bucket)
        else:
            log.info("minio.bucket.exists", bucket=bucket)

    await client.set_bucket_policy("overlays", _OVERLAYS_PUBLIC_POLICY)
    log.info("minio.bucket.policy_set", bucket="overlays", policy="public-read")


if __name__ == "__main__":
    asyncio.run(init_buckets())
