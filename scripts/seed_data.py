"""Populate the DB with sample KB articles, runbooks, policy docs, and historical
resolved tickets so retrieval + the director agent have something to work with.

Usage: python -m scripts.seed_data
"""

from __future__ import annotations

import asyncio

from app.db.session import AsyncSessionLocal
from app.retrieval.ingest import DocumentInput, ingest_documents

DOCS: list[DocumentInput] = [
    DocumentInput(
        source_type="policy",
        title="SLA Policy - Critical Incidents",
        content=(
            "P1-critical tickets (full outage, data loss, active security breach) must be "
            "acknowledged within 15 minutes and have an initial response within 1 hour. They are "
            "always escalated to the on-call engineer via the incident channel."
        ),
        metadata={"category": "security", "severity": "P1-critical"},
    ),
    DocumentInput(
        source_type="policy",
        title="SLA Policy - Standard Support",
        content=(
            "P2-high tickets get a 4 hour response SLA. P3-medium tickets get a 24 hour response "
            "SLA. P4-low tickets get a 72 hour response SLA. All SLAs are measured in business hours."
        ),
        metadata={"category": "general", "severity": "P2-high"},
    ),
    DocumentInput(
        source_type="runbook",
        title="Runbook - Billing Discrepancy",
        content=(
            "When a customer reports being charged incorrectly: 1) verify the invoice in the "
            "billing dashboard, 2) check for recent plan changes or proration, 3) if the charge is "
            "erroneous, issue a refund via Stripe and reply with the refund confirmation and ETA "
            "(3-5 business days)."
        ),
        metadata={"category": "billing"},
    ),
    DocumentInput(
        source_type="runbook",
        title="Runbook - Account Lockout",
        content=(
            "When a customer can't log in: 1) confirm identity via email + last invoice date, "
            "2) check for repeated failed logins triggering a lockout, 3) send a password reset "
            "link, 4) if 2FA device was lost, walk them through account-recovery verification."
        ),
        metadata={"category": "account_access"},
    ),
    DocumentInput(
        source_type="runbook",
        title="Runbook - API 500 Errors",
        content=(
            "When a customer reports intermittent 500s from the API: 1) check the status page and "
            "recent deploys, 2) pull error logs filtered by their API key, 3) if it's a known "
            "regression, link the incident and give an ETA; if isolated to their account, check "
            "rate limits and payload size."
        ),
        metadata={"category": "technical_bug"},
    ),
    DocumentInput(
        source_type="kb",
        title="KB - How to export your data",
        content=(
            "Customers can export their data from Settings > Data Export > Request Export. Exports "
            "are generated asynchronously and emailed as a download link within 30 minutes, valid "
            "for 7 days."
        ),
        metadata={"category": "how_to"},
    ),
    DocumentInput(
        source_type="kb",
        title="KB - Requesting a new integration",
        content=(
            "Integration requests go to the product backlog. We don't commit to timelines on "
            "feature requests, but customers can vote/track status on the public roadmap page."
        ),
        metadata={"category": "feature_request"},
    ),
    DocumentInput(
        source_type="ticket",
        title="Resolved - Customer charged twice for annual plan",
        content=(
            "Customer reported a duplicate charge after upgrading mid-cycle. Root cause: proration "
            "bug double-billed the annual difference. Resolved by refunding the duplicate charge "
            "and crediting one month. Category: billing. Severity: P3-medium."
        ),
        metadata={"category": "billing", "severity": "P3-medium"},
    ),
    DocumentInput(
        source_type="ticket",
        title="Resolved - Suspicious login attempts on account",
        content=(
            "Customer reported login attempts from unfamiliar locations. Investigated auth logs, "
            "confirmed credential-stuffing attempt, forced password reset and enabled 2FA, no "
            "account compromise confirmed. Category: security. Severity: P1-critical."
        ),
        metadata={"category": "security", "severity": "P1-critical"},
    ),
]


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = await ingest_documents(session, DOCS)
        print(f"Ingested {len(rows)} documents:")
        for row in rows:
            print(f"  - [{row.source_type}] {row.title} ({row.id})")


if __name__ == "__main__":
    asyncio.run(main())
