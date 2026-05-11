"""External system adapters — one file per external system.

Each adapter exposes a clean class with typed methods.
No HTTP framework imports (FastAPI / Starlette) in this layer.

Adapters:
    blob.py   → MinIO S3-compatible blob storage
    cache.py  → Redis / fastapi-cache2 invalidation helpers
    queue.py  → RQ (Redis Queue) job enqueueing
    sftp.py   → SFTP file watcher (paramiko)
    vault.py  → HashiCorp Vault KV v2 secret resolution
"""
