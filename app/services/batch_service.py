"""Batch business logic — creation, listing, detail, and cache invalidation."""

from typing import Any, cast

from app.config import Settings, get_settings
from app.domain.batch import BatchDetail, BatchDomain, BatchStatus, PaginatedBatchSummary
from app.services.mappers import batch_to_domain, batch_to_summary, prediction_to_read


class BatchService:
    """Orchestrates batch lifecycle and cache behavior."""

    def __init__(
        self,
        repo: Any,
        cache: Any,
        settings: Settings | None = None,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._settings = settings or get_settings()

    async def create_batch(self, owner_id: int) -> BatchDomain:
        """Create a new pending batch and invalidate cached batch lists."""
        batch = await self._repo.create(owner_id=owner_id, status=BatchStatus.pending)
        await self._cache.invalidate_batches()
        return batch_to_domain(batch)

    async def list_batches(
        self,
        limit: int = 100,
        offset: int = 0,
        status: BatchStatus | str | None = None,
    ) -> PaginatedBatchSummary:
        """Return a cached paginated batch summary page."""
        limit = _normalize_limit(limit)
        offset = max(offset, 0)
        status_key = _status_value(status)
        cache_key = self._cache.batch_list_key(status_key, limit, offset)

        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cast(PaginatedBatchSummary, PaginatedBatchSummary.model_validate(cached))

        batches = await self._repo.list_all(limit=limit, offset=offset, status=status)
        total = await self._repo.count_all(status=status)
        batch_ids = [batch.id for batch in batches]
        counts = await self._repo.count_predictions_by_batch(
            batch_ids,
            self._settings.low_confidence_threshold,
        )
        items = [
            batch_to_summary(
                batch,
                prediction_count=getattr(counts.get(batch.id), "prediction_count", 0),
                needs_review_count=getattr(counts.get(batch.id), "needs_review_count", 0),
            )
            for batch in batches
        ]
        response = PaginatedBatchSummary(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )
        await self._cache.set_json(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=self._settings.cache_ttl_batches,
        )
        return response

    async def list_all(self, limit: int = 100, offset: int = 0) -> PaginatedBatchSummary:
        """Compatibility wrapper for the scaffolded service method."""
        return await self.list_batches(limit=limit, offset=offset)

    async def get_batch_detail(self, batch_id: int) -> BatchDetail | None:
        """Return one cached batch detail with decoded prediction rows."""
        cache_key = self._cache.batch_detail_key(batch_id)
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cast(BatchDetail, BatchDetail.model_validate(cached))

        detail = await self._repo.get_detail(batch_id)
        if detail is None:
            return None

        batch, predictions = detail
        prediction_reads = [
            prediction_to_read(prediction, self._settings.low_confidence_threshold)
            for prediction in predictions
        ]
        summary = batch_to_summary(
            batch,
            prediction_count=len(prediction_reads),
            needs_review_count=sum(1 for prediction in prediction_reads if prediction.needs_review),
        )
        response = BatchDetail(
            **summary.model_dump(),
            predictions=prediction_reads,
        )
        await self._cache.set_json(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=self._settings.cache_ttl_batch,
        )
        return response

    async def get_by_id(self, batch_id: int) -> BatchDetail | None:
        """Compatibility wrapper for the scaffolded service method."""
        return await self.get_batch_detail(batch_id)

    async def update_status(self, batch_id: int, status: BatchStatus | str) -> BatchDomain:
        """Update a batch status and invalidate affected caches."""
        updated = await self._repo.update_status(batch_id, status)
        if updated is None:
            raise LookupError(f"Batch {batch_id} was not found.")

        await self._cache.invalidate_batches()
        await self._cache.invalidate_batch(batch_id)
        return batch_to_domain(updated)


def _normalize_limit(limit: int) -> int:
    return min(max(limit, 1), 500)


def _status_value(status: BatchStatus | str | None) -> str | None:
    if status is None:
        return None
    return str(getattr(status, "value", status))
