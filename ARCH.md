# Architecture

End-to-end overview of the document classifier service: containers, data
flows, layer boundaries, and where secrets, cache, and queue live.

---

## Container Diagram (9 services)

```
                        +------------------+
  Scanner vendor        |                  |
  drops TIFF  --------> |   sftp           |  atmoz/sftp
                        |   port 2222      |
                        +--------+---------+
                                 |  SFTP poll (paramiko, every 1s)
                                 v
                        +------------------+
                        |  sftp-ingest     |  our build
                        |  (ingest worker) |
                        +---+----------+---+
                            |          |
              upload bytes  |          |  enqueue job
                            v          v
                   +----------+    +----------+
                   |  minio   |    |  redis   |  redis:7-alpine
                   |  :9000   |    |  :6379   |
                   +----------+    +----+-----+
                        ^               |  RQ dequeue
                        |               v
                        |      +------------------+
                        |      |  worker          |  our build
                        |      |  (RQ inference)  |
                        |      +--------+---------+
                        |               |
                overlay |               |  write prediction
                upload  |               v
                        |      +------------------+
                        +----> |  db              |  postgres:16
                               |  :5432           |
                               +--------+---------+
                                        |  SQL
                                        v
                               +------------------+
                               |  api             |  our build
                               |  :8000           |
                               +--------+---------+
                                        |
                               +--------+---------+
                               |  vault           |  hashicorp/vault
                               |  :8200           |  (secrets at startup)
                               +------------------+

  migrate  -- runs alembic upgrade head, then exits (not shown above)
```

---

## Data Flow — SFTP drop to API response

```
1.  Scanner drops file.tif onto atmoz/sftp (port 2222)

2.  sftp-ingest polls uploads/ every 1 second via paramiko
      - validates: not empty, valid image, <= 50 MB
      - on bad file  -> move to uploads/quarantine/, log, continue
      - on good file -> continue

3.  sftp-ingest uploads raw bytes to MinIO bucket 'documents'
      key: "documents/file.tif"

4.  sftp-ingest creates a Batch row in PostgreSQL
      status: pending, owner_id: 1 (system user)

5.  sftp-ingest enqueues RQ job in Redis
      function: app.workers.inference.run_inference_job
      args: batch_id, filename, storage_key, request_id

6.  sftp-ingest moves file to uploads/processed/ on SFTP server

7.  RQ worker dequeues the job, runs run_inference_job()
      - downloads file.tif from MinIO
      - runs ConvNeXt classify_image() -> label, confidence, top5
      - generates overlay PNG (label banner + confidence bar)
      - uploads overlay to MinIO bucket 'overlays'
      - creates Prediction row in PostgreSQL (label, confidence, overlay_key)
      - updates Batch status -> completed
      - invalidates Redis cache keys for batches + predictions

8.  API returns the result on GET /batches/{id}
      - reads from PostgreSQL (or Redis cache if warm)
      - returns BatchDomain + PredictionDomain to authenticated user
```

---

## Application Layer Diagram

```
HTTP Request
    |
    v
app/api/routes/          HTTP ONLY
    - Depends() wiring
    - one service call
    - return domain model
    - raise HTTPException (only place allowed)
    |
    v
app/services/            BUSINESS LOGIC
    - transaction boundaries (commit / rollback)
    - cache invalidation  <----+
    - audit log calls           |  only services
    - call repositories         |  touch cache
    - call infra adapters       |
    |
    v
app/repositories/        SQL ONLY
    - ORM queries
    - no HTTP errors
    - no cache ops
    - no business logic
    |
    v
app/db/models.py         ORM MODELS
    - imported ONLY by repositories
    |
    v
PostgreSQL


Parallel layers (not in the HTTP path):
    app/domain/     Pydantic domain models — service return types + API shapes
    app/infra/      blob.py | cache.py | queue.py | sftp.py | vault.py
    app/config.py   pydantic-settings Settings — single source of truth
    app/main.py     FastAPI app + lifespan only
```

---

## Worker Pipeline (outside the HTTP path)

```
app/workers/ingest.py    async loop, asyncio.to_thread() for paramiko
    |
    +-- app/infra/sftp.py      paramiko adapter (sync)
    +-- app/infra/blob.py      miniopy-async adapter (async)
    +-- app/infra/queue.py     RQ adapter (sync, thin wrapper)
    +-- app/repositories/      SQLAlchemy async repos
    +-- app/infra/vault.py     hvac adapter (sync, startup only)

app/workers/inference.py  sync RQ entry point, asyncio.run() bridge
    |
    +-- app/infra/blob.py      download source, upload overlay
    +-- app/classifier/        ConvNeXt model (CPU inference)
    +-- app/repositories/      create Prediction, update Batch
    +-- app/services/          cache invalidation only
```

---

## Service Map — 9 Containers

| Service | Image | Ports | Volumes | Purpose |
|---------|-------|-------|---------|---------|
| `api` | our build (uvicorn) | 8000 | logs/ | FastAPI REST API |
| `worker` | our build (rq worker) | — | logs/ | RQ inference jobs |
| `sftp-ingest` | our build (python) | — | logs/ | SFTP polling loop |
| `migrate` | our build (alembic) | — | — | Schema migrations, exits |
| `db` | postgres:16 | 5432 (internal) | postgres_data | Application database |
| `redis` | redis:7-alpine | 6379 | — | Job queue + API cache |
| `minio` | minio/minio | 9000, 9001 | minio_data | Object storage |
| `sftp` | atmoz/sftp | 2222 | sftp_uploads | SFTP drop zone |
| `vault` | hashicorp/vault:1.16 | 8200 | — | Secret store (dev mode) |

---

## Networks vs Volumes

**Networks** (`app-net`) — let containers reach each other by name.
- `api` calls `db:5432`, `redis:6379`, `minio:9000`, `vault:8200`
- `sftp-ingest` calls `sftp:22`, `minio:9000`, `redis:6379`, `vault:8200`
- `worker` calls `db:5432`, `minio:9000`, `redis:6379`, `vault:8200`
- No container needs a public IP — they talk by service name inside `app-net`

**Volumes** — persist data across container restarts.
- `postgres_data` — all batch, prediction, user, audit rows
- `minio_data` — all uploaded TIFFs and generated overlay PNGs
- `sftp_uploads` — files currently in the SFTP drop zone

---

## Secrets — where they live

```
.env file (git-ignored)
    VAULT_ROOT_TOKEN=root        <- only secret in .env, dev mode token

Vault KV v2 at secret/data/app
    jwt_signing_key              <- resolved by api at startup (lifespan)
    postgres_password            <- resolved by api at startup
    minio_secret_key             <- resolved by sftp-ingest + worker at startup
    sftp_password                <- resolved by sftp-ingest at startup
```

The `api`, `worker`, and `sftp-ingest` containers **refuse to start** if
Vault is unreachable or if any required key is missing.

`grep -ri 'password' app/` returns zero matches outside `app/infra/vault.py`.

---

## Cache — where it lives

Redis, managed by `fastapi-cache2`. Keys are namespaced by endpoint.

| Key | TTL | Invalidated when |
|-----|-----|-----------------|
| `user:{id}` | 300s | Role is changed |
| `batches` | 60s | Any batch is created or updated |
| `batch:{id}` | 30s | Batch status changes |
| `predictions:recent` | 15s | New prediction is created |

**Rule:** only `app/services/` calls cache invalidation. Routes and
repositories never touch the cache directly.

---

## Queue — where it lives

Redis, managed by RQ. One queue named `default`.

```
sftp-ingest  -->  Redis (enqueue)  -->  worker (dequeue + run)
```

Job function: `app.workers.inference.run_inference_job`
Job timeout: 30 seconds (kills stalled jobs automatically)
Job args: `batch_id`, `filename`, `storage_key`, `request_id`

The `request_id` propagates from the ingest log through to the inference
worker log — every log line for a given file shares the same `request_id`.
