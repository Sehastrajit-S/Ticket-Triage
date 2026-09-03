import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.config import get_settings
from app.db.base import Base

EMBED_DIM = get_settings().cohere_embed_dim


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Document(Base):
    """A chunk of knowledge: past resolved ticket, KB article, runbook, or policy doc."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_type: Mapped[str] = mapped_column(String(32), index=True)  # ticket|kb|runbook|policy
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_documents_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Ticket(Base):
    """An inbound support ticket."""

    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="api")  # api|slack|email
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    raw_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    triage_decisions: Mapped[list["TriageDecision"]] = relationship(back_populates="ticket")


class TriageDecision(Base):
    """The director agent's output for a given ticket run."""

    __tablename__ = "triage_decisions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickets.id"), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64))
    routed_team: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    draft_response: Mapped[str] = mapped_column(Text, default="")
    retrieved_doc_ids: Mapped[list] = mapped_column(JSON, default=list)
    tool_trace: Mapped[list] = mapped_column(JSON, default=list)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="triage_decisions")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="triage_decision")


class Feedback(Base):
    """Human corrections applied to a triage decision, used for eval + future tuning."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = _uuid_pk()
    triage_decision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("triage_decisions.id"), index=True)
    corrected_severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corrected_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    human_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    triage_decision: Mapped["TriageDecision"] = relationship(back_populates="feedback")


class AuditLog(Base):
    """Append-only log of every tool invocation, for tool-success-rate metrics and debugging."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)  # tool_call|tool_error|escalation|...
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRun(Base):
    """A single evaluation-harness execution and its aggregate metrics."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_version: Mapped[str] = mapped_column(String(32), default="v1")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
