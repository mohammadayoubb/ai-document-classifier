# ruff: noqa: S101
"""Unit tests for AuditService.

Tests verify that the service delegates to the repository correctly,
converts ORM objects to domain models, and handles all audit action types.
No database required — FakeAuditRepository is used throughout.
"""

from datetime import UTC, datetime

from app.domain.audit import AuditAction, AuditLogDomain
from app.services.audit_service import AuditService

NOW = datetime(2026, 5, 12, tzinfo=UTC)


class FakeAuditEntry:
    """Mimics an AuditLog ORM row returned by the repository."""

    def __init__(
        self,
        entry_id: int,
        actor_id: int,
        action: str,
        target: str,
        metadata_: str | None = None,
    ) -> None:
        self.id = entry_id
        self.actor_id = actor_id
        self.action = action
        self.target = target
        self.metadata_ = metadata_
        self.timestamp = NOW


class FakeAuditRepository:
    """In-memory audit repository stub."""

    def __init__(self, stored: list[FakeAuditEntry] | None = None) -> None:
        self.created: list[dict[str, object]] = []
        self.stored: list[FakeAuditEntry] = stored or []
        self._next_id = 1

    async def create(
        self,
        actor_id: int,
        action: str,
        target: str,
        metadata: str | None,
    ) -> FakeAuditEntry:
        self.created.append(
            {"actor_id": actor_id, "action": action, "target": target, "metadata": metadata}
        )
        entry = FakeAuditEntry(
            entry_id=self._next_id,
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_=metadata,
        )
        self._next_id += 1
        return entry

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[FakeAuditEntry]:
        return self.stored[offset : offset + limit]


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------


async def test_record_calls_repo_create_with_correct_args() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    await service.record(
        actor_id=1,
        action=AuditAction.ROLE_CHANGE,
        target="user:2",
        metadata='{"old_role": "auditor", "new_role": "reviewer"}',
    )

    assert len(repo.created) == 1
    call = repo.created[0]
    assert call["actor_id"] == 1
    assert call["action"] == AuditAction.ROLE_CHANGE.value
    assert call["target"] == "user:2"
    assert call["metadata"] == '{"old_role": "auditor", "new_role": "reviewer"}'


async def test_record_returns_audit_log_domain_instance() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.record(
        actor_id=5,
        action=AuditAction.RELABEL,
        target="prediction:9",
    )

    assert isinstance(result, AuditLogDomain)
    assert result.actor_id == 5
    assert result.action == AuditAction.RELABEL
    assert result.target == "prediction:9"


async def test_record_domain_id_matches_repo_assigned_id() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    first = await service.record(actor_id=1, action=AuditAction.RELABEL, target="prediction:1")
    second = await service.record(actor_id=1, action=AuditAction.RELABEL, target="prediction:2")

    assert first.id == 1
    assert second.id == 2


async def test_record_with_none_metadata_stores_none() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.record(
        actor_id=1,
        action=AuditAction.BATCH_STATE_CHANGE,
        target="batch:3",
        metadata=None,
    )

    assert result.metadata_ is None
    assert repo.created[0]["metadata"] is None


async def test_record_batch_state_change_action() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.record(
        actor_id=2,
        action=AuditAction.BATCH_STATE_CHANGE,
        target="batch:10",
        metadata='{"status": "completed"}',
    )

    assert result.action == AuditAction.BATCH_STATE_CHANGE


# ---------------------------------------------------------------------------
# list_audit_log()
# ---------------------------------------------------------------------------


async def test_list_audit_log_returns_domain_model_list() -> None:
    stored = [
        FakeAuditEntry(1, 1, AuditAction.ROLE_CHANGE.value, "user:2"),
        FakeAuditEntry(2, 1, AuditAction.RELABEL.value, "prediction:5"),
    ]
    repo = FakeAuditRepository(stored=stored)
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.list_audit_log()

    assert len(result) == 2
    assert all(isinstance(r, AuditLogDomain) for r in result)
    assert result[0].action == AuditAction.ROLE_CHANGE
    assert result[1].action == AuditAction.RELABEL


async def test_list_audit_log_returns_empty_list_when_no_entries() -> None:
    repo = FakeAuditRepository()
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.list_audit_log()

    assert result == []


async def test_list_audit_log_maps_metadata_field_correctly() -> None:
    stored = [FakeAuditEntry(1, 1, AuditAction.ROLE_CHANGE.value, "user:2", metadata_='{"k": 1}')]
    repo = FakeAuditRepository(stored=stored)
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.list_audit_log()

    assert result[0].metadata_ == '{"k": 1}'


async def test_list_audit_log_preserves_actor_and_target() -> None:
    stored = [FakeAuditEntry(1, actor_id=7, action=AuditAction.RELABEL.value, target="prediction:42")]
    repo = FakeAuditRepository(stored=stored)
    service = AuditService(audit_repo=repo)  # type: ignore[arg-type]

    result = await service.list_audit_log()

    assert result[0].actor_id == 7
    assert result[0].target == "prediction:42"
