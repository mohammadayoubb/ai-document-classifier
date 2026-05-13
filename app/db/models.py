"""SQLAlchemy ORM models — the single authoritative schema definition.

Import rule: this module is imported EXCLUSIVELY by app/repositories/.
Routes, services, and domain modules must never import from here.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class BatchStatus(enum.StrEnum):
    """Lifecycle states of a document classification batch."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


batch_status_enum = SAEnum(
    BatchStatus,
    name="batchstatus",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class User(Base):
    """Registered application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(
        String(320),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), default="auditor", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    batches: Mapped[list["Batch"]] = relationship(back_populates="owner")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class Batch(Base):
    """A batch of one or more documents submitted for classification."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(
        batch_status_enum,
        default=BatchStatus.pending,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="batches")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="batch")


class Prediction(Base):
    """A single document's classification result within a batch."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batches.id"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    overlay_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    predicted_label: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    top5_labels: Mapped[str] = mapped_column(Text, nullable=False)
    top5_scores: Mapped[str] = mapped_column(Text, nullable=False)
    is_relabeled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    relabeled_to: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relabeled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    batch: Mapped["Batch"] = relationship(back_populates="predictions")


class AuditLog(Base):
    """Immutable record of every auditable event.

    Required audit events:
    - role changes
    - prediction relabels
    - batch status changes
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    actor: Mapped["User"] = relationship(back_populates="audit_entries")


class CasbinRule(Base):
    """Casbin policy rule managed by casbin-sqlalchemy-adapter."""

    __tablename__ = "casbin_rule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ptype: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v0: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v4: Mapped[str | None] = mapped_column(String(255), nullable=True)
    v5: Mapped[str | None] = mapped_column(String(255), nullable=True)
