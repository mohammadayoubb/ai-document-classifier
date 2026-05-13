"""Cache adapter used by services for read-through caching and invalidation."""

from __future__ import annotations

import inspect
import json
from typing import Any


class CacheAdapter:
    """JSON cache wrapper with a Redis-compatible backend and memory fallback."""

    def __init__(self, backend: Any | None = None, prefix: str = "docclassifier") -> None:
        self._backend = backend
        self._prefix = prefix.rstrip(":")
        self._memory: dict[str, str] = {}

    def batch_list_key(
        self,
        status: str | None,
        limit: int,
        offset: int,
    ) -> str:
        """Return the canonical key for a batch list page."""
        status_key = status or "all"
        return f"batches:list:{status_key}:{limit}:{offset}"

    def batch_detail_key(self, batch_id: int) -> str:
        """Return the canonical key for one batch detail response."""
        return f"batches:detail:{batch_id}"

    def recent_predictions_key(self, limit: int, only_needs_review: bool) -> str:
        """Return the canonical key for recent predictions."""
        review_key = "review" if only_needs_review else "all"
        return f"predictions:recent:{review_key}:{limit}"

    async def get_json(self, key: str) -> Any | None:
        """Fetch and JSON-decode a cache value."""
        raw = await self._get_raw(self._key(key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return raw
        return json.loads(raw)

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """JSON-encode and store a cache value."""
        payload = json.dumps(value)
        await self._set_raw(self._key(key), payload, ttl_seconds)

    async def delete(self, key: str) -> None:
        """Delete one cache key."""
        await self._delete_raw(self._key(key))

    async def delete_prefix(self, prefix: str) -> None:
        """Delete all keys beginning with a logical prefix."""
        full_prefix = self._key(prefix)
        if self._backend is None:
            for key in list(self._memory):
                if key.startswith(full_prefix):
                    self._memory.pop(key, None)
            return

        if hasattr(self._backend, "scan_iter"):
            keys = []
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
            keys = await self._maybe_await(self._backend.keys(f"{full_prefix}*"))
            for key in keys:
                await self._delete_raw(key)

    async def invalidate_user(self, user_id: int) -> None:
        """Invalidate cached user data for a role/status change."""
        await self.delete_prefix(f"user:{user_id}")

    async def invalidate_batches(self) -> None:
        """Invalidate cached batch lists."""
        await self.delete_prefix("batches:list")

    async def invalidate_batch(self, batch_id: int) -> None:
        """Invalidate one batch detail cache."""
        await self.delete(self.batch_detail_key(batch_id))

    async def invalidate_recent_predictions(self) -> None:
        """Invalidate recent prediction cache pages."""
        await self.delete_prefix("predictions:recent")

    async def invalidate_after_prediction_write(self, batch_id: int) -> None:
        """Invalidate all caches affected by creating/updating a prediction."""
        await self.invalidate_recent_predictions()
        await self.invalidate_batches()
        await self.invalidate_batch(batch_id)

    async def invalidate_after_relabel(self, batch_id: int) -> None:
        """Invalidate all caches affected by relabeling a prediction."""
        await self.invalidate_after_prediction_write(batch_id)

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key.lstrip(':')}"

    async def _get_raw(self, key: str) -> Any | None:
        if self._backend is None:
            return self._memory.get(key)
        return await self._maybe_await(self._backend.get(key))

    async def _set_raw(self, key: str, value: str, ttl_seconds: int | None) -> None:
        if self._backend is None:
            self._memory[key] = value
            return

        try:
            result = self._backend.set(key, value, ex=ttl_seconds)
        except TypeError:
            result = self._backend.set(key, value)
        await self._maybe_await(result)

    async def _delete_raw(self, key: str | bytes) -> None:
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        if self._backend is None:
            self._memory.pop(key, None)
            return
        await self._maybe_await(self._backend.delete(key))

    async def _maybe_await(self, result: Any) -> Any:
        if inspect.isawaitable(result):
            return await result
        return result
