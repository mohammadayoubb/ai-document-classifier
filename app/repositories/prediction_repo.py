"""Prediction SQL repository — data access only, no business logic."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction


class PredictionRepository:
    """SQL-only data access for the predictions table.

    Args:
        session: Async database session injected via Depends().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        batch_id: int,
        filename: str,
        storage_key: str,
        predicted_label: str,
        confidence: float,
        top5_labels: str,
        top5_scores: str,
    ) -> Prediction:
        """Insert a new prediction row and return it.

        Args:
            batch_id: Primary key of the owning batch.
            filename: Original filename from the SFTP upload.
            storage_key: MinIO object key for the raw document.
            predicted_label: Top-1 class label from the classifier.
            confidence: Top-1 confidence score.
            top5_labels: JSON array string of the top-5 label names.
            top5_scores: JSON array string of the top-5 confidence scores.

        Returns:
            The newly inserted Prediction ORM instance.
        """
        pred = Prediction(
            batch_id=batch_id,
            filename=filename,
            storage_key=storage_key,
            predicted_label=predicted_label,
            confidence=confidence,
            top5_labels=top5_labels,
            top5_scores=top5_scores,
        )
        self._session.add(pred)
        await self._session.flush()
        await self._session.refresh(pred)
        return pred

    async def get_by_id(self, pred_id: int) -> Prediction | None:
        """Look up a prediction by primary key.

        Args:
            pred_id: The prediction primary key.

        Returns:
            The Prediction ORM instance, or None if not found.
        """
        result = await self._session.execute(
            select(Prediction).where(Prediction.id == pred_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 20) -> list[Prediction]:
        """Return the most recent prediction rows across all batches.

        Args:
            limit: Maximum rows to return.

        Returns:
            A list of Prediction ORM instances ordered by creation time descending.
        """
        result = await self._session.execute(
            select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def relabel(
        self, pred_id: int, new_label: str, relabeled_by: int
    ) -> Prediction:
        """Mark a prediction as relabeled and update its label columns.

        Args:
            pred_id: The prediction primary key.
            new_label: The corrected document class label.
            relabeled_by: Primary key of the reviewer performing the relabel.

        Returns:
            The updated Prediction ORM instance.

        Raises:
            ValueError: If no prediction with pred_id exists.
        """
        result = await self._session.execute(
            select(Prediction).where(Prediction.id == pred_id)
        )
        pred = result.scalar_one_or_none()
        if pred is None:
            raise ValueError(f"Prediction {pred_id} not found")
        pred.is_relabeled = True
        pred.relabeled_to = new_label
        pred.relabeled_by = relabeled_by
        await self._session.flush()
        await self._session.refresh(pred)
        return pred

    async def update_overlay_key(self, pred_id: int, overlay_key: str) -> Prediction:
        """Set the MinIO overlay_key after the annotated PNG is generated.

        Args:
            pred_id: The prediction primary key.
            overlay_key: MinIO object key for the annotated PNG in the overlays bucket.

        Returns:
            The updated Prediction ORM instance.

        Raises:
            ValueError: If no prediction with pred_id exists.
        """
        result = await self._session.execute(
            select(Prediction).where(Prediction.id == pred_id)
        )
        pred = result.scalar_one_or_none()
        if pred is None:
            raise ValueError(f"Prediction {pred_id} not found")
        pred.overlay_key = overlay_key
        await self._session.flush()
        await self._session.refresh(pred)
        return pred
