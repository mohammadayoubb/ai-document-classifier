# CLAUDE.md — Document Classifier Service
## Engineering Standards & Architecture Contract

> This file is the ground truth for every code decision in this repo.
> Read it fully before writing a single line. Every teammate will be asked to defend code they didn't write.

---

## Project Overview

An internal document classification service (RVL-CDIP, 16 classes) built as a layered microservice stack. A scanner vendor drops TIFF images via SFTP; a worker pipeline classifies them using a fine-tuned ConvNeXt model; authenticated users with role-based permissions browse and review results through a permission-gated API. The entire stack runs via `docker compose up`.

**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 · Redis 7 · MinIO · atmoz/sftp · HashiCorp Vault (dev) · RQ · SQLAlchemy 2 + Alembic · fastapi-users (JWT) · Casbin · fastapi-cache2 · ConvNeXt (torchvision) · GitHub Actions

---

## The Single Most Important Rule

> **You must be able to defend every line in this repository.**
> "The AI suggested it" is never an answer. If you pasted code without understanding it, go back and understand it now.

---

## Architecture — The Layered Contract

This is NOT a suggestion. The architecture is the grade. Violating layer boundaries fails the review.

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
```

```
app/domain/           ← Pydantic domain models (NOT ORM models, used as service return types)
app/infra/            ← External system adapters: blob.py, cache.py, queue.py, sftp.py, vault.py
app/config.py         ← pydantic-settings Settings class (single source of truth for all config)
app/main.py           ← FastAPI app + lifespan ONLY
```

### Layer rules — enforced on code review

**`app/api/routes/`**
- ✅ Declare parameters with `Depends()`
- ✅ Call exactly one service method
- ✅ Raise `HTTPException` (ONLY place allowed)
- ✅ Return a domain model
- ❌ NO SQLAlchemy imports
- ❌ NO direct DB queries
- ❌ NO cache operations
- ❌ NO business logic or conditionals beyond input validation

**`app/services/`**
- ✅ All business logic lives here
- ✅ Transaction boundaries (commit/rollback decisions)
- ✅ Cache invalidation calls
- ✅ Audit log calls
- ✅ Call repositories
- ✅ Call infra adapters
- ❌ NO `HTTPException` raises (raise domain exceptions instead)
- ❌ NO direct SQLAlchemy session management

**`app/repositories/`**
- ✅ SQL queries and ORM operations ONLY
- ✅ Accept `AsyncSession` via constructor injection
- ✅ Return ORM model instances or None
- ❌ NO `HTTPException`
- ❌ NO `FastAPICache.invalidate()` or any cache call
- ❌ NO business logic or conditionals beyond query construction
- ❌ NO imports from `app/api/`

**`app/db/models.py`**
- ✅ SQLAlchemy ORM models ONLY
- ✅ Imported ONLY by `app/repositories/`
- ❌ Never imported in routes, services, or domain

**`app/infra/`**
- One file per external system: `blob.py` (MinIO), `cache.py` (Redis), `queue.py` (RQ), `sftp.py`, `vault.py`
- Each exposes a clean class with typed methods
- No HTTP framework imports

---

## Python Engineering Standards

### Async — all the way down

Every function in the request path that does I/O (network, DB, Redis) MUST be `async`.
One blocking call freezes the event loop for every concurrent user.

```python
# ✗ WRONG — blocking in async route
@app.post("/batches")
async def create_batch():
    result = requests.get(SOME_URL)   # blocks event loop

# ✓ CORRECT
@app.post("/batches")
async def create_batch():
    async with httpx.AsyncClient() as http:
        result = await http.get(SOME_URL)
```

- Use `httpx.AsyncClient` — never `requests` in a request path
- Use `await asyncio.sleep()` — never `time.sleep()`
- CPU-bound work (ML inference) → `asyncio.to_thread()` or runs in RQ worker (separate process)
- The RQ worker is synchronous (RQ uses threads) — that is correct and intentional

### Dependency Injection with `Depends()`

Every route parameter is injected. Nothing is constructed inside a route body.

```python
# dependencies.py — all Depends() functions live here
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    ...

# Route — declares what it needs, gets it delivered
@router.post("/batches")
async def create_batch(
    user: User = Depends(get_current_user),
    service: BatchService = Depends(get_batch_service),
):
    return await service.create_batch(owner_id=user.id)
```

`yield` in a dependency = resource lifecycle (open → yield → cleanup after request).
Never call `session.close()` manually in a route.

### Singletons via `lifespan`

Objects expensive to create and safe to share are created ONCE at startup:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — runs once
    app.state.classifier = load_and_verify(settings)
    app.state.queue      = JobQueue(settings.redis_url)
    yield
    # Shutdown — cleanup
```

| Scope | Mechanism | Examples |
|-------|-----------|---------|
| Per-process | `lifespan` + `app.state` | Classifier model, DB engine, RQ queue |
| Per-request | `yield` in `Depends()` | DB session, current user |
| Per-call | No caching | Computed values from input |

### Configuration — `pydantic-settings`

One `Settings` class. All env vars typed. Missing required values fail at startup.
`extra="forbid"` — typo in `.env` raises error, no silent `None`.
`os.getenv()` is forbidden outside `app/config.py`.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")
    database_url: str = Field(..., min_length=1)
    vault_token:  str = Field(..., min_length=1)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

### Caching

`lru_cache` — pure, deterministic, in-memory helpers (e.g., `get_settings()`).
`fastapi-cache2` (Redis) — HTTP endpoints with TTL. Invalidation lives in the **service layer only**.

Minimum cached endpoints:
- `GET /users/me` — TTL 300s, invalidated on role change
- `GET /batches` — TTL 60s, invalidated on any batch mutation
- `GET /batches/{bid}` — TTL 30s, invalidated on status/prediction change
- `GET /predictions/recent` — TTL 15s, invalidated on new prediction

Cache invalidation rule: **Only `app/services/` calls invalidation. Routers and repositories never touch cache.**

### Type Hints

All function signatures require type hints. No exceptions.
`mypy --strict` must pass. CI enforces it.

Pydantic models are required at:
- HTTP request bodies (FastAPI route parameters)
- Tool/job function inputs
- LLM structured outputs
- All domain model returns from services

### Error Handling

```python
# External calls — always timeout
async with httpx.AsyncClient(timeout=10.0) as client:
    response = await client.get(url)

# Retries — transient failures only (NOT on 4xx)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
)
async def call_external_service(): ...
```

Worker tools return structured errors — they do NOT crash the job:

```python
class JobError(BaseModel):
    error: str
    retryable: bool

async def download_document(...) -> bytes | JobError:
    try:
        return await blob.download(bucket, key)
    except MinioException as e:
        return JobError(error=str(e), retryable=True)
```

HTTP status codes (never return `200 OK` with `{"error": "..."}`):

| Code | When |
|------|------|
| 200 | Success with body |
| 201 | Created |
| 400 | Malformed input |
| 401 | No token / expired / bad signature |
| 403 | Valid token, wrong role |
| 404 | Resource not found |
| 409 | Conflict (e.g., last admin demoting themselves) |
| 422 | Pydantic validation failure |
| 500 | Unhandled server error (log full trace; show generic message to client) |

Stack traces **never** reach the client. Log them server-side with `log.exception(...)`.

---

## Authentication & Authorization

### JWT (fastapi-users)

- `Authorization: Bearer <token>` header — not body, not query string
- JWT signing key resolves from Vault at startup — never hardcoded
- Access token lifetime: 60 minutes
- `401` = no token / expired / bad signature
- `403` = valid token, insufficient role

### Casbin RBAC

Three roles:

| Role | Permissions |
|------|------------|
| `admin` | Invite users, toggle roles, view audit log |
| `reviewer` | View batches, relabel predictions where confidence < 0.7 |
| `auditor` | Read-only on batches and audit log |

Enforcement: `require_admin`, `require_reviewer_or_above` dependencies in `app/api/deps.py`.
Role changes take effect on the next request — no re-login required.
Role changes ALWAYS write an audit log entry.

### Audit Log

Every audit-able event calls `audit_service.record(actor_id, action, target)` from the service layer.
Audit-able events: role change, prediction relabel, batch state change.

---

## Database Standards

### ORM Models

Only `app/db/models.py`. Imported ONLY by `app/repositories/`.
`__tablename__` is the line that connects Python class → PostgreSQL table.

### Migrations

Every schema change has an Alembic migration committed.
"Delete the volume" is not a migration strategy.
`alembic upgrade head` runs in the `migrate` container before `api` boots.
Know the difference: `upgrade` applies pending migrations; `downgrade` reverts the last one.

### Session Lifecycle

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Response Models (DTO Pattern)

`response_model` on every endpoint is a domain model, NOT the ORM model.
`hashed_password`, `internal_ids`, and other private fields never appear in responses.

---

## Secrets Management

### The hard rule

**Never commit secrets, credentials, API keys, or passwords to version control.**
`.env` is in `.gitignore` from commit zero. Not "I'll add it later."

### What lives in Vault (KV v2 at `secret/data/app`)

- `jwt_signing_key`
- `postgres_password`
- `minio_secret_key`
- `sftp_password`

`.env` contains ONLY:
- `VAULT_ROOT_TOKEN` (dev mode token)
- Port overrides

**Verification command (must return nothing):**
```bash
grep -ri 'password' app/    # zero matches outside app/infra/vault.py
grep -ri 'secret' app/      # zero hardcoded values
```

The `api` and `worker` containers refuse to start if Vault is unreachable.

---

## Docker & Compose

Nine services. Every service in its own container. No exceptions.

| Service | Purpose |
|---------|---------|
| `api` | FastAPI app |
| `worker` | RQ inference worker |
| `sftp-ingest` | SFTP poller |
| `migrate` | Alembic migrations (runs and exits) |
| `db` | postgres:16 |
| `redis` | redis:7 |
| `minio` | S3-compatible blob |
| `sftp` | atmoz/sftp |
| `vault` | hashicorp/vault dev mode |

**Networks vs Volumes — do not confuse them:**
- **Networks:** Let containers reach each other by name (`http://api:8000`). Do NOT persist data.
- **Volumes:** Persist data across container restarts (`postgres_data`, `minio_data`, `sftp_uploads`).

No hardcoded URLs. All environment-specific values use variables with fallbacks:
```yaml
DATABASE_URL: ${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@db:5432/docclassifier}
```

`docker compose up` from a clean clone (after `cp .env.example .env`) must work with zero other setup.

---

## Classifier Startup Contract

`api` and `worker` REFUSE TO START if:
1. `app/classifier/models/classifier.pt` does not exist
2. SHA-256 of the weights does not match `model_card.json`
3. `model_card.json`'s `test_top1` is below the threshold committed in README
4. Vault is unreachable
5. Casbin policy table is empty

These checks run in `lifespan` before the app accepts requests.

---

## Worker Pipeline

### SFTP Ingest Worker (`app/workers/ingest.py`)

- Polls SFTP every 1 second (detects drops ≤ 5s)
- On new file: validate → upload to MinIO → create Batch + Prediction rows → enqueue RQ job → move to `processed/`
- On malformed file (zero-byte, non-image, > 50MB): move to `quarantine/`, structured log, DO NOT crash
- On infrastructure failure (MinIO/Redis unreachable): retry 3× with backoff, log, DO NOT quarantine

### Inference Worker (`app/workers/inference.py`)

RQ job function — synchronous (RQ uses threads):
1. Download from MinIO
2. Run `classify_image()`
3. Write prediction to DB (label, confidence, top5)
4. Generate annotated overlay PNG
5. Upload overlay to MinIO
6. Update prediction + batch status
7. Invalidate caches via service layer
8. Log structured result with `request_id`

p95 latency targets (committed in README, demonstrated in demo):
- API cached reads: < 50ms
- API uncached reads: < 200ms
- Inference per document: < 1.0s (CPU, ConvNeXt Tiny/Small)
- End-to-end (SFTP drop → visible in API): < 10s

---

## Logging

`print()` is forbidden in `app/`. Use `structlog`.

```python
import structlog
log = structlog.get_logger()

log.info("batch.created", batch_id=batch.id, owner_id=owner_id)
log.warning("ingest.retry", filename=filename, attempt=attempt)
log.exception("worker.job.failed", job_id=job_id, error=str(e))
```

Every log line is JSON with: `timestamp`, `level`, `event`, `request_id`, and relevant context keys.
`request_id` propagates from API → RQ job argument → worker logs.
Logs write to `logs/app.log` (persistent volume) AND stdout.

Log levels:
- `DEBUG` — variable values, verbose diagnostics (dev only)
- `INFO` — normal events (batch created, job completed, user registered)
- `WARNING` — unexpected but recoverable (retry attempt, empty batch)
- `ERROR` — operation failed (DB timeout, MinIO unreachable)
- `CRITICAL` — system unusable (can't connect to DB at startup)

---

## Code Style

### Tooling (all enforced in CI)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "B", "UP", "ASYNC", "S"]

[tool.mypy]
strict = true
```

Pre-commit pipeline: `ruff format → ruff check → mypy → gitleaks`

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables, functions | `snake_case` | `batch_id`, `get_prediction()` |
| Classes | `PascalCase` | `BatchService`, `BlobStorage` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES = 3` |
| Files / modules | `snake_case` | `batch_service.py` |
| Private attributes | `_leading_underscore` | `self._session` |
| Booleans | reads as question | `is_active`, `has_permission` |
| Collections | plural | `batches`, `predictions` |
| Functions | start with verb | `fetch_batch()`, `validate_image()` |

Avoid: `process_data()`, `utils.py`, `helpers.py`, `misc.py`, `thing.py`
Use: `classify_document()`, `blob_storage.py`, `casbin_enforcer.py`

### Docstrings

Google-style on all public modules, classes, and functions:

```python
def classify_image(model: nn.Module, image_bytes: bytes, labels: list[str]) -> PredictionResult:
    """Run inference on raw image bytes.

    Args:
        model: Loaded ConvNeXt model in eval mode.
        image_bytes: Raw TIFF or PNG bytes.
        labels: Ordered list of class names (16 for RVL-CDIP).

    Returns:
        PredictionResult with top-1 label, confidence, and top-5.

    Raises:
        ValueError: If image_bytes cannot be decoded as an image.
    """
```

### Inline Comments

```python
# Good — explains WHY
# Casbin enforcer must be re-loaded after role toggle — cached policy becomes stale
await enforcer.load_policy()

# Bad — explains WHAT (the code already says this)
# Load policy
await enforcer.load_policy()
```

Markers: `# TODO:`, `# FIXME:`, `# HACK:` — always with reason.

### Import Order

```python
# 1. Standard library
import hashlib
from pathlib import Path

# 2. Third-party
import structlog
from fastapi import Depends, HTTPException

# 3. Local
from app.config import get_settings
from app.domain.batch import BatchDomain
```

---

## Git Workflow

### Branch naming

```
feature/user-authentication
bugfix/sftp-poller-crash-on-empty-file
refactor/extract-casbin-enforcer
test/golden-set-replay
chore/add-github-actions-ci
```

- Lowercase + hyphens only
- Never commit directly to `main`
- Delete merged branches

### Commit messages (Conventional Commits)

```
feat(auth): add JWT-based registration and login
fix(worker): quarantine zero-byte SFTP drops instead of crashing
refactor(cache): move invalidation from routes to service layer
test(classifier): add golden-set replay test
chore(ci): add golden-set CI job
security(vault): resolve JWT signing key from Vault at startup
```

Imperative mood. Under 72 chars. No period.

### Pull Request rules

- Fewer than 400 lines of change per PR
- One concern per PR (no mixing features + refactors)
- At least one reviewer before merging
- Resolve all comments before merging
- Squash on merge to keep `main` clean
- Link issues: `Closes #42`

---

## Testing Standards

### File / function naming

```
tests/unit/test_batch_service.py
tests/unit/test_prediction_repo.py
tests/integration/test_auth_flow.py
tests/smoke/test_sftp_to_prediction.py

def test_relabel_returns_403_for_auditor_role():
def test_confidence_below_threshold_allows_relabel():
def test_batch_status_invalidates_cache_on_update():
```

### Patterns

- Arrange → Act → Assert (AAA) in every test
- One assertion per test when possible
- Mock all external dependencies in unit tests (MinIO, Redis, SFTP, LLM)
- Test both success and failure paths

```python
# Pydantic validation test
def test_prediction_domain_rejects_negative_confidence():
    with pytest.raises(ValidationError):
        PredictionDomain(confidence=-0.1, ...)

# Service test with mocked repo
async def test_create_batch_invalidates_cache(mocker):
    mock_cache = mocker.AsyncMock()
    service = BatchService(repo=MockBatchRepo(), cache=mock_cache)
    await service.create_batch(owner_id=1)
    mock_cache.invalidate_batches.assert_called_once()
```

### Coverage targets

- New code: ≥ 80% line coverage
- Auth, relabel, role-toggle paths: ≥ 95%

### CI — tests that don't run automatically don't exist

Every push runs: `ruff → mypy → golden-set test → docker build → smoke test`
Golden-set test failure blocks all downstream jobs.

---

## The Presentation Contract

Be ready to answer live:
- Point at the exact line where `session.commit()` happens for any write
- Point at the exact line where tools are enqueued to RQ
- Explain what happens when Vault is killed mid-request
- Add a hypothetical new endpoint live (know your layer boundaries cold)
- Explain a teammate's code in detail

The reviewer will ask you to add a new endpoint or CLI command live. Know the layer contract well enough to answer in 60 seconds.
