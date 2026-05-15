"""Prediction service — owns prediction review rules, cache behavior, and audit calls.

Routes and workers call this layer when they need prediction read/write behavior
that is more than raw SQL.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from app.config import Settings, get_settings
from app.domain.audit import AuditAction
from app.domain.prediction import PredictionRead, RecentPredictionsResponse
from app.services.mappers import prediction_to_read


class PredictionService:
    """Manages prediction reads, relabel validation, writes, and cache invalidation."""

    def __init__(
        self,
        repo: Any,
        cache: Any,
        audit: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Store service dependencies.

        Args:
            repo: Prediction repository-like object.
            cache: Cache adapter-like object.
            audit: Optional audit service-like object.
            settings: Optional settings override for tests.
        """
        self._repo = repo
        self._cache = cache
        self._audit = audit
        self._settings = settings or get_settings()

    async def list_recent(
        self,
        limit: int = 20,
        only_needs_review: bool = False,
    ) -> RecentPredictionsResponse:
        """Return cached recent predictions across all batches.

        Args:
            limit: Maximum number of recent predictions to return.
            only_needs_review: Whether to include only low-confidence unreviewed rows.

        Returns:
            Recent predictions response with decoded top-5 fields.
        """
        limit = min(max(limit, 1), 100)
        cache_key = self._cache.recent_predictions_key(limit, only_needs_review)

        # CACHE READ: dashboard/review widgets reuse recent-prediction pages.
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cast(
                RecentPredictionsResponse,
                RecentPredictionsResponse.model_validate(cached),
            )

        # REPOSITORY CALL: no cache hit, so fetch current rows from SQL.
        predictions = await self._repo.list_recent(
            limit=limit,
            only_needs_review=only_needs_review,
            low_confidence_threshold=self._settings.low_confidence_threshold,
        )
        items = [
            prediction_to_read(prediction, self._settings.low_confidence_threshold)
            for prediction in predictions
        ]
        response = RecentPredictionsResponse(items=items, total=len(items), limit=limit)

        # CACHE WRITE: store serialized Pydantic response for later requests.
        await self._cache.set_json(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=self._settings.cache_ttl_recent,
        )
        return response

    async def relabel(self, pred_id: int, new_label: str, actor_id: int) -> PredictionRead:
        """Relabel a low-confidence prediction after validating the corrected label.

        Args:
            pred_id: Prediction primary key.
            new_label: Human-selected label, including same-label confirmation.
            actor_id: Reviewer/admin user id applying the label.

        Returns:
            Updated prediction read model.

        Raises:
            ValueError: If the label is invalid or the prediction is high-confidence.
            LookupError: If the prediction does not exist.
        """
        self._validate_label(new_label)

        # REPOSITORY CALL: load original row for validation and audit metadata.
        prediction = await self._repo.get_by_id(pred_id)
        if prediction is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        # only confidence < 0.7 can be relabeled.
        if float(prediction.confidence) >= self._settings.low_confidence_threshold:
            raise ValueError(
                "Only low-confidence predictions can be relabeled "
                f"(< {self._settings.low_confidence_threshold})."
            )

        # REPOSITORY CALL: mark prediction as human-reviewed/relabelled.
        updated = await self._repo.relabel(pred_id, new_label, actor_id)
        if updated is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        if self._audit is not None:
            # AUDIT CALL: relabels are governance events and must be traceable.
            await self._audit.record(
                actor_id=actor_id,
                action=AuditAction.RELABEL,
                target=f"prediction:{pred_id}",
                metadata=json.dumps({
                    "old_label": prediction.predicted_label,
                    "new_label": new_label,
                    "batch_id": updated.batch_id,
                    "filename": prediction.filename,
                }),
            )

        # CACHE INVALIDATION: relabeling changes batch detail and recent-review views.
        await self._cache.invalidate_after_relabel(updated.batch_id)
        return prediction_to_read(updated, self._settings.low_confidence_threshold)

    async def create_prediction_from_worker(
        self,
        *,
        batch_id: int,
        filename: str,
        storage_key: str,
        predicted_label: str | None = None,
        confidence: float | None = None,
        top5_labels: Sequence[str] | None = None,
        top5_scores: Sequence[float] | None = None,
        overlay_key: str | None = None,
        prediction_result: Any | None = None,
    ) -> PredictionRead:
        """Create a prediction row from worker/classifier output.

        Args:
            batch_id: Parent batch id.
            filename: Original document filename.
            storage_key: MinIO key for the source document.
            predicted_label: Optional top-1 label from the worker.
            confidence: Optional top-1 confidence from the worker.
            top5_labels: Optional top-5 labels.
            top5_scores: Optional top-5 scores.
            overlay_key: Optional MinIO key for overlay image.
            prediction_result: Optional object with classifier result attributes.

        Returns:
            Created prediction read model.

        Raises:
            ValueError: If label or confidence is missing.
        """
        predicted_label = predicted_label or _attr(
            prediction_result,
            "predicted_label",
            "label",
        )
        confidence = confidence if confidence is not None else _attr(
            prediction_result,
            "confidence",
            "score",
        )
        top5_labels = top5_labels or _attr(prediction_result, "top5_labels", default=None)
        top5_scores = top5_scores or _attr(prediction_result, "top5_scores", default=None)

        if predicted_label is None or confidence is None:
            raise ValueError("Worker prediction must include predicted_label and confidence.")

        labels = list(top5_labels) if top5_labels is not None else [str(predicted_label)]
        scores = list(top5_scores) if top5_scores is not None else [float(confidence)]

        # REPOSITORY CALL: persist worker output as a prediction row.
        created = await self._repo.create(
            batch_id=batch_id,
            filename=filename,
            storage_key=storage_key,
            predicted_label=str(predicted_label),
            confidence=float(confidence),
            top5_labels=json.dumps(labels),
            top5_scores=json.dumps(scores),
            overlay_key=overlay_key,
        )

        # CACHE INVALIDATION: worker writes affect batch detail/list and recent predictions.
        await self._cache.invalidate_after_prediction_write(batch_id)
        return prediction_to_read(created, self._settings.low_confidence_threshold)

    # updates the overlay key for a given prediction and then invalidates any caches that might be affected by this change.
    #  This is likely used when a new overlay image is generated for a prediction, and we need to update the reference to that overlay in the prediction record.
    async def update_overlay_key(self, pred_id: int, overlay_key: str) -> PredictionRead:
        """Update a prediction overlay key and invalidate affected caches.

        Args:
            pred_id: Prediction primary key.
            overlay_key: MinIO key for the generated overlay image.

        Returns:
            Updated prediction read model.

        Raises:
            LookupError: If the prediction does not exist.
        """
        # REPOSITORY CALL: persist overlay metadata.
        updated = await self._repo.update_overlay_key(pred_id, overlay_key)
        if updated is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        # CACHE INVALIDATION: overlay URL appears in batch/detail and recent views.
        await self._cache.invalidate_after_prediction_write(updated.batch_id)
        return prediction_to_read(updated, self._settings.low_confidence_threshold)

    def _validate_label(self, label: str) -> None:
        """Ensure a human-selected label is part of the configured classifier labels.

        Args:
            label: Label submitted by a reviewer/admin.

        Raises:
            ValueError: If the label is not configured.
        """
        if label not in self._settings.classifier_labels:
            raise ValueError(f"'{label}' is not a configured classifier label.")


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Read the first available attribute from a classifier result object.

    Args:
        obj: Source object to inspect.
        names: Candidate attribute names in priority order.
        default: Value returned when no attribute exists.

    Returns:
        The first matching attribute value, or default.
    """
    if obj is None:
        return default
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default
