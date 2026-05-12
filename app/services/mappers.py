"""Mapping helpers from repository objects to domain models."""

from __future__ import annotations

import json
from typing import Any

from app.domain.batch import BatchDomain, BatchStatus, BatchSummary
from app.domain.prediction import PredictionRead


def prediction_to_read(prediction: Any, low_confidence_threshold: float) -> PredictionRead:
    """Convert a prediction-like object into the service read model."""
    top5_labels = [str(label) for label in _decode_json_list(prediction.top5_labels)]
    top5_scores = [float(score) for score in _decode_json_list(prediction.top5_scores)]
    confidence = float(prediction.confidence)
    is_relabeled = bool(getattr(prediction, "is_relabeled", False))

    return PredictionRead(
        id=prediction.id,
        batch_id=prediction.batch_id,
        filename=prediction.filename,
        storage_key=getattr(prediction, "storage_key", None),
        overlay_key=getattr(prediction, "overlay_key", None),
        predicted_label=prediction.predicted_label,
        confidence=confidence,
        top5_labels=top5_labels,
        top5_scores=top5_scores,
        needs_review=confidence < low_confidence_threshold and not is_relabeled,
        is_relabeled=is_relabeled,
        relabeled_to=getattr(prediction, "relabeled_to", None),
        relabeled_by=getattr(prediction, "relabeled_by", None),
        created_at=prediction.created_at,
    )


def batch_to_domain(batch: Any) -> BatchDomain:
    """Convert a batch-like object into the base batch read model."""
    return BatchDomain(
        id=batch.id,
        owner_id=batch.owner_id,
        status=BatchStatus(getattr(batch.status, "value", batch.status)),
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


def batch_to_summary(
    batch: Any,
    prediction_count: int = 0,
    needs_review_count: int = 0,
) -> BatchSummary:
    """Convert a batch-like object and counts into a summary model."""
    domain = batch_to_domain(batch)
    return BatchSummary(
        **domain.model_dump(),
        prediction_count=prediction_count,
        needs_review_count=needs_review_count,
    )


def _decode_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, list):
            raise ValueError("Expected a JSON array string.")
        return decoded
    return list(value)
