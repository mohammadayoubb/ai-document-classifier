"""Batch SQL repository — owns only database reads/writes for batches.

Repositories are the lowest application layer. They build SQLAlchemy statements,
execute them with the injected session, and return ORM objects to services.
"""

from typing import NamedTuple, cast

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, BatchStatus, Prediction


class BatchCounts(NamedTuple):
    """Aggregate prediction counts for one batch."""

    prediction_count: int
    needs_review_count: int


def _coerce_status(status: BatchStatus | str | object) -> BatchStatus:
    """Normalize a domain/string status into the database enum.

    Args:
        status: Domain enum, database enum, or raw string status value.

    Returns:
        A BatchStatus enum instance suitable for SQLAlchemy assignment/filtering.

    Raises:
        TypeError: If the provided value cannot be interpreted as a string.
        ValueError: If the string is not a valid BatchStatus value.
    """
    value = getattr(status, "value", status)
    if not isinstance(value, str):
        raise TypeError("Batch status must be a string or enum value.")
    return BatchStatus(value)


class BatchRepository:
    """SQL-only data access for the batches table."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLAlchemy session used by all repository methods.

        Args:
            session: Async SQLAlchemy session owned by the caller.
        """
        self._session = session

    async def create(
        self,
        owner_id: int,
        status: BatchStatus | str = BatchStatus.pending,
    ) -> Batch:
        """Insert a new batch row and return it.

        Args:
            owner_id: User id that owns this batch.
            status: Initial lifecycle status for the batch.

        Returns:
            The newly created Batch ORM object with generated fields populated.
        """
        batch = Batch(owner_id=owner_id, status=_coerce_status(status))

        # DB WRITE: stage the new batch row in the current transaction.
        self._session.add(batch)

        # DB CALL: flush/refresh exposes generated id and timestamps to services.
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def get_by_id(self, batch_id: int) -> Batch | None:
        """Look up a batch by primary key.

        Args:
            batch_id: Batch primary key.

        Returns:
            The Batch ORM object, or None when it does not exist.
        """
        # DB CALL: direct primary-key lookup through SQLAlchemy session.
        return cast(Batch | None, await self._session.get(Batch, batch_id))

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        status: BatchStatus | str | None = None,
    ) -> list[Batch]:
        """Return batch rows ordered by creation time descending.

        Args:
            limit: Maximum number of batch rows to return.
            offset: Number of rows to skip for pagination.
            status: Optional lifecycle status filter.

        Returns:
            A list of Batch ORM rows.
        """
        stmt = select(Batch).order_by(Batch.created_at.desc(), Batch.id.desc())
        if status is not None:
            stmt = stmt.where(Batch.status == _coerce_status(status))
        stmt = stmt.limit(limit).offset(offset)

        # DB CALL: execute the list query with optional status filtering.
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self, status: BatchStatus | str | None = None) -> int:
        """Count all batches, optionally filtered by status.

        Args:
            status: Optional lifecycle status filter.

        Returns:
            Total number of matching batch rows.
        """
        stmt = select(func.count(Batch.id))
        if status is not None:
            stmt = stmt.where(Batch.status == _coerce_status(status))

        # DB CALL: count matching batches for pagination metadata.
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def get_detail(self, batch_id: int) -> tuple[Batch, list[Prediction]] | None:
        """Return one batch and its prediction rows without relying on lazy loading.

        Args:
            batch_id: Batch primary key.

        Returns:
            A tuple of the Batch ORM object and its Prediction rows, or None.
        """
        # DB CALL: reuse the primary-key lookup before loading child rows.
        batch = await self.get_by_id(batch_id)
        if batch is None:
            return None

        stmt = (
            select(Prediction)
            .where(Prediction.batch_id == batch_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
        )

        # DB CALL: explicitly load predictions to avoid implicit lazy IO.
        result = await self._session.execute(stmt)
        return batch, list(result.scalars().all())

    async def count_predictions_by_batch(
        self,
        batch_ids: list[int],
        low_confidence_threshold: float,
    ) -> dict[int, BatchCounts]:
        """Return prediction and review-needed counts grouped by batch.

        Args:
            batch_ids: Batch ids to aggregate.
            low_confidence_threshold: Confidence below which a prediction needs review.

        Returns:
            Mapping from batch id to prediction/review-needed counts.
        """
        if not batch_ids:
            return {}

        # DB EXPRESSION: count only low-confidence, not-yet-relabeled rows as review-needed.
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

        # DB CALL: aggregate counts for all visible batches in one query.
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
        """Update the status column of a batch row.

        Args:
            batch_id: Batch primary key.
            status: New lifecycle status.

        Returns:
            Updated Batch ORM object, or None if the batch does not exist.
        """
        # DB CALL: load the row before mutating it inside the current transaction.
        batch = await self.get_by_id(batch_id)
        if batch is None:
            return None

        batch.status = _coerce_status(status)

        # DB CALL: persist the mutation and refresh generated/update columns.
        await self._session.flush()
        await self._session.refresh(batch)
        return batch
