"""Batch SQL repository — data access only, no business logic."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch, BatchStatus


class BatchRepository:
    """SQL-only data access for the batches table.

    Args:
        session: Async database session injected via Depends().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, owner_id: int) -> Batch:
        """Insert a new pending batch row and return it.

        Args:
            owner_id: Primary key of the owning user.

        Returns:
            The newly inserted Batch ORM instance.
        """
        batch = Batch(owner_id=owner_id, status=BatchStatus.pending)
        self._session.add(batch)
        await self._session.flush()
        await self._session.refresh(batch)
        return batch

    async def get_by_id(self, batch_id: int) -> Batch | None:
        """Look up a batch by primary key.

        Args:
            batch_id: The batch primary key.

        Returns:
            The Batch ORM instance, or None if not found.
        """
        result = await self._session.execute(select(Batch).where(Batch.id == batch_id))
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Batch]:
        """Return all batch rows ordered by creation time descending.

        Args:
            limit: Maximum rows to return.
            offset: Rows to skip before returning results.

        Returns:
            A list of Batch ORM instances.
        """
        result = await self._session.execute(
            select(Batch).order_by(Batch.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def update_status(self, batch_id: int, status: BatchStatus) -> Batch:
        """Update the status column of a batch row.

        Args:
            batch_id: The batch primary key.
            status: The new BatchStatus enum value.

        Returns:
            The updated Batch ORM instance.

        Raises:
            ValueError: If no batch with batch_id exists.
        """
        result = await self._session.execute(select(Batch).where(Batch.id == batch_id))
        batch = result.scalar_one_or_none()
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found")
        batch.status = status
        await self._session.flush()
        await self._session.refresh(batch)
        return batch
