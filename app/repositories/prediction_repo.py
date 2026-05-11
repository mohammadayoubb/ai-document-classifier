"""Prediction SQL repository — data access only, no business logic."""

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
        # TODO: Phase 6
        ...  # type: ignore[return-value]

    async def get_by_id(self, pred_id: int) -> Prediction | None:
        """Look up a prediction by primary key.

        Args:
            pred_id: The prediction primary key.

        Returns:
            The Prediction ORM instance, or None if not found.
        """
        # TODO: Phase 6
        return None

    async def list_recent(self, limit: int = 20) -> list[Prediction]:
        """Return the most recent prediction rows across all batches.

        Args:
            limit: Maximum rows to return.

        Returns:
            A list of Prediction ORM instances ordered by creation time descending.
        """
        # TODO: Phase 6
        return []

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
        """
        # TODO: Phase 6
        ...  # type: ignore[return-value]

    async def update_overlay_key(self, pred_id: int, overlay_key: str) -> Prediction:
        """Set the MinIO overlay_key after the annotated PNG is generated.

        Args:
            pred_id: The prediction primary key.
            overlay_key: MinIO object key for the annotated PNG in the overlays bucket.

        Returns:
            The updated Prediction ORM instance.
        """
        # TODO: Phase 8
        ...  # type: ignore[return-value]
