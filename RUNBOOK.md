# Operations Runbook

> Complete in Phase 12 with step-by-step operational procedures.

## Sections to document

- `docker compose up` from a clean clone
- How to run the golden test manually
- How to seed Vault secrets (`python scripts/vault_seed.py`)
- How to create MinIO buckets (`python scripts/minio_init.py`)
- How to add a new user and assign their role
- How to drop a test TIFF via SCP: `scp -P 2222 file.tif uploader@localhost:uploads/`
- How to check logs: `docker compose logs -f api`
- How to restart just the worker: `docker compose restart worker`
- How to swap model weights (stop workers → replace `.pt` → update SHA-256 → restart)
