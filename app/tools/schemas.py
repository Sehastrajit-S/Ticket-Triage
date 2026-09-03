"""Cohere tool_definitions (OpenAI-style function schema) for the director's tool-use loop."""

from app.agent.schemas import Category, Severity

_CATEGORY_VALUES = [c.value for c in Category]
_SEVERITY_VALUES = [s.value for s in Severity]

_CATEGORY_PROPERTY = {"type": "string", "enum": _CATEGORY_VALUES}
_SEVERITY_PROPERTY = {"type": "string", "enum": _SEVERITY_VALUES}

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Semantic search over past resolved tickets, KB articles, runbooks, and policy "
                "docs (Embed v4 + Rerank 4). Use this before classifying or drafting a reply to "
                "ground your answer in real precedent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query, e.g. the ticket subject/body."},
                    "source_types": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["ticket", "kb", "runbook", "policy"]},
                        "description": "Optional filter on document source type.",
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of reranked results to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_ticket",
            "description": "Classify a ticket's severity and category using its subject and body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_policy",
            "description": "Look up the SLA and escalation policy that applies to a given category+severity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": _CATEGORY_PROPERTY,
                    "severity": _SEVERITY_PROPERTY,
                },
                "required": ["category", "severity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_ticket",
            "description": "Decide which team a ticket should be routed to, and whether it must be escalated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": _CATEGORY_PROPERTY,
                    "severity": _SEVERITY_PROPERTY,
                },
                "required": ["category", "severity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_response",
            "description": (
                "Draft a customer-facing reply grounded in previously retrieved documents. "
                "Pass the doc_ids returned by search_knowledge_base — do not invent ids."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "category": _CATEGORY_PROPERTY,
                    "doc_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["subject", "body", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_ticket",
            "description": "Notify the on-call channel about a ticket needing immediate human attention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string"},
                    "severity": _SEVERITY_PROPERTY,
                    "category": _CATEGORY_PROPERTY,
                    "reason": {"type": "string"},
                },
                "required": ["ticket_id", "severity", "category", "reason"],
            },
        },
    },
]
