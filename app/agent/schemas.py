"""Shared taxonomy and pydantic I/O contracts for tools + the director agent."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    P1_CRITICAL = "P1-critical"
    P2_HIGH = "P2-high"
    P3_MEDIUM = "P3-medium"
    P4_LOW = "P4-low"


class Category(StrEnum):
    BILLING = "billing"
    TECHNICAL_BUG = "technical_bug"
    ACCOUNT_ACCESS = "account_access"
    FEATURE_REQUEST = "feature_request"
    HOW_TO = "how_to"
    SECURITY = "security"
    OTHER = "other"


# Default category -> team routing. P1 tickets and anything tagged `security`
# are escalated regardless of this table (see tools/route.py).
DEFAULT_CATEGORY_TEAM_MAP: dict[Category, str] = {
    Category.BILLING: "billing_support",
    Category.TECHNICAL_BUG: "engineering_support",
    Category.ACCOUNT_ACCESS: "account_support",
    Category.FEATURE_REQUEST: "product_backlog",
    Category.HOW_TO: "general_support",
    Category.SECURITY: "security_team",
    Category.OTHER: "general_support",
}

ESCALATION_SEVERITIES = {Severity.P1_CRITICAL}
ESCALATION_CATEGORIES = {Category.SECURITY}


class TicketInput(BaseModel):
    subject: str
    body: str
    customer_id: str | None = None
    channel: str = "api"


# --- Tool I/O contracts -----------------------------------------------------


class SearchKBInput(BaseModel):
    query: str
    source_types: list[str] | None = None
    top_n: int | None = None


class SearchKBResult(BaseModel):
    document_id: str
    source_type: str
    title: str
    content: str
    relevance_score: float


class ClassifyInput(BaseModel):
    subject: str
    body: str


class ClassifyResult(BaseModel):
    severity: Severity
    category: Category
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class PolicyCheckInput(BaseModel):
    category: Category
    severity: Severity


class PolicyCheckResult(BaseModel):
    sla_hours: int
    policy_notes: str
    matched_doc_ids: list[str] = Field(default_factory=list)


class RouteInput(BaseModel):
    category: Category
    severity: Severity


class RouteResult(BaseModel):
    team: str
    escalated: bool
    reason: str


class DraftResponseInput(BaseModel):
    subject: str
    body: str
    category: Category
    doc_ids: list[str] = Field(
        default_factory=list,
        description="Document ids previously returned by search_knowledge_base to ground the reply in.",
    )


class DraftResponseResult(BaseModel):
    draft: str
    cited_doc_ids: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(
        default_factory=list,
        description="Span-level citations from Cohere's native grounded generation, each tied to source document ids.",
    )


class EscalateInput(BaseModel):
    ticket_id: str
    severity: Severity
    category: Category
    reason: str


class EscalateResult(BaseModel):
    notified: bool
    channel: str


class TriageResult(BaseModel):
    """Final, persisted output of a director run."""

    ticket_id: str
    severity: Severity
    category: Category
    routed_team: str
    confidence: float
    rationale: str
    draft_response: str
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    tool_trace: list[dict] = Field(default_factory=list)
    escalated: bool = False
    latency_ms: int = 0
