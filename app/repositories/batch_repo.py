"""Batch SQL repository — data access only, no business logic."""

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
        # TODO: Phase 6
        ...  # type: ignore[return-value]

    async def get_by_id(self, batch_id: int) -> Batch | None:
        """Look up a batch by primary key.

        Args:
            batch_id: The batch primary key.

        Returns:
            The Batch ORM instance, or None if not found.
        """
        # TODO: Phase 6
        return None

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Batch]:
        """Return all batch rows ordered by creation time descending.

        Args:
            limit: Maximum rows to return.
            offset: Rows to skip before returning results.

        Returns:
            A list of Batch ORM instances.
        """
        # TODO: Phase 6
        return []

    async def update_status(self, batch_id: int, status: BatchStatus) -> Batch:
        """Update the status column of a batch row.

        Args:
            batch_id: The batch primary key.
            status: The new BatchStatus enum value.

        Returns:
            The updated Batch ORM instance.
        """
        # TODO: Phase 6
        ...  # type: ignore[return-value]
