# ruff: noqa: S101
"""Unit tests for Pydantic domain model validation constraints.

Tests verify that invalid inputs are rejected at model construction time,
that enum values are correct, and that model_validate works from ORM-like
attribute objects (the from_attributes=True pattern used by services).
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.domain.audit import AuditAction, AuditLogDomain
from app.domain.batch import BatchDomain, BatchStatus, BatchSummary, PaginatedBatchSummary
from app.domain.prediction import PredictionRead
from app.domain.user import UserDomain, UserRole, UserRoleUpdateRequest

NOW = datetime(2026, 5, 12, tzinfo=UTC)


# ---------------------------------------------------------------------------
# PredictionRead — field constraints
# ---------------------------------------------------------------------------


def _valid_prediction(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        id=1,
        batch_id=1,
        filename="scan.tif",
        predicted_label="invoice",
        confidence=0.8,
        top5_labels=["invoice"],
        top5_scores=[0.8],
        needs_review=False,
        is_relabeled=False,
        created_at=NOW,
    )
    base.update(overrides)
    return base


def test_prediction_read_rejects_negative_confidence() -> None:
    with pytest.raises(ValidationError):
        PredictionRead(**_valid_prediction(confidence=-0.01))


def test_prediction_read_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        PredictionRead(**_valid_prediction(confidence=1.001))


def test_prediction_read_accepts_confidence_at_zero() -> None:
    p = PredictionRead(**_valid_prediction(confidence=0.0))
    assert p.confidence == 0.0


def test_prediction_read_accepts_confidence_at_one() -> None:
    p = PredictionRead(**_valid_prediction(confidence=1.0))
    assert p.confidence == 1.0


def test_prediction_read_optional_fields_default_to_none() -> None:
    p = PredictionRead(**_valid_prediction())
    assert p.storage_key is None
    assert p.overlay_key is None
    assert p.relabeled_to is None
    assert p.relabeled_by is None


# ---------------------------------------------------------------------------
# BatchSummary / PaginatedBatchSummary — field constraints
# ---------------------------------------------------------------------------


def _valid_batch_summary(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = dict(
        id=1,
        owner_id=1,
        status=BatchStatus.pending,
        created_at=NOW,
        updated_at=NOW,
        prediction_count=0,
        needs_review_count=0,
    )
    base.update(overrides)
    return base


def test_batch_summary_rejects_negative_prediction_count() -> None:
    with pytest.raises(ValidationError):
        BatchSummary(**_valid_batch_summary(prediction_count=-1))


def test_batch_summary_rejects_negative_needs_review_count() -> None:
    with pytest.raises(ValidationError):
        BatchSummary(**_valid_batch_summary(needs_review_count=-1))


def test_batch_summary_accepts_zero_counts() -> None:
    s = BatchSummary(**_valid_batch_summary(prediction_count=0, needs_review_count=0))
    assert s.prediction_count == 0
    assert s.needs_review_count == 0


def test_paginated_batch_summary_rejects_zero_limit() -> None:
    """limit has gt=0 constraint."""
    with pytest.raises(ValidationError):
        PaginatedBatchSummary(items=[], total=0, limit=0, offset=0)


def test_paginated_batch_summary_rejects_negative_limit() -> None:
    with pytest.raises(ValidationError):
        PaginatedBatchSummary(items=[], total=0, limit=-1, offset=0)


def test_paginated_batch_summary_rejects_negative_total() -> None:
    with pytest.raises(ValidationError):
        PaginatedBatchSummary(items=[], total=-1, limit=10, offset=0)


def test_paginated_batch_summary_rejects_negative_offset() -> None:
    with pytest.raises(ValidationError):
        PaginatedBatchSummary(items=[], total=0, limit=10, offset=-1)


def test_paginated_batch_summary_accepts_valid_values() -> None:
    p = PaginatedBatchSummary(items=[], total=0, limit=100, offset=0)
    assert p.total == 0
    assert p.limit == 100


# ---------------------------------------------------------------------------
# BatchDomain — from_attributes model_validate
# ---------------------------------------------------------------------------


def test_batch_domain_model_validate_from_orm_like_object() -> None:
    fake_orm = SimpleNamespace(
        id=7,
        owner_id=3,
        status="completed",
        created_at=NOW,
        updated_at=NOW,
    )
    domain = BatchDomain.model_validate(fake_orm)
    assert domain.id == 7
    assert domain.status == BatchStatus.completed


# ---------------------------------------------------------------------------
# UserDomain — validation
# ---------------------------------------------------------------------------


def test_user_domain_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserDomain(id=1, email="not-an-email", role=UserRole.ADMIN, is_active=True, created_at=NOW)


def test_user_domain_accepts_valid_email() -> None:
    user = UserDomain(
        id=1,
        email="admin@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=NOW,
    )
    assert user.email == "admin@example.com"


def test_user_domain_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        UserDomain(
            id=1,
            email="x@example.com",
            role="superuser",  # type: ignore[arg-type]
            is_active=True,
            created_at=NOW,
        )


def test_user_role_update_request_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        UserRoleUpdateRequest(new_role="god")  # type: ignore[arg-type]


def test_user_role_update_request_accepts_all_defined_roles() -> None:
    for role in UserRole:
        req = UserRoleUpdateRequest(new_role=role)
        assert req.new_role == role


# ---------------------------------------------------------------------------
# Enum value contracts
# ---------------------------------------------------------------------------


def test_audit_action_string_values() -> None:
    assert AuditAction.ROLE_CHANGE == "role_change"
    assert AuditAction.RELABEL == "relabel"
    assert AuditAction.BATCH_STATE_CHANGE == "batch_state_change"


def test_batch_status_string_values() -> None:
    assert BatchStatus.pending == "pending"
    assert BatchStatus.running == "running"
    assert BatchStatus.completed == "completed"
    assert BatchStatus.failed == "failed"


def test_user_role_string_values() -> None:
    assert UserRole.ADMIN == "admin"
    assert UserRole.REVIEWER == "reviewer"
    assert UserRole.AUDITOR == "auditor"


# ---------------------------------------------------------------------------
# AuditLogDomain — from_attributes model_validate
# ---------------------------------------------------------------------------


def test_audit_log_domain_model_validate_from_orm_like_object() -> None:
    fake_orm = SimpleNamespace(
        id=1,
        actor_id=10,
        action="role_change",
        target="user:3",
        metadata_=None,
        timestamp=NOW,
    )
    domain = AuditLogDomain.model_validate(fake_orm)
    assert domain.id == 1
    assert domain.actor_id == 10
    assert domain.action == AuditAction.ROLE_CHANGE
    assert domain.metadata_ is None


def test_audit_log_domain_rejects_unknown_action() -> None:
    fake_orm = SimpleNamespace(
        id=1,
        actor_id=1,
        action="unknown_action",
        target="x",
        metadata_=None,
        timestamp=NOW,
    )
    with pytest.raises(ValidationError):
        AuditLogDomain.model_validate(fake_orm)
