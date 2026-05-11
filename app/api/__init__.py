"""HTTP API layer — routers, dependency injection, and middleware.

Layer contract (enforced on code review):
- Routes call exactly one service method and return a domain model.
- No SQLAlchemy imports anywhere in this package.
- No cache operations.
- No business logic beyond input validation.
- HTTPException is raised ONLY here, never in services or repositories.
"""
