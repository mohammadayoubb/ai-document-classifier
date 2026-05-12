"""SQLAlchemy ORM models — the single authoritative schema definition.

Import rule: this module is imported EXCLUSIVELY by app/repositories/.
Routes, services, and domain modules must never import from here.
"""

import enum
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class BatchStatus(str, enum.Enum):
    """Lifecycle states of a document classification batch."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class User(Base):
    """Registered application user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    role: Mapped[str] = mapped_column(default="auditor")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    batches: Mapped[list["Batch"]] = relationship(back_populates="owner")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class Batch(Base):
    """A batch of one or more documents submitted for classification."""

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[BatchStatus] = mapped_column(default=BatchStatus.pending)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="batches")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="batch")


class Prediction(Base):
    """A single document's classification result within a batch."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    filename: Mapped[str]
    storage_key: Mapped[str]        # MinIO object key for the original document
    overlay_key: Mapped[str | None] # MinIO object key for the annotated PNG
    predicted_label: Mapped[str]
    confidence: Mapped[float]
    top5_labels: Mapped[str]        # JSON array string
    top5_scores: Mapped[str]        # JSON array string
    is_relabeled: Mapped[bool] = mapped_column(default=False)
    relabeled_to: Mapped[str | None]
    relabeled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    batch: Mapped["Batch"] = relationship(back_populates="predictions")


class AuditLog(Base):
    """Immutable record of every auditable event (role change, relabel, status change)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]         # "role_change" | "relabel" | "batch_state_change"
    target: Mapped[str]         # human-readable description of what changed
    metadata_: Mapped[str | None]  # JSON extra context
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())

    actor: Mapped["User"] = relationship(back_populates="audit_entries")


class CasbinRule(Base):
    """Casbin policy rule managed by casbin-sqlalchemy-adapter."""

    __tablename__ = "casbin_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    ptype: Mapped[str | None]
    v0: Mapped[str | None]
    v1: Mapped[str | None]
    v2: Mapped[str | None]
    v3: Mapped[str | None]
    v4: Mapped[str | None]
    v5: Mapped[str | None]
