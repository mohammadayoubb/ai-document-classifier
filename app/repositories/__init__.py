"""Repository layer — SQL operations only.

Repositories:
- Accept an AsyncSession via constructor injection
- Return ORM model instances or None
- NEVER raise HTTPException
- NEVER call cache.invalidate()
- NEVER contain business logic beyond query construction
- NEVER import from app/api/
"""
