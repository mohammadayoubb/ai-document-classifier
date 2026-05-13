"""Batch SQL repository — data access only, no business logic."""

from typing import NamedTuple, cast

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, BatchStatus, Prediction


class BatchCounts(NamedTuple):
    """Aggregate prediction counts for one batch."""

    prediction_count: int
    needs_review_count: int


def _coerce_status(status: BatchStatus | str | object) -> BatchStatus:
    """Normalize a domain/string status into the DB enum."""
    value = getattr(status, "value", status)
    if not isinstance(value, str):
        raise TypeError("Batch status must be a string or enum value.")
    return BatchStatus(value)


class BatchRepository:
    """SQL-only data access for the batches table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        owner_id: int,
        status: BatchStatus | str = BatchStatus.pending,
    ) -> Batch:
        """Insert a new batch row and return it."""
        batch = Batch(owner_id=owner_id, status=_coerce_status(status))
        self._session.add(batch)
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def get_by_id(self, batch_id: int) -> Batch | None:
        """Look up a batch by primary key."""
        return cast(Batch | None, await self._session.get(Batch, batch_id))

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        status: BatchStatus | str | None = None,
    ) -> list[Batch]:
        """Return batch rows ordered by creation time descending."""
        stmt = select(Batch).order_by(Batch.created_at.desc(), Batch.id.desc())
        if status is not None:
            stmt = stmt.where(Batch.status == _coerce_status(status))
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self, status: BatchStatus | str | None = None) -> int:
        """Count all batches, optionally filtered by status."""
        stmt = select(func.count(Batch.id))
        if status is not None:
            stmt = stmt.where(Batch.status == _coerce_status(status))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_detail(self, batch_id: int) -> tuple[Batch, list[Prediction]] | None:
        """Return one batch and its prediction rows without relying on lazy loading."""
        batch = await self.get_by_id(batch_id)
        if batch is None:
            return None

        stmt = (
            select(Prediction)
            .where(Prediction.batch_id == batch_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
        )
        result = await self._session.execute(stmt)
        return batch, list(result.scalars().all())

    async def count_predictions_by_batch(
        self,
        batch_ids: list[int],
        low_confidence_threshold: float,
    ) -> dict[int, BatchCounts]:
        """Return prediction and review-needed counts grouped by batch."""
        if not batch_ids:
            return {}

        review_case = case(
            (
                (Prediction.confidence < low_confidence_threshold)
                & (Prediction.is_relabeled.is_(False)),
                1,
            ),
            else_=0,
        )
        stmt = (
            select(
                Prediction.batch_id,
                func.count(Prediction.id),
                func.coalesce(func.sum(review_case), 0),
            )
            .where(Prediction.batch_id.in_(batch_ids))
            .group_by(Prediction.batch_id)
        )
        result = await self._session.execute(stmt)
        return {
            int(batch_id): BatchCounts(
                prediction_count=int(prediction_count),
                needs_review_count=int(needs_review_count),
            )
            for batch_id, prediction_count, needs_review_count in result.all()
        }

    async def update_status(
        self,
        batch_id: int,
        status: BatchStatus | str | object,
    ) -> Batch | None:
        """Update the status column of a batch row."""
        batch = await self.get_by_id(batch_id)
        if batch is None:
            return None

        batch.status = _coerce_status(status)
        await self._session.flush()
        await self._session.refresh(batch)
        return batch
