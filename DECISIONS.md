# Architectural Decisions

Every decision that is not obvious from reading the code is recorded here.
Format: Context → Options considered → Decision → Consequences.

---

## 2026-05-01 — RQ over Celery for the inference job queue

**Context:**
The inference worker is CPU-bound (ConvNeXt model). We needed a job queue
that could run inference jobs in a separate process so the SFTP ingest loop
and the API are never blocked by model inference.

**Options considered:**
- **Celery** — the most popular Python task queue. Supports many brokers,
  has a full result backend, complex routing, and periodic tasks.
- **RQ (Redis Queue)** — lightweight queue that uses Redis as the broker.
  Job functions are plain Python functions. No extra config files.

**Decision:** RQ.

**Consequences:**
- Redis was already in the stack for caching (fastapi-cache2). RQ reuses
  the same Redis instance — no new service required.
- RQ job functions are plain synchronous Python functions. Easy to read,
  easy to test, no Celery-specific decorators to explain.
- RQ has fewer features than Celery (no complex routing, no periodic tasks).
  We do not need those features — one queue, one job type, one worker.
- If Redis restarts, in-flight jobs are lost. This is acceptable for our
  use case and is documented in the disaster recovery section below.

---

## 2026-05-01 — atmoz/sftp as the SFTP server

**Context:**
The scanner vendor drops TIFF files via SFTP. We needed an SFTP server
that runs inside Docker Compose so the entire stack starts with one command.

**Options considered:**
- **test.rebex.net** — a public demo SFTP server. Free but public, requires
  internet, shared credentials, not suitable for production or CI.
- **atmoz/sftp** — an open-source Docker image that runs a real OpenSSH
  SFTP server. Configured entirely via Docker Compose.
- **OpenSSH directly** — install and configure OpenSSH in a custom image.

**Decision:** atmoz/sftp.

**Consequences:**
- The SFTP server starts automatically with `docker compose up` — no manual
  setup, works offline, works in CI.
- All credentials are defined in `docker-compose.yml` — visible to the team,
  no hidden state.
- The named Docker volume `sftp_uploads` persists files across container
  restarts, matching real-world SFTP server behaviour.

---

## 2026-05-01 — asyncio.to_thread() for paramiko SFTP calls

**Context:**
The ingest worker is async (uses `asyncio`). Paramiko (the SFTP library)
is entirely synchronous — it opens real TCP connections and blocks until
each call completes.

**Options considered:**
- **Call paramiko directly** — would block the event loop, freezing all
  async tasks during every SFTP operation.
- **asyncsh / asyncssh** — async-native SFTP libraries. Would require
  replacing paramiko entirely.
- **asyncio.to_thread()** — runs the synchronous paramiko call in a thread
  pool managed by asyncio. The event loop stays free.

**Decision:** `asyncio.to_thread()` wrapping paramiko.

**Consequences:**
- Paramiko remains as the SFTP library — stable, well-documented, battle-tested.
- The event loop is never blocked during SFTP I/O.
- Each SFTP call (list, download, rename) is individually wrapped, which
  makes the threading boundary explicit and easy to follow.

---

## 2026-05-01 — Ingest worker creates Batch only; inference worker creates Prediction

**Context:**
When a file is received via SFTP, we need database rows to track its
progress. The question was: should the ingest worker create both the Batch
and Prediction rows, or just the Batch?

**Options considered:**
- **Ingest creates both Batch and Prediction (with placeholder values)** —
  requires an `update_result()` method on the prediction repo to fill in
  real values later. Two writes to the same row.
- **Ingest creates Batch only; inference creates Prediction with real values** —
  the Prediction row is created once with correct label, confidence, and top5.
  No placeholder values, no update needed.

**Decision:** Ingest creates Batch only; inference creates the complete Prediction.

**Consequences:**
- The Prediction row always contains real classification results from the
  moment it is created — no invalid intermediate state.
- The inference worker needs no `update_result()` repo method — it calls
  `create()` once with all fields populated.
- There is a window where a Batch exists but has no Prediction (while the
  job is queued). The API handles this by checking `batch.status`.

---

## 2026-05-01 — Quarantine on file validation failure; retry on infrastructure failure

**Context:**
Two different categories of failure can occur during ingest:
1. The file itself is bad (empty, not an image, over 50 MB).
2. Our infrastructure is temporarily unavailable (MinIO down, Redis down).

**Options considered:**
- **Delete bad files** — loses the evidence. An operator cannot inspect what
  the vendor uploaded.
- **Quarantine bad files** — moves them to `uploads/quarantine/` on the SFTP
  server. An operator can inspect and decide what to do.
- **Retry infrastructure failures** — the file is valid; it is not the file's
  fault that our MinIO is temporarily overloaded. Quarantining it would be wrong.

**Decision:** Quarantine on file validation failure. Retry (3×, exponential backoff)
on infrastructure failure. Never quarantine a valid file due to our own infrastructure
being temporarily unavailable.

**Consequences:**
- Operators can inspect `uploads/quarantine/` to understand what the vendor
  sent and why it was rejected.
- Transient MinIO or Redis outages do not result in lost or misclassified files.
- A file that fails all 3 retries is logged as an error but stays in `uploads/`
  so the next poll cycle retries it automatically.

---

## 2026-05-01 — SYSTEM_USER_ID = 1 for SFTP-originated batches

**Context:**
The `batches` table requires an `owner_id` foreign key to `users`. SFTP file
drops have no authenticated user — there is no HTTP request, no JWT token.

**Options considered:**
- **Make `owner_id` nullable** — would require schema changes and special
  handling in the API layer everywhere `owner_id` is used.
- **Use a dedicated system user** — create a non-human user in the database
  at setup time and use its ID for automated ingestion.

**Decision:** `SYSTEM_USER_ID = 1` — the first registered user (the admin).

**Consequences:**
- No schema changes required.
- The RUNBOOK documents that at least one user must be registered before
  dropping SFTP files (see RUNBOOK.md section 4).
- All SFTP-originated batches appear under the admin user's account in the
  API. Reviewers can see them regardless of role.

---

## 2026-05-01 — asyncio.run() bridge in the RQ inference worker

**Context:**
RQ calls job functions synchronously — it runs them in a thread, not in an
asyncio event loop. Our repositories and MinIO client are fully async. We
needed a way to call async code from a sync RQ job function.

**Options considered:**
- **Rewrite repos and blob client as sync** — would require two parallel
  implementations (sync for workers, async for the API). Maintenance burden.
- **asyncio.run()** — creates a fresh event loop inside the sync job function,
  runs all async code in it, closes the loop when done.

**Decision:** `asyncio.run()` inside `run_inference_job()`.

**Consequences:**
- One implementation of repos and adapters — async everywhere.
- Each RQ job gets a fresh event loop. This is correct for a worker process
  (not a server) where jobs run sequentially in the same thread.
- The sync/async boundary is explicit and contained to the one entry-point
  function `run_inference_job()`.

---

## 2026-05-01 — Vault dev mode (not production mode)

**Context:**
HashiCorp Vault manages all application secrets. Vault has a dev mode that
starts with a known root token, stores data in memory, and requires no
initialisation or unseal procedure.

**Options considered:**
- **Vault production mode** — requires initialisation, unseal keys, TLS
  certificates, and persistent storage configuration. Appropriate for real
  deployments.
- **Vault dev mode** — starts instantly, root token is `root`, data is in
  memory. Appropriate for development and graded demos.

**Decision:** Vault dev mode.

**Consequences:**
- `docker compose up` starts Vault with zero configuration beyond setting
  `VAULT_DEV_ROOT_TOKEN_ID=root`.
- All secrets are lost when the Vault container restarts — re-run
  `python scripts/vault_seed.py` after any restart.
- This is intentional for a development and demo environment. A production
  deployment would use Vault with Raft storage and auto-unseal.

---

## 2026-05-01 — Redis queue loss on container restart

**Context:**
RQ stores jobs in Redis. If the Redis container restarts, all queued jobs
that have not yet started are lost. In-flight jobs running in the worker
process complete normally.

**Decision:** Accept this limitation for the current scope. Document it here.

**Mitigation in place:**
- Redis uses `redis:7-alpine` with default persistence off. Restarting Redis
  clears the queue.
- The ingest worker detects orphaned batches indirectly: any batch that stays
  in `pending` status beyond the inference timeout is visible to operators
  via the API.

**What a production system would do:**
- Enable Redis AOF (Append Only File) persistence so the queue survives restarts.
- Or use RQ's built-in `result_ttl` and a periodic cleanup job to requeue
  stuck batches.

---

## 2026-05-01 — Cache TTL choices

| Endpoint | TTL | Rationale |
|----------|-----|-----------|
| `GET /users/me` | 300s | User profile rarely changes; role changes invalidate explicitly |
| `GET /batches` | 60s | New batches arrive infrequently; 60s staleness is acceptable |
| `GET /batches/{id}` | 30s | Status changes (pending → completed) should be visible quickly |
| `GET /predictions/recent` | 15s | Reviewers watch this — stale data longer than 15s is disruptive |

Cache invalidation happens only in `app/services/` — never in routes or repositories.
