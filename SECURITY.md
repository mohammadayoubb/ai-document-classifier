# Security

> Complete in Phase 12 with full secrets management writeup.

## Sections to document

- Secrets management approach — all secrets in Vault KV v2, not in `.env`
- What `secret/data/app` stores: `jwt_signing_key`, `postgres_password`, `minio_secret_key`, `sftp_password`
- JWT signing key rotation procedure
- Guarantee: `grep -ri 'password' app/` returns zero matches outside `app/infra/vault.py`
- CORS configuration
- What an attacker gets if they steal a JWT — and why the 60-minute lifetime is acceptable
