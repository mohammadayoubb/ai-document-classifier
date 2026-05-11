"""Service layer — business logic, transaction boundaries, cache invalidation.

Services are the ONLY layer that:
- Contains business logic and decision-making conditionals
- Calls cache.invalidate() via the CacheAdapter
- Writes audit log entries
- Coordinates between repositories and infra adapters

Services NEVER:
- Raise HTTPException (raise domain-specific ValueError / LookupError instead)
- Directly manage SQLAlchemy sessions (sessions are injected via constructor)
- Import from app/api/
"""
