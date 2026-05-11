# Architecture

> Complete in Phase 12 with ASCII container diagram, layer diagram, and
> descriptions of where secrets, cache, and queue live.

## Container Overview (9 services)

| Service | Image / Build | Purpose |
|---------|--------------|---------|
| `api` | our build | FastAPI app — auth, RBAC, batch/prediction endpoints |
| `worker` | our build | RQ inference worker |
| `sftp-ingest` | our build | SFTP poller — enqueues inference jobs |
| `migrate` | our build | Alembic migrations (runs and exits) |
| `db` | postgres:16 | Application database |
| `redis` | redis:7-alpine | Queue (RQ) + cache (fastapi-cache2) |
| `minio` | minio/minio | S3-compatible blob storage |
| `sftp` | atmoz/sftp | SFTP server for scanner vendor drops |
| `vault` | hashicorp/vault:1.16 | Secret store (KV v2 dev mode) |

## Layer Diagram

```
HTTP Request
    ↓
app/api/routes/       ← HTTP ONLY: Depends() wiring, one service call, return domain model
    ↓
app/services/         ← Business logic, transaction boundaries, cache invalidation, audit log
    ↓
app/repositories/     ← SQL ONLY: no HTTP errors, no cache ops, no business logic
    ↓
app/db/models.py      ← SQLAlchemy ORM models (imported ONLY by repositories)
    ↓
PostgreSQL

app/domain/           ← Pydantic domain models (service return types + API response shapes)
app/infra/            ← blob.py | cache.py | queue.py | sftp.py | vault.py
app/config.py         ← pydantic-settings Settings class (single source of truth)
app/main.py           ← FastAPI app + lifespan ONLY
```

## Secrets — where they live

- `VAULT_ROOT_TOKEN` — `.env` only (dev mode token)
- `jwt_signing_key`, `postgres_password`, `minio_secret_key`, `sftp_password` — Vault KV v2 at `secret/data/app`

## Cache — where it lives

Redis (fastapi-cache2). Invalidation happens ONLY in `app/services/`.

## Queue — where it lives

Redis (RQ). Jobs are enqueued by the ingest worker and consumed by the inference worker.
