"""Prediction SQL repository — owns only database reads/writes for predictions.

This file deliberately contains no review rules, cache invalidation, or audit
logic. Those decisions live in services.
"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction


class PredictionRepository:
    """SQL-only data access for the predictions table."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the SQLAlchemy session used by prediction queries.

        Args:
            session: Async SQLAlchemy session owned by the caller.
        """
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
        overlay_key: str | None = None,
    ) -> Prediction:
        """Insert a new prediction row and return it.

        Args:
            batch_id: Parent batch id.
            filename: Original uploaded filename.
            storage_key: MinIO object key for the source document.
            predicted_label: Top-1 classifier label.
            confidence: Top-1 confidence score.
            top5_labels: JSON string containing top-5 labels.
            top5_scores: JSON string containing top-5 scores.
            overlay_key: Optional MinIO key for the generated overlay PNG.

        Returns:
            The newly created Prediction ORM object.
        """
        prediction = Prediction(
            batch_id=batch_id,
            filename=filename,
            storage_key=storage_key,
            overlay_key=overlay_key,
            predicted_label=predicted_label,
            confidence=confidence,
            top5_labels=top5_labels,
            top5_scores=top5_scores,
        )

        # DB WRITE: stage prediction row created by the worker/service layer.
        self._session.add(prediction)

        # DB CALL: flush/refresh exposes id and timestamps to services.
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction

    async def get_by_id(self, pred_id: int) -> Prediction | None:
        """Look up a prediction by primary key.

        Args:
            pred_id: Prediction primary key.

        Returns:
            Prediction ORM object, or None when it does not exist.
        """
        # DB CALL: direct primary-key lookup through SQLAlchemy session.
        return cast(Prediction | None, await self._session.get(Prediction, pred_id))

    async def list_recent(
        self,
        limit: int = 20,
        only_needs_review: bool = False,
        low_confidence_threshold: float = 0.7,
    ) -> list[Prediction]:
        """Return the most recent prediction rows across all batches.

        Args:
            limit: Maximum number of predictions to return.
            only_needs_review: Whether to restrict rows to low-confidence items.
            low_confidence_threshold: Confidence cutoff for review-needed rows.

        Returns:
            Prediction ORM rows ordered newest first.
        """
        stmt = select(Prediction).order_by(Prediction.created_at.desc(), Prediction.id.desc())
        if only_needs_review:
            stmt = stmt.where(
                Prediction.confidence < low_confidence_threshold,
                Prediction.is_relabeled.is_(False),
            )
        stmt = stmt.limit(limit)

        # DB CALL: execute recent prediction query for dashboard/review views.
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_batch(self, batch_id: int) -> list[Prediction]:
        """Return predictions for one batch ordered by newest first.

        Args:
            batch_id: Parent batch id.

        Returns:
            Prediction ORM rows belonging to the batch.
        """
        stmt = (
            select(Prediction)
            .where(Prediction.batch_id == batch_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
        )

        # DB CALL: load all predictions for one batch detail view.
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def relabel(
        self,
        pred_id: int,
        new_label: str,
        relabeled_by: int,
    ) -> Prediction | None:
        """Mark a prediction as relabeled and update reviewer columns.

        Args:
            pred_id: Prediction primary key.
            new_label: Human-confirmed or corrected label.
            relabeled_by: User id of the reviewer/admin applying the label.

        Returns:
            Updated Prediction ORM object, or None if not found.
        """
        # DB CALL: load row before mutating reviewer fields.
        prediction = await self.get_by_id(pred_id)
        if prediction is None:
            return None

        prediction.is_relabeled = True
        prediction.relabeled_to = new_label
        prediction.relabeled_by = relabeled_by

        # DB CALL: persist relabel fields and refresh the ORM object.
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction

    async def update_overlay_key(
        self,
        pred_id: int,
        overlay_key: str,
    ) -> Prediction | None:
        """Set the MinIO overlay_key after the annotated PNG is generated.

        Args:
            pred_id: Prediction primary key.
            overlay_key: MinIO object key for the overlay PNG.

        Returns:
            Updated Prediction ORM object, or None if not found.
        """
        # DB CALL: load row before mutating overlay metadata.
        prediction = await self.get_by_id(pred_id)
        if prediction is None:
            return None

        prediction.overlay_key = overlay_key

        # DB CALL: persist overlay key and refresh the ORM object.
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction
