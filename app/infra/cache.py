"""Cache adapter — centralizes service-layer read-through caching.

The project uses this adapter as the cache boundary. It works with Redis-like
backends and a memory fallback for tests, while services decide what to cache.
"""

from __future__ import annotations

import inspect
import json
from typing import Any


class CacheAdapter:
    """JSON cache wrapper with a Redis-compatible backend and memory fallback."""

    def __init__(self, backend: Any | None = None, prefix: str = "docclassifier") -> None:
        """Create a cache adapter.

        Args:
            backend: Redis-compatible backend, or None for in-memory fallback.
            prefix: Prefix added to every physical cache key.
        """
        self._backend = backend
        self._prefix = prefix.rstrip(":")
        self._memory: dict[str, str] = {}

    def batch_list_key(
        self,
        status: str | None,
        limit: int,
        offset: int,
    ) -> str:
        """Return the canonical key for a batch list page.

        Args:
            status: Optional batch status filter.
            limit: Page size.
            offset: Page offset.

        Returns:
            Logical cache key for the batch list response.
        """
        status_key = status or "all"
        return f"batches:list:{status_key}:{limit}:{offset}"

    def batch_detail_key(self, batch_id: int) -> str:
        """Return the canonical key for one batch detail response.

        Args:
            batch_id: Batch primary key.

        Returns:
            Logical cache key for the batch detail response.
        """
        return f"batches:detail:{batch_id}"

    def recent_predictions_key(self, limit: int, only_needs_review: bool) -> str:
        """Return the canonical key for recent predictions.

        Args:
            limit: Maximum recent predictions included.
            only_needs_review: Whether the page filters to review-needed rows.

        Returns:
            Logical cache key for recent prediction responses.
        """
        review_key = "review" if only_needs_review else "all"
        return f"predictions:recent:{review_key}:{limit}"

    async def get_json(self, key: str) -> Any | None:
        """Fetch and JSON-decode a cache value.

        Args:
            key: Logical cache key without the adapter prefix.

        Returns:
            Decoded JSON value, raw backend value, or None on cache miss.
        """
        # CACHE READ: resolve logical key into the prefixed backend key.
        raw = await self._get_raw(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return raw
        return json.loads(raw)

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """JSON-encode and store a cache value.

        Args:
            key: Logical cache key without the adapter prefix.
            value: JSON-serializable payload to cache.
            ttl_seconds: Optional expiration time.
        """
        payload = json.dumps(value)

        # CACHE WRITE: store serialized payload using the prefixed backend key.
        await self._set_raw(self._key(key), payload, ttl_seconds)

    async def delete(self, key: str) -> None:
        """Delete one cache key.

        Args:
            key: Logical cache key without the adapter prefix.
        """
        # CACHE DELETE: remove one precise response key.
        await self._delete_raw(self._key(key))

    async def delete_prefix(self, prefix: str) -> None:
        """Delete all keys beginning with a logical prefix.

        Args:
            prefix: Logical key prefix to remove.
        """
        full_prefix = self._key(prefix)
        if self._backend is None:
            # CACHE DELETE: memory fallback prefix scan for unit tests.
            for key in list(self._memory):
                if key.startswith(full_prefix):
                    self._memory.pop(key, None)
            return

        if hasattr(self._backend, "scan_iter"):
            keys = []
            # CACHE SCAN: Redis scan_iter avoids blocking Redis with KEYS.
            result = self._backend.scan_iter(f"{full_prefix}*")
            if inspect.isasyncgen(result):
                async for key in result:
                    keys.append(key)
            else:
                keys.extend(result)
            for key in keys:
                await self._delete_raw(key)
            return

        if hasattr(self._backend, "keys"):
            # CACHE SCAN: compatibility fallback for simple fake Redis clients.
            keys = await self._maybe_await(self._backend.keys(f"{full_prefix}*"))
            for key in keys:
                await self._delete_raw(key)

    async def invalidate_user(self, user_id: int) -> None:
        """Invalidate cached user data for a role/status change.

        Args:
            user_id: User id whose cached responses are stale.
        """
        await self.delete_prefix(f"user:{user_id}")

    async def invalidate_batches(self) -> None:
        """Invalidate cached batch lists.

        Batch list pages include status and aggregate counts, so any batch or
        prediction write can make them stale.
        """
        await self.delete_prefix("batches:list")

    async def invalidate_batch(self, batch_id: int) -> None:
        """Invalidate one batch detail cache.

        Args:
            batch_id: Batch whose detail response is stale.
        """
        await self.delete(self.batch_detail_key(batch_id))

    async def invalidate_recent_predictions(self) -> None:
        """Invalidate recent prediction cache pages.

        Recent prediction pages change when worker writes or relabels happen.
        """
        await self.delete_prefix("predictions:recent")

    async def invalidate_after_prediction_write(self, batch_id: int) -> None:
        """Invalidate all caches affected by creating/updating a prediction.

        Args:
            batch_id: Batch containing the changed prediction.
        """
        await self.invalidate_recent_predictions()
        await self.invalidate_batches()
        await self.invalidate_batch(batch_id)

    async def invalidate_after_relabel(self, batch_id: int) -> None:
        """Invalidate all caches affected by relabeling a prediction.

        Args:
            batch_id: Batch containing the relabeled prediction.
        """
        await self.invalidate_after_prediction_write(batch_id)

    def _key(self, key: str) -> str:
        """Return the physical backend key for a logical cache key.

        Args:
            key: Logical cache key.

        Returns:
            Prefix-qualified cache key.
        """
        return f"{self._prefix}:{key.lstrip(':')}"

    async def _get_raw(self, key: str) -> Any | None:
        """Fetch a raw backend value.

        Args:
            key: Physical backend cache key.

        Returns:
            Raw cached value, or None.
        """
        if self._backend is None:
            return self._memory.get(key)
        return await self._maybe_await(self._backend.get(key))

    async def _set_raw(self, key: str, value: str, ttl_seconds: int | None) -> None:
        """Store a raw backend value.

        Args:
            key: Physical backend cache key.
            value: Serialized value.
            ttl_seconds: Optional expiration time.
        """
        if self._backend is None:
            self._memory[key] = value
            return

        try:
            result = self._backend.set(key, value, ex=ttl_seconds)
        except TypeError:
            result = self._backend.set(key, value)
        await self._maybe_await(result)

    async def _delete_raw(self, key: str | bytes) -> None:
        """Delete a raw backend key.

        Args:
            key: Physical backend cache key, possibly returned as bytes by Redis.
        """
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if self._backend is None:
            self._memory.pop(key, None)
            return
        await self._maybe_await(self._backend.delete(key))

    async def _maybe_await(self, result: Any) -> Any:
        """Await a result only when the backend API is asynchronous.

        Args:
            result: Sync value or awaitable returned by the cache backend.

        Returns:
            The resolved result.
        """
        if inspect.isawaitable(result):
            return await result
        return result
