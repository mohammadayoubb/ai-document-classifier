# ruff: noqa: S101
"""Unit tests for service layer mapper helpers.

Covers prediction_to_read, batch_to_domain, batch_to_summary, and
_decode_json_list. No database or network required.
"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domain.batch import BatchStatus
from app.services.mappers import (
    _decode_json_list,
    batch_to_domain,
    batch_to_summary,
    prediction_to_read,
)

NOW = datetime(2026, 5, 12, tzinfo=UTC)
THRESHOLD = 0.7


def _raw_prediction(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = dict(
        id=1,
        batch_id=5,
        filename="scan.tif",
        storage_key="documents/scan.tif",
        overlay_key=None,
        predicted_label="invoice",
        confidence=0.4,
        top5_labels=json.dumps(["invoice", "form"]),
        top5_scores=json.dumps([0.4, 0.6]),
        is_relabeled=False,
        relabeled_to=None,
        relabeled_by=None,
        created_at=NOW,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _raw_batch(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = dict(
        id=7,
        owner_id=3,
        status="pending",
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# prediction_to_read — needs_review logic
# ---------------------------------------------------------------------------


def test_needs_review_true_when_low_confidence_and_not_relabeled() -> None:
    raw = _raw_prediction(confidence=0.4)
    result = prediction_to_read(raw, THRESHOLD)
    assert result.needs_review is True


def test_needs_review_false_when_confidence_at_threshold() -> None:
    """Confidence equal to the threshold is NOT low-confidence."""
    raw = _raw_prediction(confidence=THRESHOLD)
    result = prediction_to_read(raw, THRESHOLD)
    assert result.needs_review is False


def test_needs_review_false_when_confidence_above_threshold() -> None:
    raw = _raw_prediction(confidence=0.95)
    result = prediction_to_read(raw, THRESHOLD)
    assert result.needs_review is False


def test_needs_review_false_when_relabeled_even_if_low_confidence() -> None:
    """A relabeled prediction is considered resolved regardless of confidence."""
    raw = _raw_prediction(confidence=0.1, is_relabeled=True)
    result = prediction_to_read(raw, THRESHOLD)
    assert result.needs_review is False


# ---------------------------------------------------------------------------
# prediction_to_read — field mapping
# ---------------------------------------------------------------------------


def test_prediction_to_read_decodes_json_list_strings() -> None:
    raw = _raw_prediction(
        top5_labels=json.dumps(["invoice", "form", "email"]),
        top5_scores=json.dumps([0.5, 0.3, 0.2]),
    )
    result = prediction_to_read(raw, THRESHOLD)
    assert result.top5_labels == ["invoice", "form", "email"]
    assert result.top5_scores == pytest.approx([0.5, 0.3, 0.2])


def test_prediction_to_read_handles_list_values_directly() -> None:
    """Pre-decoded lists (not JSON strings) pass through unchanged."""
    raw = _raw_prediction(
        top5_labels=["letter", "memo"],
        top5_scores=[0.55, 0.45],
    )
    result = prediction_to_read(raw, THRESHOLD)
    assert result.top5_labels == ["letter", "memo"]
    assert result.top5_scores == pytest.approx([0.55, 0.45])


def test_prediction_to_read_passes_through_relabel_fields() -> None:
    raw = _raw_prediction(
        confidence=0.3,
        is_relabeled=True,
        relabeled_to="form",
        relabeled_by=42,
    )
    result = prediction_to_read(raw, THRESHOLD)
    assert result.is_relabeled is True
    assert result.relabeled_to == "form"
    assert result.relabeled_by == 42


def test_prediction_to_read_passes_through_overlay_key() -> None:
    raw = _raw_prediction(overlay_key="overlays/scan.png")
    result = prediction_to_read(raw, THRESHOLD)
    assert result.overlay_key == "overlays/scan.png"


def test_prediction_to_read_overlay_key_none_by_default() -> None:
    raw = _raw_prediction()
    result = prediction_to_read(raw, THRESHOLD)
    assert result.overlay_key is None


def test_prediction_to_read_maps_core_identity_fields() -> None:
    raw = _raw_prediction(id=99, batch_id=7, filename="doc.tif", predicted_label="memo")
    result = prediction_to_read(raw, THRESHOLD)
    assert result.id == 99
    assert result.batch_id == 7
    assert result.filename == "doc.tif"
    assert result.predicted_label == "memo"


# ---------------------------------------------------------------------------
# batch_to_domain
# ---------------------------------------------------------------------------


def test_batch_to_domain_converts_string_status_to_enum() -> None:
    raw = _raw_batch(status="completed")
    result = batch_to_domain(raw)
    assert result.status == BatchStatus.completed


def test_batch_to_domain_converts_enum_status() -> None:
    raw = _raw_batch(status=BatchStatus.running)
    result = batch_to_domain(raw)
    assert result.status == BatchStatus.running


def test_batch_to_domain_maps_all_fields() -> None:
    raw = _raw_batch(id=99, owner_id=7)
    result = batch_to_domain(raw)
    assert result.id == 99
    assert result.owner_id == 7
    assert result.created_at == NOW
    assert result.updated_at == NOW


# ---------------------------------------------------------------------------
# batch_to_summary
# ---------------------------------------------------------------------------


def test_batch_to_summary_includes_prediction_counts() -> None:
    raw = _raw_batch()
    result = batch_to_summary(raw, prediction_count=5, needs_review_count=2)
    assert result.prediction_count == 5
    assert result.needs_review_count == 2


def test_batch_to_summary_defaults_counts_to_zero() -> None:
    raw = _raw_batch()
    result = batch_to_summary(raw)
    assert result.prediction_count == 0
    assert result.needs_review_count == 0


def test_batch_to_summary_preserves_batch_domain_fields() -> None:
    raw = _raw_batch(id=11, status="failed")
    result = batch_to_summary(raw, prediction_count=3, needs_review_count=1)
    assert result.id == 11
    assert result.status == BatchStatus.failed


# ---------------------------------------------------------------------------
# _decode_json_list
# ---------------------------------------------------------------------------


def test_decode_json_list_parses_json_array_string() -> None:
    assert _decode_json_list('["a", "b"]') == ["a", "b"]


def test_decode_json_list_returns_list_directly() -> None:
    assert _decode_json_list([1, 2, 3]) == [1, 2, 3]


def test_decode_json_list_returns_empty_for_none() -> None:
    assert _decode_json_list(None) == []


def test_decode_json_list_raises_for_non_array_json() -> None:
    with pytest.raises(ValueError, match="JSON array"):
        _decode_json_list('{"key": "value"}')


def test_decode_json_list_parses_numeric_array() -> None:
    result = _decode_json_list("[0.8, 0.1, 0.1]")
    assert result == pytest.approx([0.8, 0.1, 0.1])
