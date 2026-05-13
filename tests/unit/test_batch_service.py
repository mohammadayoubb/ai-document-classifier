# ruff: noqa: S101, S106
import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.domain.batch import BatchStatus, PaginatedBatchSummary
from app.infra.cache import CacheAdapter
from app.services.batch_service import BatchService

NOW = datetime(2026, 5, 12, tzinfo=UTC)


def make_settings() -> Settings:
    return Settings(
        vault_root_token="root",
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/test",
        low_confidence_threshold=0.7,
        cache_ttl_batches=60,
        cache_ttl_batch=30,
    )


def make_batch(batch_id: int = 1, status: str = "pending") -> SimpleNamespace:
    return SimpleNamespace(
        id=batch_id,
        owner_id=10,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def make_prediction(
    prediction_id: int = 1,
    confidence: float = 0.4,
    is_relabeled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=prediction_id,
        batch_id=1,
        filename="invoice.pdf",
        storage_key="raw/invoice.pdf",
        overlay_key=None,
        predicted_label="invoice",
        confidence=confidence,
        top5_labels=json.dumps(["invoice", "form"]),
        top5_scores=json.dumps([confidence, 1 - confidence]),
        is_relabeled=is_relabeled,
        relabeled_to=None,
        relabeled_by=None,
        created_at=NOW,
    )


class FakeBatchRepo:
    def __init__(self) -> None:
        self.batches = [make_batch()]
        self.detail = (self.batches[0], [make_prediction()])
        self.counts = {1: SimpleNamespace(prediction_count=1, needs_review_count=1)}
        self.list_calls = 0
        self.detail_calls = 0
        self.updated_status: object | None = None

    async def create(self, owner_id: int, status: BatchStatus) -> SimpleNamespace:
        return make_batch(batch_id=2, status=status.value)

    async def list_all(
        self,
        limit: int,
        offset: int,
        status: BatchStatus | str | None = None,
    ) -> list[SimpleNamespace]:
        self.list_calls += 1
        return self.batches

    async def count_all(self, status: BatchStatus | str | None = None) -> int:
        return len(self.batches)

    async def count_predictions_by_batch(
        self,
        batch_ids: list[int],
        low_confidence_threshold: float,
    ) -> dict[int, SimpleNamespace]:
        return self.counts

    async def get_detail(self, batch_id: int) -> tuple[SimpleNamespace, list[SimpleNamespace]]:
        self.detail_calls += 1
        return self.detail

    async def update_status(self, batch_id: int, status: BatchStatus | str) -> SimpleNamespace:
        self.updated_status = status
        return make_batch(batch_id=batch_id, status=getattr(status, "value", status))


def test_list_batches_reads_from_cache_when_present() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())
        key = cache.batch_list_key(None, 100, 0)
        cached = PaginatedBatchSummary(
            items=[],
            total=0,
            limit=100,
            offset=0,
        )
        await cache.set_json(key, cached.model_dump(mode="json"))

        result = await service.list_batches()

        assert result.total == 0
        assert repo.list_calls == 0

    asyncio.run(exercise())


def test_list_batches_queries_repo_and_sets_cache_on_miss() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())

        result = await service.list_batches()

        assert repo.list_calls == 1
        assert result.items[0].prediction_count == 1
        assert result.items[0].needs_review_count == 1
        assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is not None

    asyncio.run(exercise())


def test_batch_detail_reads_and_writes_cache() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())

        first = await service.get_batch_detail(1)
        second = await service.get_batch_detail(1)

        assert repo.detail_calls == 1
        assert first is not None
        assert second is not None
        assert first.predictions[0].needs_review is True
        assert second.prediction_count == 1

    asyncio.run(exercise())


def test_status_update_invalidates_list_and_detail_caches() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())
        await cache.set_json(
            cache.batch_list_key(None, 100, 0),
            {"items": [], "total": 0, "limit": 100, "offset": 0},
        )
        await cache.set_json(cache.batch_detail_key(1), {"cached": True})

        updated = await service.update_status(1, BatchStatus.completed)

        assert updated.status == BatchStatus.completed
        assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None
        assert await cache.get_json(cache.batch_detail_key(1)) is None

    asyncio.run(exercise())


def test_create_batch_returns_domain_and_invalidates_list_cache() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())
        await cache.set_json(
            cache.batch_list_key(None, 100, 0),
            {"items": [], "total": 0, "limit": 100, "offset": 0},
        )

        result = await service.create_batch(owner_id=1)

        assert result.id == 2
        assert result.status == BatchStatus.pending
        assert await cache.get_json(cache.batch_list_key(None, 100, 0)) is None

    asyncio.run(exercise())


def test_list_batches_clamps_limit_above_500() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())

        result = await service.list_batches(limit=9999)

        assert result.limit == 500

    asyncio.run(exercise())


def test_list_batches_clamps_limit_below_one_to_one() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())

        result = await service.list_batches(limit=0)

        assert result.limit == 1

    asyncio.run(exercise())


def test_list_batches_normalizes_negative_offset_to_zero() -> None:
    async def exercise() -> None:
        repo = FakeBatchRepo()
        cache = CacheAdapter(prefix="test")
        service = BatchService(repo, cache, settings=make_settings())

        result = await service.list_batches(limit=10, offset=-10)

        assert result.offset == 0

    asyncio.run(exercise())


def test_update_status_raises_lookup_error_when_batch_not_found() -> None:
    class MissingBatchRepo(FakeBatchRepo):
        async def update_status(  # type: ignore[override]
            self,
            batch_id: int,
            status: object,
        ) -> None:
            return None

    async def exercise() -> None:
        service = BatchService(
            MissingBatchRepo(),
            CacheAdapter(prefix="test"),
            settings=make_settings(),
        )

        with pytest.raises(LookupError, match="not found"):
            await service.update_status(999, BatchStatus.completed)

    asyncio.run(exercise())


def test_get_batch_detail_returns_none_when_batch_not_found() -> None:
    class EmptyRepo(FakeBatchRepo):
        async def get_detail(  # type: ignore[override]
            self,
            batch_id: int,
        ) -> None:
            return None

    async def exercise() -> None:
        service = BatchService(
            EmptyRepo(),
            CacheAdapter(prefix="test"),
            settings=make_settings(),
        )

        result = await service.get_batch_detail(9999)

        assert result is None

    asyncio.run(exercise())
