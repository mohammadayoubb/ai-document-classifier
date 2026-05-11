"""Redis cache invalidation adapter for fastapi-cache2.

Invalidation is the exclusive responsibility of the service layer.
Routes and repositories must never call these methods directly.
"""

import structlog
from fastapi_cache import FastAPICache

log = structlog.get_logger()


class CacheAdapter:
    """Thin wrapper for cache namespace management and targeted invalidation.

    Each method maps to a specific endpoint's cache namespace.
    TTLs are set at the route level via @cache(expire=...).
    """

    async def invalidate_user(self, user_id: int) -> None:
        """Invalidate the /users/me cache for a specific user.

        Called after a role change so the next request reflects the updated
        role without requiring re-login.

        Args:
            user_id: Primary key of the user whose cache entry should be cleared.
        """
        await FastAPICache.clear(namespace=f"user:{user_id}")

    async def invalidate_batches(self) -> None:
        """Invalidate the /batches list cache.

        Called after any batch creation or status change.
        """
        await FastAPICache.clear(namespace="batches")

    async def invalidate_batch(self, batch_id: int) -> None:
        """Invalidate the cache for a specific /batches/{batch_id} entry.

        Args:
            batch_id: Primary key of the batch whose cache entry should be cleared.
        """
        await FastAPICache.clear(namespace=f"batch:{batch_id}")

    async def invalidate_recent_predictions(self) -> None:
        """Invalidate the /predictions/recent cache.

        Called after any new prediction is written to the database.
        """
        await FastAPICache.clear(namespace="predictions:recent")
