"""Prediction business logic — recent reads, relabeling, and worker writes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from app.config import Settings, get_settings
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
        self._repo = repo
        self._cache = cache
        self._audit = audit
        self._settings = settings or get_settings()

    async def list_recent(
        self,
        limit: int = 20,
        only_needs_review: bool = False,
    ) -> RecentPredictionsResponse:
        """Return cached recent predictions across all batches."""
        limit = min(max(limit, 1), 100)
        cache_key = self._cache.recent_predictions_key(limit, only_needs_review)
        cached = await self._cache.get_json(cache_key)
        if cached is not None:
            return cast(
                RecentPredictionsResponse,
                RecentPredictionsResponse.model_validate(cached),
            )

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
        await self._cache.set_json(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=self._settings.cache_ttl_recent,
        )
        return response

    async def relabel(self, pred_id: int, new_label: str, actor_id: int) -> PredictionRead:
        """Relabel a low-confidence prediction after validating the corrected label."""
        self._validate_label(new_label)
        prediction = await self._repo.get_by_id(pred_id)
        if prediction is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        if float(prediction.confidence) >= self._settings.low_confidence_threshold:
            raise ValueError(
                "Only low-confidence predictions can be relabeled "
                f"(< {self._settings.low_confidence_threshold})."
            )

        updated = await self._repo.relabel(pred_id, new_label, actor_id)
        if updated is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        # Member B integration point: call the audit writer here when it is ready.
        _ = self._audit

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
        """Create a prediction row from worker/classifier output."""
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
        await self._cache.invalidate_after_prediction_write(batch_id)
        return prediction_to_read(created, self._settings.low_confidence_threshold)

    async def update_overlay_key(self, pred_id: int, overlay_key: str) -> PredictionRead:
        """Update a prediction overlay key and invalidate affected caches."""
        updated = await self._repo.update_overlay_key(pred_id, overlay_key)
        if updated is None:
            raise LookupError(f"Prediction {pred_id} was not found.")

        await self._cache.invalidate_after_prediction_write(updated.batch_id)
        return prediction_to_read(updated, self._settings.low_confidence_threshold)

    def _validate_label(self, label: str) -> None:
        if label not in self._settings.classifier_labels:
            raise ValueError(f"'{label}' is not a configured classifier label.")


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    if obj is None:
        return default
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default
