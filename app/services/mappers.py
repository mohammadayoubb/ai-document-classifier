"""Mapper helpers — convert ORM-like objects into Pydantic domain models.

Services use these helpers at their boundary so routes never receive raw
SQLAlchemy objects or JSON-encoded classifier fields.
"""

from __future__ import annotations

import json
from typing import Any

from app.domain.batch import BatchDomain, BatchStatus, BatchSummary
from app.domain.prediction import PredictionRead


# what this mapper does is to convert the prediction object that we get from the database into a PredictionRead object that we can return to the client.
# It also decodes the top5_labels and top5_scores from JSON strings into Python lists. It also determines if the prediction needs review based on the confidence and whether it has been relabeled.
def prediction_to_read(prediction: Any, low_confidence_threshold: float) -> PredictionRead:
    """Convert a prediction-like object into the service read model.

    Args:
        prediction: ORM-like prediction object from a repository.
        low_confidence_threshold: Confidence below which review is needed.

    Returns:
        PredictionRead with decoded top-5 fields and needs_review flag.
    """
    # JSON DECODE: database stores top-5 values as strings; domain uses lists.
    top5_labels = [str(label) for label in _decode_json_list(prediction.top5_labels)]
    top5_scores = [float(score) for score in _decode_json_list(prediction.top5_scores)]
    confidence = float(prediction.confidence)
    is_relabeled = bool(getattr(prediction, "is_relabeled", False))

    # DOMAIN MAP: build the Pydantic response model used by service callers.
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
    """Convert a batch-like object into the base batch read model.

    Args:
        batch: ORM-like batch object from a repository.

    Returns:
        BatchDomain with normalized status enum.
    """
    # DOMAIN MAP: normalize ORM enum/string status into the domain enum.
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
    """Convert a batch-like object and counts into a summary model.

    Args:
        batch: ORM-like batch object from a repository.
        prediction_count: Number of predictions in the batch.
        needs_review_count: Number of predictions needing human review.

    Returns:
        BatchSummary used by paginated list responses.
    """
    # DOMAIN MAP: reuse the base conversion, then add aggregate counters.
    domain = batch_to_domain(batch)
    return BatchSummary(
        **domain.model_dump(),
        prediction_count=prediction_count,
        needs_review_count=needs_review_count,
    )


def _decode_json_list(value: Any) -> list[Any]:
    """Decode a JSON list stored by the database layer.

    Args:
        value: JSON string, Python iterable, or None.

    Returns:
        A Python list.

    Raises:
        ValueError: If a JSON string does not decode to a list.
    """
    if value is None:
        return []
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, list):
            raise ValueError("Expected a JSON array string.")
        return decoded
    return list(value)
