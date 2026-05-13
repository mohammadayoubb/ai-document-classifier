"""Prediction SQL repository — data access only, no business logic."""

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction


class PredictionRepository:
    """SQL-only data access for the predictions table."""

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
        overlay_key: str | None = None,
    ) -> Prediction:
        """Insert a new prediction row and return it."""
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
        self._session.add(prediction)
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction

    async def get_by_id(self, pred_id: int) -> Prediction | None:
        """Look up a prediction by primary key."""
        return cast(Prediction | None, await self._session.get(Prediction, pred_id))

    async def list_recent(
        self,
        limit: int = 20,
        only_needs_review: bool = False,
        low_confidence_threshold: float = 0.7,
    ) -> list[Prediction]:
        """Return the most recent prediction rows across all batches."""
        stmt = select(Prediction).order_by(Prediction.created_at.desc(), Prediction.id.desc())
        if only_needs_review:
            stmt = stmt.where(
                Prediction.confidence < low_confidence_threshold,
                Prediction.is_relabeled.is_(False),
            )
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_batch(self, batch_id: int) -> list[Prediction]:
        """Return predictions for one batch ordered by newest first."""
        stmt = (
            select(Prediction)
            .where(Prediction.batch_id == batch_id)
            .order_by(Prediction.created_at.desc(), Prediction.id.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def relabel(
        self,
        pred_id: int,
        new_label: str,
        relabeled_by: int,
    ) -> Prediction | None:
        """Mark a prediction as relabeled and update reviewer columns."""
        prediction = await self.get_by_id(pred_id)
        if prediction is None:
            return None

        prediction.is_relabeled = True
        prediction.relabeled_to = new_label
        prediction.relabeled_by = relabeled_by
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction

    async def update_overlay_key(
        self,
        pred_id: int,
        overlay_key: str,
    ) -> Prediction | None:
        """Set the MinIO overlay_key after the annotated PNG is generated."""
        prediction = await self.get_by_id(pred_id)
        if prediction is None:
            return None

        prediction.overlay_key = overlay_key
        await self._session.flush()
        await self._session.refresh(prediction)
        return prediction
