# Security

Security model for the AI Document Classifier service.

---

## Secrets Management

All application secrets are stored in **HashiCorp Vault KV v2** at `secret/data/app`.
Nothing sensitive is hardcoded or committed to version control.

### What lives in Vault

| Key | Used by |
|-----|---------|
| `jwt_signing_key` | `api` — signs and verifies JWT access tokens |
| `postgres_password` | `api`, `worker`, `sftp-ingest`, `migrate` — database connection |
| `minio_secret_key` | `worker`, `sftp-ingest` — MinIO object storage access |
| `sftp_password` | `sftp-ingest` — SFTP server authentication |

### What lives in `.env`

`.env` contains **only**:
- `VAULT_ROOT_TOKEN` — the Vault dev mode root token (not an application secret)
- Port overrides (optional)

`.env` is git-ignored from commit zero. `.env.example` ships as the template.

### Startup contract

`api`, `worker`, and `sftp-ingest` **refuse to start** if Vault is unreachable or any required
secret key is missing. The check runs in `lifespan` before the app accepts any requests.

```python
# app/main.py — lifespan
vault = VaultClient(addr=settings.vault_addr, token=settings.vault_token)
if not vault.is_reachable():
    raise RuntimeError("Vault is unreachable. Refusing to start.")
settings.jwt_signing_key = vault.get_secret("app", "jwt_signing_key")
```

### Verification

```bash
# Must return zero matches (outside app/infra/vault.py)
grep -ri 'password' app/
grep -ri 'secret' app/
```

---

## Authentication — JWT (fastapi-users)

- **Scheme:** `Authorization: Bearer <token>` header — never in body or query string
- **Signing key:** Resolved from Vault at startup — never hardcoded
- **Token lifetime:** 60 minutes
- **Library:** `fastapi-users` with SQLAlchemy adapter

### Token theft threat model

If an attacker steals a valid JWT:
- They can act as that user for up to **60 minutes** (token lifetime)
- They cannot escalate their role — roles are stored in PostgreSQL and re-read on every request
- They cannot access other users' data — all queries are scoped by the authenticated user
- After 60 minutes the token expires and is worthless

The 60-minute lifetime is acceptable for an internal enterprise tool where tokens are not
stored in cookies (no CSRF risk) and the threat of token interception is low on a private network.

### JWT signing key rotation

1. Generate a new key: `python -c "import secrets; print(secrets.token_hex(64))"`
2. Write it to Vault: update `jwt_signing_key` in `secret/data/app`
3. Restart `api`: `docker compose restart api`

All existing tokens are immediately invalidated — users must log in again.

---

## Authorization — Casbin RBAC

Three roles with explicit permission grants. No implicit permissions.

| Role | Allowed actions |
|------|----------------|
| `admin` | All routes including role toggle and audit log |
| `reviewer` | View batches, relabel predictions where confidence < 0.7 |
| `auditor` | Read-only on batches and audit log |

Role enforcement uses `require_admin` and `require_reviewer_or_above` dependencies
declared in `app/api/deps.py`. Every route that requires authorization declares its
dependency explicitly — there is no global middleware that silently grants access.

Role changes take effect on the **next request** — no re-login required.
Every role change writes an entry to the audit log (actor, action, target, timestamp).

The last admin cannot demote themselves — the `user_service` checks and returns `409 Conflict`.

---

## CORS

The API allows cross-origin requests from the frontend origins only:

```python
allow_origins=["http://localhost:5173", "http://localhost:3000"]
```

All other origins are blocked by the browser's CORS policy.
`allow_credentials=True` is required for the `Authorization` header to be forwarded.

---

## HTTP Status Codes

The API never returns `200 OK` with an error body.

| Code | Meaning |
|------|---------|
| 401 | No token, expired token, or bad signature |
| 403 | Valid token, insufficient role |
| 404 | Resource not found |
| 409 | Conflict (e.g., last admin demoting themselves) |
| 422 | Pydantic validation failure |
| 500 | Unhandled server error — generic message to client, full trace in logs |

Stack traces never reach the client. They are logged server-side with `log.exception(...)`.

---

## Object Storage (MinIO)

- `documents` bucket — **private**. Only the service account can read/write.
- `overlays` bucket — **public-read**. Annotated overlay PNGs are served directly
  to the frontend browser without an API proxy. The bucket policy allows anonymous
  `s3:GetObject` only — no write or list access.

---

## Audit Log

Every sensitive action is recorded in the `audit_log` table:

| Event | Logged fields |
|-------|--------------|
| Role change | actor_id, target_user_id, old_role, new_role, timestamp |
| Prediction relabel | actor_id, prediction_id, old_label, new_label, timestamp |
| Batch state change | actor_id, batch_id, old_status, new_status, timestamp |

Audit log entries are written by `app/services/audit_service.py` — never by routes
or repositories directly.
