# ruff: noqa: S101
"""Unit tests for CacheAdapter.

All tests use the in-memory fallback (backend=None) — no Redis required.
Key-format correctness and invalidation semantics are verified end-to-end
via set/get cycles.
"""

import pytest

from app.infra.cache import CacheAdapter


def make_cache() -> CacheAdapter:
    """Return a fresh in-memory CacheAdapter with a test-scoped prefix."""
    return CacheAdapter(prefix="test")


# ---------------------------------------------------------------------------
# Key name helpers
# ---------------------------------------------------------------------------


def test_batch_list_key_no_status() -> None:
    cache = make_cache()
    assert cache.batch_list_key(None, 100, 0) == "batches:list:all:100:0"


def test_batch_list_key_with_status() -> None:
    cache = make_cache()
    assert cache.batch_list_key("pending", 50, 10) == "batches:list:pending:50:10"


def test_batch_list_key_with_completed_status() -> None:
    cache = make_cache()
    assert cache.batch_list_key("completed", 20, 0) == "batches:list:completed:20:0"


def test_batch_detail_key() -> None:
    cache = make_cache()
    assert cache.batch_detail_key(42) == "batches:detail:42"


def test_batch_detail_key_different_ids_differ() -> None:
    cache = make_cache()
    assert cache.batch_detail_key(1) != cache.batch_detail_key(2)


def test_recent_predictions_key_all() -> None:
    cache = make_cache()
    assert cache.recent_predictions_key(20, False) == "predictions:recent:all:20"


def test_recent_predictions_key_review_only() -> None:
    cache = make_cache()
    assert cache.recent_predictions_key(20, True) == "predictions:recent:review:20"


def test_recent_predictions_key_different_limits_differ() -> None:
    cache = make_cache()
    assert cache.recent_predictions_key(10, False) != cache.recent_predictions_key(20, False)


# ---------------------------------------------------------------------------
# get_json / set_json
# ---------------------------------------------------------------------------


async def test_get_json_returns_none_on_miss() -> None:
    cache = make_cache()
    assert await cache.get_json("no:such:key") is None


async def test_set_json_and_get_json_round_trip() -> None:
    cache = make_cache()
    data = {"items": [1, 2], "total": 2, "limit": 10, "offset": 0}
    await cache.set_json("my:key", data)
    result = await cache.get_json("my:key")
    assert result == data


async def test_set_json_overwrites_existing_value() -> None:
    cache = make_cache()
    await cache.set_json("k", {"v": 1})
    await cache.set_json("k", {"v": 2})
    assert (await cache.get_json("k")) == {"v": 2}


async def test_different_keys_are_independent() -> None:
    cache = make_cache()
    await cache.set_json("key:a", {"x": 1})
    await cache.set_json("key:b", {"x": 2})
    assert (await cache.get_json("key:a")) == {"x": 1}
    assert (await cache.get_json("key:b")) == {"x": 2}


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_removes_key() -> None:
    cache = make_cache()
    await cache.set_json("to:delete", {"x": 1})
    await cache.delete("to:delete")
    assert await cache.get_json("to:delete") is None


async def test_delete_nonexistent_key_does_not_raise() -> None:
    cache = make_cache()
    await cache.delete("ghost:key")


# ---------------------------------------------------------------------------
# delete_prefix
# ---------------------------------------------------------------------------


async def test_delete_prefix_removes_all_matching_keys() -> None:
    cache = make_cache()
    await cache.set_json("batches:list:all:100:0", {"a": 1})
    await cache.set_json("batches:list:pending:100:0", {"b": 2})
    await cache.set_json("batches:detail:1", {"c": 3})

    await cache.delete_prefix("batches:list")

    assert await cache.get_json("batches:list:all:100:0") is None
    assert await cache.get_json("batches:list:pending:100:0") is None


async def test_delete_prefix_leaves_non_matching_keys_intact() -> None:
    cache = make_cache()
    await cache.set_json("batches:list:all:100:0", {"a": 1})
    await cache.set_json("batches:detail:1", {"c": 3})

    await cache.delete_prefix("batches:list")

    assert await cache.get_json("batches:detail:1") is not None


# ---------------------------------------------------------------------------
# Domain-specific invalidation helpers
# ---------------------------------------------------------------------------


async def test_invalidate_batches_clears_all_list_keys() -> None:
    cache = make_cache()
    await cache.set_json(cache.batch_list_key(None, 100, 0), {"items": []})
    await cache.set_json(cache.batch_list_key("pending", 100, 0), {"items": []})

    await cache.invalidate_batches()

    assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None
    assert await cache.get_json(cache.batch_list_key("pending", 100, 0)) is None


async def test_invalidate_batch_clears_only_that_detail_key() -> None:
    cache = make_cache()
    await cache.set_json(cache.batch_detail_key(1), {"id": 1})
    await cache.set_json(cache.batch_detail_key(2), {"id": 2})

    await cache.invalidate_batch(1)

    assert await cache.get_json(cache.batch_detail_key(1)) is None
    assert await cache.get_json(cache.batch_detail_key(2)) is not None


async def test_invalidate_recent_predictions_clears_all_recent_pages() -> None:
    cache = make_cache()
    await cache.set_json(cache.recent_predictions_key(20, False), {"items": []})
    await cache.set_json(cache.recent_predictions_key(20, True), {"items": []})

    await cache.invalidate_recent_predictions()

    assert await cache.get_json(cache.recent_predictions_key(20, False)) is None
    assert await cache.get_json(cache.recent_predictions_key(20, True)) is None


async def test_invalidate_after_prediction_write_clears_all_three_families() -> None:
    cache = make_cache()
    await cache.set_json(cache.batch_list_key(None, 100, 0), {"items": []})
    await cache.set_json(cache.batch_detail_key(5), {"id": 5})
    await cache.set_json(cache.recent_predictions_key(20, False), {"items": []})

    await cache.invalidate_after_prediction_write(batch_id=5)

    assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None
    assert await cache.get_json(cache.batch_detail_key(5)) is None
    assert await cache.get_json(cache.recent_predictions_key(20, False)) is None


async def test_invalidate_after_prediction_write_does_not_clear_other_batch_detail() -> None:
    cache = make_cache()
    await cache.set_json(cache.batch_detail_key(5), {"id": 5})
    await cache.set_json(cache.batch_detail_key(9), {"id": 9})

    await cache.invalidate_after_prediction_write(batch_id=5)

    # Batch 9's detail should survive
    assert await cache.get_json(cache.batch_detail_key(9)) is not None


async def test_invalidate_after_relabel_clears_same_caches_as_prediction_write() -> None:
    """Relabeling should invalidate the same cache families as creating a prediction."""
    cache = make_cache()
    await cache.set_json(cache.batch_list_key(None, 100, 0), {"items": []})
    await cache.set_json(cache.batch_detail_key(3), {"id": 3})
    await cache.set_json(cache.recent_predictions_key(20, False), {"items": []})

    await cache.invalidate_after_relabel(batch_id=3)

    assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None
    assert await cache.get_json(cache.batch_detail_key(3)) is None
    assert await cache.get_json(cache.recent_predictions_key(20, False)) is None


async def test_invalidate_batches_does_not_clear_detail_or_recent() -> None:
    """invalidate_batches targets list keys only."""
    cache = make_cache()
    await cache.set_json(cache.batch_detail_key(10), {"id": 10})
    await cache.set_json(cache.recent_predictions_key(20, False), {"items": []})

    await cache.invalidate_batches()

    assert await cache.get_json(cache.batch_detail_key(10)) is not None
    assert await cache.get_json(cache.recent_predictions_key(20, False)) is not None


async def test_invalidate_user_clears_user_prefixed_keys() -> None:
    cache = make_cache()
    await cache.set_json("user:7:profile", {"role": "admin"})
    await cache.set_json("user:7:other", {"x": 1})
    await cache.set_json("user:8:profile", {"role": "auditor"})

    await cache.invalidate_user(7)

    assert await cache.get_json("user:7:profile") is None
    assert await cache.get_json("user:7:other") is None
    assert await cache.get_json("user:8:profile") is not None
