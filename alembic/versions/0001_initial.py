"""initial schema: documents, tickets, triage_decisions, feedback, audit_log, eval_runs

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.config import get_settings

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = get_settings().cohere_embed_dim


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("doc_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_source_type", "documents", ["source_type"])
    op.create_index(
        "ix_documents_embedding_hnsw",
        "documents",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("customer_id", sa.String(128), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False, server_default="api"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("raw_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])

    op.create_table(
        "triage_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("routed_team", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("draft_response", sa.Text, nullable=False, server_default=""),
        sa.Column("retrieved_doc_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("tool_trace", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_triage_decisions_ticket_id", "triage_decisions", ["ticket_id"])

    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "triage_decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("triage_decisions.id"),
            nullable=False,
        ),
        sa.Column("corrected_severity", sa.String(32), nullable=True),
        sa.Column("corrected_category", sa.String(64), nullable=True),
        sa.Column("corrected_team", sa.String(64), nullable=True),
        sa.Column("human_notes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_triage_decision_id", "feedback", ["triage_decision_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tickets.id"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_ticket_id", "audit_log", ["ticket_id"])
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("audit_log")
    op.drop_table("feedback")
    op.drop_table("triage_decisions")
    op.drop_table("tickets")
    op.drop_index("ix_documents_embedding_hnsw", table_name="documents")
    op.drop_table("documents")
