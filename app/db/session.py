"""Async database engine and session factory.

The engine and SessionLocal are module-level singletons — created once at
import time using the DATABASE_URL env var.  Tests must set DATABASE_URL
(e.g. via a conftest.py fixture) before importing this module.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for use as a FastAPI Depends() dependency.

    Commits on normal exit, rolls back on exception, and always closes.
    Never call session.close() manually in a route — this generator handles it.

    Yields:
        An AsyncSession bound to the application's connection pool.
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
