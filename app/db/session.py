"""Async database engine and session factory.

The engine is created lazily so startup can resolve Vault-backed secrets before
SQLAlchemy builds a database URL. Tests can inject a URL with init_engine().
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the process-wide async engine on first use and return it."""
    global _engine, _session_factory

    if _engine is not None:
        return _engine

    url = database_url or get_settings().build_database_url()
    _engine = create_async_engine(url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    """Return the configured async engine, initializing it if necessary."""
    return init_engine()


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the configured async sessionmaker, initializing it if necessary."""
    if _session_factory is None:
        init_engine()
    if _session_factory is None:
        raise RuntimeError("Database session factory was not initialized.")
    return _session_factory


async def dispose_engine() -> None:
    """Dispose the current engine and reset the cached factory."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def SessionLocal() -> AsyncSession:
    """Return a new async session for use by worker code (not FastAPI routes).

    Workers call ``async with SessionLocal() as session:`` instead of using
    FastAPI's Depends(get_session) because they run outside the request cycle.
    """
    return get_sessionmaker()()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for use as a FastAPI Depends() dependency.

    Commits on normal exit, rolls back on exception, and always closes.
    Never call session.close() manually in a route — this generator handles it.

    Yields:
        An AsyncSession bound to the application's connection pool.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
