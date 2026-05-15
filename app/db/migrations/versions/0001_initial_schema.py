"""Initial document-classifier schema migration.

This migration owns the first database shape: users, batches, predictions,
audit log rows, Casbin policies, and the batch status enum.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-12 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the current application tables.

    All DDL uses IF NOT EXISTS / DO...EXCEPTION so that a partial previous run
    (where the enum or some tables were created but alembic_version was not
    stamped) does not block a clean re-run.
    """
    # DDL CALL: PostgreSQL enum type required by batches.status.
    # PostgreSQL DO...EXCEPTION is the only reliable way to
    # create a type idempotently; CREATE TYPE lacks IF NOT EXISTS before PG 9.1,
    # and SQLAlchemy's create_type=False flag can be lost when the type object
    # is copied internally during op.create_table.
    op.execute(sa.text(
        "DO $$ BEGIN "
        "  CREATE TYPE batchstatus AS ENUM ('pending', 'running', 'completed', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    ))

    # DDL CALL: users table used by auth, ownership, and role management.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
            id          SERIAL          PRIMARY KEY,
            email       VARCHAR(320)    NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role        VARCHAR(64)     NOT NULL,
            is_active   BOOLEAN         NOT NULL,
            created_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
        )
    """))
    # DDL CALL: unique index enforces one account per email address.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
    ))

    # DDL CALL: batches table groups one document classification request.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS batches (
            id          SERIAL          PRIMARY KEY,
            owner_id    INTEGER         NOT NULL REFERENCES users(id),
            status      batchstatus     NOT NULL,
            created_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ     NOT NULL DEFAULT now()
        )
    """))

    # DDL CALL: audit_log table stores immutable governance events.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          SERIAL          PRIMARY KEY,
            actor_id    INTEGER         NOT NULL REFERENCES users(id),
            action      VARCHAR(128)    NOT NULL,
            target      VARCHAR(255)    NOT NULL,
            metadata    TEXT,
            timestamp   TIMESTAMPTZ     NOT NULL DEFAULT now()
        )
    """))

    # DDL CALL: casbin_rule table stores RBAC policy loaded at API startup.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS casbin_rule (
            id      SERIAL          PRIMARY KEY,
            ptype   VARCHAR(255),
            v0      VARCHAR(255),
            v1      VARCHAR(255),
            v2      VARCHAR(255),
            v3      VARCHAR(255),
            v4      VARCHAR(255),
            v5      VARCHAR(255)
        )
    """))

    # DDL CALL: predictions table stores classifier output and human review data.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS predictions (
            id              SERIAL          PRIMARY KEY,
            batch_id        INTEGER         NOT NULL REFERENCES batches(id),
            filename        VARCHAR(255)    NOT NULL,
            storage_key     VARCHAR(1024)   NOT NULL,
            overlay_key     VARCHAR(1024),
            predicted_label VARCHAR(128)    NOT NULL,
            confidence      DOUBLE PRECISION NOT NULL,
            top5_labels     TEXT            NOT NULL,
            top5_scores     TEXT            NOT NULL,
            is_relabeled    BOOLEAN         NOT NULL,
            relabeled_to    VARCHAR(128),
            relabeled_by    INTEGER         REFERENCES users(id),
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now()
        )
    """))
    # DDL CALL: index speeds batch-detail prediction lookups.
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_predictions_batch_id ON predictions (batch_id)"
    ))


def downgrade() -> None:
    """Drop the initial application tables.

    Tables are dropped in dependency order so foreign keys do not block rollback.
    """
    # DDL CALL: reverse order mirrors table dependencies from predictions upward.
    op.execute(sa.text("DROP INDEX IF EXISTS ix_predictions_batch_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS predictions"))
    op.execute(sa.text("DROP TABLE IF EXISTS casbin_rule"))
    op.execute(sa.text("DROP TABLE IF EXISTS audit_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS batches"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_users_email"))
    op.execute(sa.text("DROP TABLE IF EXISTS users"))
    op.execute(sa.text("DROP TYPE IF EXISTS batchstatus"))
