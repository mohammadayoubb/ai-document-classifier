# Week 6 Project — Document Classifier as an Authenticated Service
## Phase-by-Phase Build Plan · Team of 4

> **Golden rule:** Understand every line. All four of you will be asked about it on Friday.
> Architecture is the grade. A clean codebase with a slightly-worse model beats a tangled one.

---

## Team Assignments

| Member | Primary Ownership |
|--------|------------------|
| **Member A** | ML Classifier (Colab) · Model artifacts · CI golden-set test |
| **Member B** | Auth (fastapi-users + Vault) · Casbin RBAC · Audit log · User routes |
| **Member C** | Core API layer · Repositories · Services · Caching · Batch/Prediction routes |
| **Member D** | Docker Compose · SFTP ingest worker · Inference worker (RQ) · MinIO · Infra adapters |

Every member also owns their own tests and contributes to integration/smoke tests.

---

## Trello Board Setup (Before Any Code)

Create the board immediately. Columns: **Backlog → To Do → In Progress → Review → Done**

Cards to create on Day 1 (assign owners now):
- [ ] Repo scaffold + CLAUDE.md + pre-commit
- [ ] Docker Compose skeleton (all 9 services)
- [ ] Vault dev mode + KV v2 + seed script
- [ ] Alembic migrations (all tables)
- [ ] fastapi-users JWT auth + Vault key resolution
- [ ] Casbin RBAC + role-toggle endpoint
- [ ] Audit log (service layer)
- [ ] Repository layer (users, batches, predictions)
- [ ] Service layer (batch, prediction, user)
- [ ] fastapi-cache2 Redis setup + invalidation
- [ ] API routes (users, batches, predictions)
- [ ] Infra adapters (MinIO, Redis/RQ, SFTP, Vault, cache)
- [ ] SFTP ingest worker
- [ ] Inference worker (RQ)
- [ ] ML training on Colab (ConvNeXt)
- [ ] Model card + golden set selection (50 images)
- [ ] golden.py replay test
- [ ] GitHub Actions CI pipeline
- [ ] Latency budget verification
- [ ] Structured logging + request ID propagation
- [ ] ARCH.md, DECISIONS.md, RUNBOOK.md, SECURITY.md, COLLABORATION.md
- [ ] Presentation prep

---

## Phase 0 — Repository Scaffold
**Owner: Member D + all**  
**Duration: ~2 hours, Day 1 morning**  
**Parallel: Everyone sets up local dev after this is merged**

### 0.1 — Create repo and folder structure

```
project-root/
├── app/
│   ├── api/                  # HTTP only — routers, no business logic
│   │   ├── __init__.py
│   │   ├── deps.py           # All Depends() functions
│   │   └── routes/
│   │       ├── users.py
│   │       ├── batches.py
│   │       └── predictions.py
│   ├── services/             # Business logic + transaction boundaries + cache invalidation
│   │   ├── batch_service.py
│   │   ├── prediction_service.py
│   │   └── user_service.py
│   ├── repositories/         # SQL only — no HTTP errors, no cache invalidation
│   │   ├── batch_repo.py
│   │   ├── prediction_repo.py
│   │   └── user_repo.py
│   ├── domain/               # Pydantic domain models (NOT ORM models)
│   │   ├── batch.py
│   │   ├── prediction.py
│   │   └── user.py
│   ├── infra/                # External system adapters
│   │   ├── blob.py           # MinIO adapter
│   │   ├── cache.py          # Redis / fastapi-cache2 helpers
│   │   ├── queue.py          # RQ adapter
│   │   ├── sftp.py           # SFTP polling adapter
│   │   └── vault.py          # Vault KV v2 adapter
│   ├── db/
│   │   ├── models.py         # SQLAlchemy ORM models — imported ONLY by repositories
│   │   ├── session.py        # Async engine + SessionLocal
│   │   └── migrations/       # Alembic env.py + versions/
│   ├── classifier/
│   │   ├── model.py          # ConvNeXt loader, weight verification
│   │   ├── predict.py        # Single-image inference function
│   │   ├── models/
│   │   │   ├── classifier.pt         # git LFS
│   │   │   └── model_card.json
│   │   └── eval/
│   │       ├── golden.py             # Replay test
│   │       ├── golden_images/        # 50 TIFFs
│   │       └── golden_expected.json
│   ├── workers/
│   │   ├── ingest.py         # SFTP poller entrypoint
│   │   └── inference.py      # RQ worker entrypoint
│   ├── config.py             # pydantic-settings Settings class
│   └── main.py               # FastAPI app + lifespan
├── tests/
│   ├── unit/
│   ├── integration/
│   └── smoke/
├── notebooks/                # Colab training notebooks (exported)
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml
├── Dockerfile                # For api, worker, sftp-ingest, migrate — multi-stage
├── .env.example
├── .gitignore
├── .dockerignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── CLAUDE.md
├── ARCH.md
├── DECISIONS.md
├── RUNBOOK.md
├── SECURITY.md
├── COLLABORATION.md
└── LICENSES.md
```

### 0.2 — Create `.gitignore`
Include: `.env`, `.env.*`, `.venv/`, `__pycache__/`, `*.py[cod]`, `.idea/`, `.vscode/`, `.DS_Store`, `*.pem`, `*.key`, `htmlcov/`, `.coverage`, `.pytest_cache/`, `.mypy_cache/`

### 0.3 — Create `.dockerignore`
Include: `.git`, `.env`, `.env.*`, `__pycache__/`, `.venv/`, `tests/`, `.github/`, `*.md`, `notebooks/`

### 0.4 — Create `pyproject.toml`
```toml
[project]
name = "doc-classifier"
requires-python = ">=3.11"

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "B", "UP", "ASYNC", "S"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 0.5 — Create `.pre-commit-config.yaml`
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

### 0.6 — Create `.env.example`
```
# Vault — only real secret needed locally
VAULT_ROOT_TOKEN=root

# Ports (override if needed)
API_PORT=8000
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
SFTP_PORT=2222
VAULT_PORT=8200
```

### 0.7 — Git setup
- Create `main` branch, protect it (require PR + review)
- Create initial branches: `feature/infra-scaffold`, `feature/auth`, `feature/api-layer`, `feature/workers`

**Acceptance criteria:**
- [ ] `docker compose up` starts (services may fail — that's ok, scaffold exists)
- [ ] Pre-commit hooks install and run on `git commit`
- [ ] `.env` is listed in `.gitignore`
- [ ] Every folder has an `__init__.py`

---

## Phase 1 — Docker Compose + Supporting Services
**Owner: Member D**  
**Duration: ~4 hours, Day 1**

### 1.1 — `docker-compose.yml`

Nine services exactly as specified:

```yaml
version: "3.9"

services:
  api:
    build:
      context: .
      target: api
    ports: ["${API_PORT:-8000}:8000"]
    env_file: .env
    environment:
      - VAULT_ADDR=http://vault:8200
      - VAULT_TOKEN=${VAULT_ROOT_TOKEN}
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/docclassifier
      - REDIS_URL=redis://redis:6379
      - MINIO_ENDPOINT=minio:9000
    depends_on:
      migrate: { condition: service_completed_successfully }
      vault:   { condition: service_healthy }
    networks: [app-net]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  worker:
    build:
      context: .
      target: worker
    env_file: .env
    environment:
      - VAULT_ADDR=http://vault:8200
      - VAULT_TOKEN=${VAULT_ROOT_TOKEN}
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/docclassifier
      - REDIS_URL=redis://redis:6379
      - MINIO_ENDPOINT=minio:9000
    depends_on:
      migrate: { condition: service_completed_successfully }
    networks: [app-net]

  sftp-ingest:
    build:
      context: .
      target: sftp-ingest
    env_file: .env
    environment:
      - SFTP_HOST=sftp
      - SFTP_PORT=22
      - SFTP_USER=uploader
      - SFTP_PASSWORD=password
      - REDIS_URL=redis://redis:6379
      - MINIO_ENDPOINT=minio:9000
    depends_on: [sftp, minio, redis]
    networks: [app-net]

  migrate:
    build:
      context: .
      target: migrate
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/docclassifier
    depends_on:
      db: { condition: service_healthy }
    networks: [app-net]

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: docclassifier
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes: [postgres_data:/var/lib/postgresql/data]
    networks: [app-net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    networks: [app-net]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "${MINIO_PORT:-9000}:9000"
      - "${MINIO_CONSOLE_PORT:-9001}:9001"
    volumes: [minio_data:/data]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    networks: [app-net]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s

  sftp:
    image: atmoz/sftp
    ports: ["${SFTP_PORT:-2222}:22"]
    volumes: [sftp_uploads:/home/uploader/uploads]
    command: uploader:password:::uploads
    networks: [app-net]

  vault:
    image: hashicorp/vault:1.16
    ports: ["${VAULT_PORT:-8200}:8200"]
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: ${VAULT_ROOT_TOKEN:-root}
      VAULT_DEV_LISTEN_ADDRESS: "0.0.0.0:8200"
    cap_add: [IPC_LOCK]
    networks: [app-net]
    healthcheck:
      test: ["CMD", "vault", "status"]
      interval: 5s
      retries: 10

networks:
  app-net:

volumes:
  postgres_data:
  minio_data:
  sftp_uploads:
```

### 1.2 — Multi-stage `Dockerfile`

```dockerfile
FROM python:3.11-slim AS base
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock* ./
RUN uv pip install --system -r pyproject.toml

COPY app/ ./app/

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "app.workers.inference"]

FROM base AS sftp-ingest
CMD ["python", "-m", "app.workers.ingest"]

FROM base AS migrate
CMD ["alembic", "upgrade", "head"]
```

### 1.3 — Vault seed script `scripts/vault_seed.py`

Run once after `docker compose up vault`:
- Enable KV v2 at `secret/`
- Write: `secret/data/app` with keys: `jwt_signing_key`, `postgres_password`, `minio_secret_key`, `sftp_password`

### 1.4 — MinIO bucket init script `scripts/minio_init.py`

Create buckets: `documents` (raw uploads), `overlays` (annotated PNGs)

**Acceptance criteria:**
- [ ] `docker compose up` starts all 9 services with no errors
- [ ] `curl http://localhost:8000/health` returns 200
- [ ] MinIO console accessible at `localhost:9001`
- [ ] Vault accessible at `localhost:8200`
- [ ] SFTP: `sftp -P 2222 uploader@localhost` works

---

## Phase 2 — Configuration + Vault Adapter
**Owner: Member B**  
**Duration: ~3 hours, Day 1**

### 2.1 — `app/infra/vault.py`

```python
import hvac
import structlog

log = structlog.get_logger()

class VaultClient:
    """Thin wrapper around hvac for KV v2 secret resolution."""

    def __init__(self, addr: str, token: str) -> None:
        self._client = hvac.Client(url=addr, token=token)

    def get_secret(self, path: str, key: str) -> str:
        """Read a single key from KV v2. Raises RuntimeError if missing."""
        response = self._client.secrets.kv.v2.read_secret_version(path=path)
        data = response["data"]["data"]
        if key not in data:
            raise RuntimeError(f"Vault secret '{path}/{key}' not found")
        return data[key]

    def is_reachable(self) -> bool:
        try:
            return self._client.is_authenticated()
        except Exception:
            return False
```

### 2.2 — `app/config.py`

```python
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Resolved at runtime from Vault — set as empty string defaults, overridden in lifespan
    jwt_signing_key: str = ""
    
    # Infrastructure URLs (from environment / docker-compose)
    database_url:    str = Field(..., min_length=1)
    redis_url:       str = "redis://localhost:6379"
    minio_endpoint:  str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = ""    # resolved from Vault
    vault_addr:      str = "http://localhost:8200"
    vault_token:     str = Field(..., min_length=1)
    
    # SFTP
    sftp_host:     str = "localhost"
    sftp_port:     int = 2222
    sftp_user:     str = "uploader"
    sftp_password: str = ""       # resolved from Vault
    sftp_poll_interval_seconds: int = 1   # poll every second, detect drops ≤5s

    # Model
    model_weights_path: str = "app/classifier/models/classifier.pt"
    model_card_path:    str = "app/classifier/models/model_card.json"
    min_test_top1:      float = 0.90   # refuse to start below this

    # App
    classifier_labels: list[str] = [
        "letter", "form", "email", "handwritten", "advertisement",
        "scientific_report", "scientific_publication", "specification",
        "file_folder", "news_article", "budget", "invoice",
        "presentation", "questionnaire", "resume", "memo",
    ]
    low_confidence_threshold: float = 0.7

    # Caching TTLs (seconds)
    cache_ttl_me:         int = 300
    cache_ttl_batches:    int = 60
    cache_ttl_batch:      int = 30
    cache_ttl_recent:     int = 15

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

**Acceptance criteria:**
- [ ] App refuses to start if `VAULT_ADDR` is unreachable (tested manually)
- [ ] `grep -ri 'password' app/` returns zero matches outside `app/infra/vault.py`
- [ ] Missing required env var raises `ValidationError` at startup

---

## Phase 3 — Database Models + Alembic Migrations
**Owner: Member C**  
**Duration: ~4 hours, Day 1-2**

### 3.1 — `app/db/models.py`

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, DateTime, func, Enum as SAEnum
import enum

class Base(DeclarativeBase):
    pass

class BatchStatus(str, enum.Enum):
    pending   = "pending"
    running   = "running"
    completed = "completed"
    failed    = "failed"

class User(Base):
    __tablename__ = "users"
    id:             Mapped[int]  = mapped_column(primary_key=True)
    email:          Mapped[str]  = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    role:           Mapped[str]  = mapped_column(default="auditor")
    is_active:      Mapped[bool] = mapped_column(default=True)
    created_at:     Mapped[DateTime] = mapped_column(server_default=func.now())
    batches:        Mapped[list["Batch"]]     = relationship(back_populates="owner")
    audit_entries:  Mapped[list["AuditLog"]]  = relationship(back_populates="actor")

class Batch(Base):
    __tablename__ = "batches"
    id:          Mapped[int]    = mapped_column(primary_key=True)
    owner_id:    Mapped[int]    = mapped_column(ForeignKey("users.id"))
    status:      Mapped[BatchStatus] = mapped_column(default=BatchStatus.pending)
    created_at:  Mapped[DateTime]    = mapped_column(server_default=func.now())
    updated_at:  Mapped[DateTime]    = mapped_column(server_default=func.now(), onupdate=func.now())
    owner:       Mapped["User"]              = relationship(back_populates="batches")
    predictions: Mapped[list["Prediction"]]  = relationship(back_populates="batch")

class Prediction(Base):
    __tablename__ = "predictions"
    id:              Mapped[int]   = mapped_column(primary_key=True)
    batch_id:        Mapped[int]   = mapped_column(ForeignKey("batches.id"), index=True)
    filename:        Mapped[str]
    storage_key:     Mapped[str]                  # MinIO object key for original
    overlay_key:     Mapped[str | None]           # MinIO object key for overlay PNG
    predicted_label: Mapped[str]
    confidence:      Mapped[float]
    top5_labels:     Mapped[str]                  # JSON array string
    top5_scores:     Mapped[str]                  # JSON array string
    is_relabeled:    Mapped[bool] = mapped_column(default=False)
    relabeled_to:    Mapped[str | None]
    relabeled_by:    Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at:      Mapped[DateTime]  = mapped_column(server_default=func.now())
    batch:           Mapped["Batch"]   = relationship(back_populates="predictions")

class AuditLog(Base):
    __tablename__ = "audit_log"
    id:         Mapped[int]      = mapped_column(primary_key=True)
    actor_id:   Mapped[int]      = mapped_column(ForeignKey("users.id"))
    action:     Mapped[str]                     # "role_change", "relabel", "batch_state_change"
    target:     Mapped[str]                     # description of what changed
    metadata_:  Mapped[str | None]              # JSON extra context
    timestamp:  Mapped[DateTime] = mapped_column(server_default=func.now())
    actor:      Mapped["User"]   = relationship(back_populates="audit_entries")

# Casbin rule table (managed by casbin-sqlalchemy-adapter)
class CasbinRule(Base):
    __tablename__ = "casbin_rule"
    id:    Mapped[int]        = mapped_column(primary_key=True)
    ptype: Mapped[str | None]
    v0:    Mapped[str | None]
    v1:    Mapped[str | None]
    v2:    Mapped[str | None]
    v3:    Mapped[str | None]
    v4:    Mapped[str | None]
    v5:    Mapped[str | None]
```

### 3.2 — `app/db/session.py`

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

### 3.3 — Alembic setup

```bash
alembic init app/db/migrations
# Edit env.py to import Base from app.db.models
# Set sqlalchemy.url from DATABASE_URL env var
alembic revision --autogenerate -m "initial schema"
alembic upgrade head   # verify locally
```

### 3.4 — Casbin policy file `app/infra/casbin_model.conf`

```ini
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
```

### 3.5 — Seed Casbin policies (in migrate container or startup)

```
admin,  /users,            POST
admin,  /users/role,       PUT
admin,  /audit,            GET
reviewer, /batches,        GET
reviewer, /batches/*,      GET
reviewer, /predictions/*,  PATCH
auditor,  /batches,        GET
auditor,  /batches/*,      GET
auditor,  /audit,          GET
```

**Acceptance criteria:**
- [ ] `alembic upgrade head` runs cleanly, all tables exist
- [ ] pgAdmin shows: `users`, `batches`, `predictions`, `audit_log`, `casbin_rule` tables
- [ ] `alembic downgrade -1` works without error

---

## Phase 4 — Authentication (fastapi-users + Vault JWT key)
**Owner: Member B**  
**Duration: ~4 hours, Day 2**

### 4.1 — `app/main.py` — lifespan

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog

log = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # 1. Resolve secrets from Vault — refuse to start if unreachable
    vault = VaultClient(addr=settings.vault_addr, token=settings.vault_token)
    if not vault.is_reachable():
        raise RuntimeError("Vault is unreachable. Refusing to start.")
    
    app.state.vault        = vault
    app.state.jwt_key      = vault.get_secret("app", "jwt_signing_key")
    settings.jwt_signing_key = app.state.jwt_key   # inject into settings

    # 2. Verify classifier weights
    from app.classifier.model import load_and_verify
    app.state.classifier = load_and_verify(settings)   # raises if SHA-256 mismatch or top1 < threshold

    # 3. Verify Casbin policy table is not empty (refuse to start if it is)
    from app.infra.casbin_init import verify_policies_loaded
    await verify_policies_loaded()

    # 4. Redis cache init
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.redis import RedisBackend
    import aioredis
    redis = aioredis.from_url(settings.redis_url)
    FastAPICache.init(RedisBackend(redis), prefix="docclassifier")
    app.state.redis = redis

    # 5. RQ queue
    from rq import Queue
    from redis import Redis as SyncRedis
    app.state.queue = Queue(connection=SyncRedis.from_url(settings.redis_url))

    log.info("app.startup.complete")
    yield

    await redis.close()
    log.info("app.shutdown.complete")

app = FastAPI(lifespan=lifespan, title="Document Classifier API")
```

### 4.2 — `app/api/deps.py`

```python
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/jwt/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
) -> User:
    """Decode JWT, load user from DB. Raises 401 if invalid."""
    ...

async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user

async def require_reviewer_or_above(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "reviewer"):
        raise HTTPException(status_code=403, detail="Reviewer role required")
    return user

def get_queue(request: Request):
    return request.app.state.queue

def get_classifier(request: Request):
    return request.app.state.classifier
```

### 4.3 — Auth routes via fastapi-users

Register: `POST /auth/register`  
Login: `POST /auth/jwt/login` → returns `{ access_token, token_type }`  
JWT signing key MUST come from `app.state.jwt_key` (resolved from Vault at startup).

**Critical checks:**
- `Authorization: Bearer <token>` header — not body, not cookie
- `401` for missing/expired/invalid token
- `403` for valid token, wrong role

**Acceptance criteria:**
- [ ] `POST /auth/register` creates a user with `auditor` role
- [ ] `POST /auth/jwt/login` returns a valid JWT
- [ ] `GET /users/me` with token returns user; without token returns 401
- [ ] Admin-only endpoint returns 403 for auditor token
- [ ] Kill Vault container → `docker compose restart api` fails to boot

---

## Phase 5 — Casbin RBAC + Audit Log
**Owner: Member B**  
**Duration: ~3 hours, Day 2-3**

### 5.1 — Casbin enforcer setup `app/infra/casbin_init.py`

```python
import casbin
from casbin_sqlalchemy_adapter import Adapter
from app.config import get_settings

_enforcer: casbin.AsyncEnforcer | None = None

async def get_enforcer() -> casbin.AsyncEnforcer:
    global _enforcer
    if _enforcer is None:
        adapter = Adapter(get_settings().database_url)
        _enforcer = casbin.AsyncEnforcer("app/infra/casbin_model.conf", adapter)
        await _enforcer.load_policy()
    return _enforcer

async def verify_policies_loaded() -> None:
    enforcer = await get_enforcer()
    policies = await enforcer.get_policy()
    if not policies:
        raise RuntimeError("Casbin policy table is empty. Refusing to start.")
```

### 5.2 — Role-toggle endpoint `app/api/routes/users.py`

```python
@router.put("/users/{user_id}/role")
async def toggle_role(
    user_id: int,
    new_role: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    user_service: UserService = Depends(get_user_service),
):
    """
    Toggle a user's role. Updates Casbin policy + writes audit log entry.
    Cache for affected user is invalidated immediately.
    No re-login required — permissions update on next request.
    """
    ...
```

### 5.3 — Audit log service method `app/services/user_service.py`

```python
async def record_audit(
    self,
    actor_id: int,
    action: str,        # "role_change" | "relabel" | "batch_state_change"
    target: str,
    metadata: dict | None = None,
) -> None:
    """Write an audit log entry. Called from services only — never from routes."""
    ...
```

**Every audit-able event calls `record_audit` before returning.**

**Acceptance criteria:**
- [ ] Role change → audit log row created (verify in pgAdmin)
- [ ] Changed user's role is enforced on next request without re-login
- [ ] `GET /audit` returns entries; auditor can read it; reviewer cannot
- [ ] Last admin cannot demote themselves (guard in service layer)

---

## Phase 6 — Repository + Service + API Layer
**Owner: Member C**  
**Duration: ~6 hours, Day 2-3**

### 6.1 — Repository pattern (all repos follow this contract)

```python
# app/repositories/batch_repo.py
class BatchRepository:
    """SQL only. No HTTP errors. No cache operations. No business logic."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, owner_id: int) -> Batch: ...
    async def get_by_id(self, batch_id: int) -> Batch | None: ...
    async def list_all(self, limit: int, offset: int) -> list[Batch]: ...
    async def update_status(self, batch_id: int, status: BatchStatus) -> Batch: ...
```

Repositories NEVER:
- Raise `HTTPException`
- Call `FastAPICache.invalidate()`
- Contain conditional business logic
- Import from `app/api/`

### 6.2 — Service layer (owns everything repos don't)

```python
# app/services/batch_service.py
class BatchService:
    """Business logic. Transaction boundaries. Cache invalidation. Audit log calls."""

    def __init__(self, repo: BatchRepository, cache: CacheAdapter) -> None:
        self._repo  = repo
        self._cache = cache

    async def create_batch(self, owner_id: int) -> BatchDomain:
        batch = await self._repo.create(owner_id)
        await self._cache.invalidate_batches()          # <-- cache invalidation lives HERE
        return BatchDomain.model_validate(batch)

    async def update_status(self, batch_id: int, status: BatchStatus) -> BatchDomain:
        batch = await self._repo.update_status(batch_id, status)
        await self._cache.invalidate_batch(batch_id)
        return BatchDomain.model_validate(batch)
```

### 6.3 — Domain models `app/domain/`

Pydantic models separate from ORM. Used as service return types and API response shapes.

```python
class BatchDomain(BaseModel):
    id:         int
    owner_id:   int
    status:     BatchStatus
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class PredictionDomain(BaseModel):
    id:               int
    batch_id:         int
    filename:         str
    predicted_label:  str
    confidence:       float
    is_relabeled:     bool
    relabeled_to:     str | None
    model_config = ConfigDict(from_attributes=True)
```

### 6.4 — API routes `app/api/routes/`

Routers ONLY:
- Declare parameters with `Depends()`
- Call one service method
- Return a domain model

```python
# app/api/routes/batches.py
@router.get("/batches", response_model=list[BatchDomain])
@cache(expire=settings.cache_ttl_batches)
async def list_batches(
    user: User = Depends(get_current_user),
    service: BatchService = Depends(get_batch_service),
):
    return await service.list_all()

@router.get("/batches/{batch_id}", response_model=BatchDomain)
@cache(expire=settings.cache_ttl_batch)
async def get_batch(
    batch_id: int,
    user: User = Depends(get_current_user),
    service: BatchService = Depends(get_batch_service),
):
    batch = await service.get_by_id(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch
```

### 6.5 — Cache adapter `app/infra/cache.py`

```python
from fastapi_cache import FastAPICache

class CacheAdapter:
    """Thin wrapper for cache key management and invalidation."""

    async def invalidate_batches(self) -> None:
        await FastAPICache.clear(namespace="batches")

    async def invalidate_batch(self, batch_id: int) -> None:
        await FastAPICache.clear(namespace=f"batch:{batch_id}")

    async def invalidate_user(self, user_id: int) -> None:
        await FastAPICache.clear(namespace=f"user:{user_id}")
```

**Cached endpoints (minimum required):**
- `GET /users/me` — TTL: 300s, invalidated on role change
- `GET /batches` — TTL: 60s, invalidated on batch create/update
- `GET /batches/{bid}` — TTL: 30s, invalidated on status change
- `GET /predictions/recent` — TTL: 15s, invalidated on new prediction

### 6.6 — Prediction relabel endpoint

Only `reviewer` role, only when `confidence < 0.7`:

```python
@router.patch("/predictions/{pred_id}/relabel")
async def relabel_prediction(
    pred_id: int,
    new_label: str,
    user: User = Depends(require_reviewer_or_above),
    service: PredictionService = Depends(get_prediction_service),
):
    ...
```

**Acceptance criteria:**
- [ ] Route files contain zero SQLAlchemy imports
- [ ] Service files contain zero `HTTPException` raises
- [ ] Repository files contain zero `cache.invalidate` calls
- [ ] All 4 required endpoints are cached; cache invalidates on writes (verify with Redis CLI)
- [ ] Relabel returns 403 for auditor, 422 if confidence ≥ 0.7

---

## Phase 7 — ML Classifier (Colab — Member A)
**Owner: Member A**  
**Duration: Day 1-3 (parallel)**

### 7.1 — Training notebook `notebooks/train_rvlcdip.ipynb`

```python
# Key decisions to document in model_card.json:
# - backbone: convnext_tiny_in22k or convnext_small_in22k (torchvision.models only)
# - freeze_policy: "partial_unfreeze" (freeze stem + stage 1, unfreeze stage 2-4 + head)
# - optimizer: AdamW, lr=1e-4, weight_decay=1e-2
# - scheduler: CosineAnnealingLR
# - augmentations: RandomHorizontalFlip, RandomRotation(15), ColorJitter
# - epochs: 10-15 (ConvNeXt converges fast)
# - batch_size: 64
# - input_size: 224x224 grayscale→RGB (replicate channels)
```

Must achieve **≥ 90% top-1 accuracy** on full 40k test split. Track per-class accuracy — identify worst class.

### 7.2 — Golden set selection

50 images: at least 2 per class, deliberately include:
- Easy cases (very clear layout)
- Ambiguous cases (e.g., a memo that looks like a letter)
- Edge cases (poor scan quality)

```json
// golden_expected.json
[
  {
    "filename": "0001.tif",
    "expected_label": "invoice",
    "expected_top1_confidence": 0.9823
  },
  ...
]
```

### 7.3 — `app/classifier/model.py`

```python
import hashlib, json, torch
from torchvision import models
from app.config import Settings

def load_and_verify(settings: Settings) -> torch.nn.Module:
    """
    Load classifier weights and verify:
    1. File exists
    2. SHA-256 matches model_card.json
    3. Reported test top-1 >= settings.min_test_top1
    Raises RuntimeError on any failure — prevents startup.
    """
    weights_path = Path(settings.model_weights_path)
    card_path    = Path(settings.model_card_path)

    if not weights_path.exists():
        raise RuntimeError(f"Classifier weights not found at {weights_path}")

    with open(card_path) as f:
        card = json.load(f)

    # SHA-256 verification
    sha256 = hashlib.sha256(weights_path.read_bytes()).hexdigest()
    if sha256 != card["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch: expected {card['sha256']}, got {sha256}")

    # Quality gate
    if card["test_top1"] < settings.min_test_top1:
        raise RuntimeError(
            f"Model top-1 {card['test_top1']:.3f} < threshold {settings.min_test_top1}"
        )

    model = models.convnext_tiny(weights=None, num_classes=16)
    state_dict = torch.load(weights_path, map_location="cpu")
    model.load_state_dict(state_dict)
    model.eval()
    return model
```

### 7.4 — `app/classifier/predict.py`

```python
def classify_image(model, image_bytes: bytes, labels: list[str]) -> PredictionResult:
    """
    Run inference on raw image bytes.
    Returns top-1 label, confidence, and top-5.
    p95 latency target: < 1.0s on CPU with ConvNeXt Tiny.
    """
    ...
```

### 7.5 — `app/classifier/eval/golden.py`

```python
# Run as: pytest app/classifier/eval/golden.py
def test_golden_set():
    """
    Pass = byte-identical labels, top-1 confidence within 1e-6 of expected.
    Failure blocks CI.
    """
    model = load_and_verify(get_settings())
    with open("app/classifier/eval/golden_expected.json") as f:
        expected = json.load(f)
    
    for item in expected:
        image_bytes = (Path("app/classifier/eval/golden_images") / item["filename"]).read_bytes()
        result = classify_image(model, image_bytes, get_settings().classifier_labels)
        assert result.label == item["expected_label"], f"Label mismatch on {item['filename']}"
        assert abs(result.confidence - item["expected_top1_confidence"]) < 1e-6
```

### 7.6 — `app/classifier/models/model_card.json`

```json
{
  "backbone": "convnext_tiny",
  "torchvision_weights_enum": "ConvNeXt_Tiny_Weights.IMAGENET1K_V1",
  "freeze_policy": "partial_unfreeze",
  "test_top1": 0.921,
  "test_top5": 0.987,
  "golden_top1": 1.0,
  "worst_class": {"name": "handwritten", "accuracy": 0.847},
  "per_class_accuracy": { ... },
  "sha256": "abc123...",
  "environment": {
    "python": "3.11",
    "torch": "2.4.0",
    "torchvision": "0.19.0",
    "colab_gpu": "T4"
  }
}
```

**Acceptance criteria:**
- [ ] `pytest app/classifier/eval/golden.py` passes locally
- [ ] SHA-256 in model_card matches actual `.pt` file
- [ ] Model file committed via git LFS
- [ ] Deliberately corrupted weights → app refuses to start

---

## Phase 8 — Ingestion Pipeline (SFTP → MinIO → RQ)
**Owner: Member D**  
**Duration: ~5 hours, Day 3-4**

### 8.1 — MinIO adapter `app/infra/blob.py`

```python
from miniopy_async import Minio

class BlobStorage:
    """Async MinIO adapter. All MinIO access goes through this class."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str) -> None:
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str) -> None: ...
    async def download(self, bucket: str, key: str) -> bytes: ...
    async def get_presigned_url(self, bucket: str, key: str, expires_seconds: int = 3600) -> str: ...
```

### 8.2 — RQ adapter `app/infra/queue.py`

```python
from rq import Queue
from redis import Redis

class JobQueue:
    """Thin RQ wrapper. Enqueue and inspect jobs."""

    def __init__(self, redis_url: str) -> None:
        self._redis = Redis.from_url(redis_url)
        self._queue = Queue(connection=self._redis)

    def enqueue_inference(self, batch_id: int, prediction_id: int, storage_key: str) -> str:
        """Returns job ID."""
        job = self._queue.enqueue(
            "app.workers.inference.run_inference_job",
            batch_id, prediction_id, storage_key,
            job_timeout=30,
        )
        return job.id
```

### 8.3 — SFTP ingest worker `app/workers/ingest.py`

```python
"""
SFTP poller. Polls every {sftp_poll_interval_seconds} seconds.
On new file:
  1. Download from SFTP
  2. Validate (not zero-byte, is valid image, < 50MB)
  3. Upload to MinIO bucket 'documents'
  4. Create Batch + Prediction rows in DB
  5. Enqueue inference job
  6. Delete from SFTP (or move to processed/)

On malformed file:
  - Log structured error with filename, reason
  - Move to 'quarantine/' on SFTP
  - Do NOT crash the poller

Detect drops within 5 seconds (poll_interval = 1s default).
"""
```

Error handling — what to do for each case:
- Zero-byte file → quarantine + log `"ingest.error.empty_file"`
- Non-image file → quarantine + log `"ingest.error.invalid_format"`
- File > 50MB → quarantine + log `"ingest.error.file_too_large"`
- MinIO unreachable → retry 3x with backoff, log `"ingest.error.blob_unreachable"`, do NOT quarantine
- Redis unreachable → retry 3x, log `"ingest.error.queue_unreachable"`

### 8.4 — Inference worker `app/workers/inference.py`

```python
def run_inference_job(batch_id: int, prediction_id: int, storage_key: str) -> None:
    """
    RQ job function (sync — RQ runs in threads).
    1. Download image from MinIO
    2. Run classify_image()
    3. Write prediction result to DB (label, confidence, top5)
    4. Generate annotated overlay PNG (draw predicted label + confidence bar)
    5. Upload overlay to MinIO 'overlays' bucket
    6. Update prediction row with overlay_key
    7. Update batch status to 'completed' (or 'failed' on error)
    8. Invalidate affected caches via service layer
    9. Log structured job result with request_id
    """
```

**p95 latency target: < 1.0s inference, < 10s end-to-end from SFTP drop to GET /batches/{bid}**

**Acceptance criteria:**
- [ ] Drop a TIFF via `scp -P 2222 file.tif uploader@localhost:uploads/`
- [ ] Within 5 seconds: batch row created in DB
- [ ] Within 10 seconds: prediction row with label visible in `GET /batches/{bid}`
- [ ] Overlay PNG visible in MinIO console
- [ ] Zero-byte file → quarantine folder, structured log entry, poller continues

---

## Phase 9 — Logging + Request ID Propagation
**Owner: Member C (API side) + Member D (worker side)**  
**Duration: ~3 hours, Day 4**

### 9.1 — Structured logging setup `app/infra/logging_setup.py`

```python
import structlog, logging, sys
from pathlib import Path

def configure_logging(log_level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level)
        ),
    )
    # Write to persistent file AND stdout
    handler = logging.FileHandler("logs/app.log")
    logging.basicConfig(handlers=[handler, logging.StreamHandler(sys.stdout)])
```

### 9.2 — Request ID middleware `app/api/middleware.py`

```python
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response
```

Every log line across api + worker carries `request_id`. Pass it as a job argument to RQ.

**Acceptance criteria:**
- [ ] Every request log line is valid JSON with `request_id`, `timestamp`, `level`
- [ ] The same `request_id` appears in API log AND worker log for the same document
- [ ] Logs write to `logs/app.log` (persists across container restart)
- [ ] Zero `print()` calls in `app/` directory

---

## Phase 10 — GitHub Actions CI
**Owner: Member A**  
**Duration: ~3 hours, Day 4-5**

### 10.1 — `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install uv && uv pip install --system -e ".[dev]"
      - run: ruff check .
      - run: mypy app/

  golden-set-test:
    runs-on: ubuntu-latest
    needs: lint-and-typecheck
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install uv && uv pip install --system -e ".[dev]"
      - run: pytest app/classifier/eval/golden.py -v
        # Failure here blocks all downstream jobs

  smoke-test:
    runs-on: ubuntu-latest
    needs: golden-set-test
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true
      - name: Start stack
        run: |
          cp .env.example .env
          docker compose up -d --build
          sleep 30   # wait for services
      - name: Health check
        run: curl -f http://localhost:8000/health
      - name: Register + login
        run: |
          curl -sf -X POST http://localhost:8000/auth/register \
            -H "Content-Type: application/json" \
            -d '{"email":"test@test.com","password":"TestPass123!"}'
      - name: SFTP drop + verify prediction
        run: |
          # Drop a golden image via SCP
          scp -P 2222 -o StrictHostKeyChecking=no \
            app/classifier/eval/golden_images/0001.tif \
            uploader@localhost:uploads/
          # Wait up to 15s for prediction to appear
          python scripts/smoke_check.py
      - name: Tear down
        if: always()
        run: docker compose down -v
```

### 10.2 — `scripts/smoke_check.py`

Poll `GET /batches` with admin token until prediction appears, timeout at 15s. Exit 1 if not found.

**Acceptance criteria:**
- [ ] Push a commit with a broken golden test → CI fails on `golden-set-test` job
- [ ] Full stack smoke test passes on a clean clone
- [ ] CI badge in README shows green

---

## Phase 11 — Latency Budget Verification
**Owner: Member C**  
**Duration: ~2 hours, Day 5**

### Target numbers (commit these in README)

| Metric | Target | How to measure |
|--------|--------|---------------|
| API cached read p95 | < 50ms | `wrk` or `locust` against `GET /batches` (warm cache) |
| API uncached read p95 | < 200ms | same endpoint, `Cache-Control: no-cache` |
| Inference p95 | < 1.0s | time `classify_image()` over 50 golden images |
| End-to-end p95 | < 10s | SFTP drop → `GET /batches/{bid}` shows prediction |

### `scripts/benchmark.py`

```python
# Measure inference latency over the 50 golden images
# Output: p50, p95, p99 in ms
# If p95 > 1000ms: print warning and suggest switching from ConvNeXt Small → Tiny
```

---

## Phase 12 — Documentation
**Owner: All (review together)**  
**Duration: ~3 hours, Day 5-6**

### `ARCH.md`
- ASCII diagram of all 9 containers + data flows
- Layer diagram: api → services → repositories → domain/infra
- Describe: where secrets live, where cache lives, where queue lives

### `DECISIONS.md`
Format for each decision:
```
## [Date] — Decision title
Context: Why we faced this choice
Options: What we considered
Decision: What we chose
Consequences: Trade-offs we accepted
```
Required decisions to document:
- Why RQ over Celery
- Why ConvNeXt Tiny vs Small
- Freeze policy rationale
- Cache TTL choices
- Why Vault dev mode (not production mode)
- How you handle Redis queue loss on container restart

### `RUNBOOK.md`
- `docker compose up` from scratch
- How to run the golden test manually
- How to seed Vault secrets
- How to add a new user and set their role
- How to drop a test TIFF via SCP
- How to check logs
- How to restart just the worker
- How to swap model weights

### `SECURITY.md`
- Secrets management approach
- What Vault KV v2 stores
- JWT signing key rotation procedure
- `grep -ri 'password' app/` returns nothing guarantee
- CORS configuration
- What an attacker gets if they steal a JWT (and why that's acceptable)

### `COLLABORATION.md`
- Trello board link
- Who owned what
- How you handled merges/review
- Where you got stuck + how you unblocked
- One decision the team disagreed on

---

## Phase 13 — Final Hardening + Demo Prep
**Owner: All**  
**Duration: Day 6**

### Pre-submission checklist (run the full `08_pre_build_checklist.md`)

Critical items to verify live before Thursday midnight:
- [ ] `docker compose up` from clean clone works
- [ ] `cp .env.example .env` is literally all setup needed
- [ ] `grep -ri 'password' app/` returns zero matches (outside Vault code)
- [ ] Kill Vault → api refuses to start
- [ ] Corrupt `.pt` file → api refuses to start  
- [ ] SFTP drop → prediction visible in 10s
- [ ] Role toggle → next request enforces new role (no re-login)
- [ ] Broken golden test fails CI
- [ ] All 4 cached endpoints return `X-Cache: HIT` on second request
- [ ] Logs write to file, not just stdout
- [ ] All 4 members can explain every component

### Demo script (practice this)

1. `git clone <repo> && cd repo && cp .env.example .env && docker compose up`
2. Show all 9 containers healthy
3. Register admin/reviewer/auditor users
4. `scp -P 2222 invoice.tif uploader@localhost:uploads/`
5. Show prediction appearing in `GET /batches/{bid}` within 10s
6. Show overlay PNG in MinIO console
7. Show reviewer can relabel low-confidence prediction; auditor cannot
8. Toggle reviewer → auditor role; show immediate permission change
9. Show audit log entry for role change
10. Kill Vault: `docker compose stop vault`, `docker compose restart api` → watch it refuse
11. Show CI failing on broken golden test (have a branch ready)
12. Walk Trello board

---

## Critical "Think About" Answers (prepare before Friday)

| Question | Your answer |
|----------|-------------|
| MinIO unreachable mid-job | Worker catches `MinioException`, marks batch as `failed`, logs structured error, does NOT crash RQ worker process |
| Redis loses queue (container restart) | In-flight jobs are lost (RQ limitation). Mitigation: RQ persistence via `result_ttl`, or use RQ with AOF Redis. Document in DECISIONS.md |
| Last admin demotes themselves | Service layer checks: if `user.role == "admin"` and count of admins == 1, raise `HTTPException(409, "Cannot demote last admin")` |
| Cache vs DB disagreement | Cache has TTL — stale data resolves on expiry. For immediate consistency: service invalidates on write. Document your TTL choices |
| Malformed SFTP drop | Quarantine to `uploads/quarantine/`, log structured error, poller continues |
| Model hot-swap | Stop workers, replace `.pt`, update `model_card.json` SHA-256, restart workers. In-flight jobs complete with old model (acceptable). Document in RUNBOOK.md |

---

## Tag & Submit

```bash
git tag v0.1.0-week6
git push origin v0.1.0-week6
```

Submission format:
```
Project 6, [Name 1], [Name 2], [Name 3], [Name 4]
Repo: https://github.com/...
Trello: https://trello.com/...
Tag: v0.1.0-week6
Backbone: convnext_tiny | ConvNeXt_Tiny_Weights.IMAGENET1K_V1
Freeze policy: partial_unfreeze
Test top-1: 0.921 | Top-5: 0.987 | Worst-class: 0.847 (handwritten)
Latency p95: api-uncached=142ms inference=680ms e2e=7.2s
README contains: ARCH.md, DECISIONS.md, RUNBOOK.md, SECURITY.md, COLLABORATION.md
```
