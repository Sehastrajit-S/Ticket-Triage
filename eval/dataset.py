"""Synthetic labeled tickets covering the full taxonomy, used by the eval harness.

`relevant_doc_title` must match a title in scripts/seed_data.py exactly — the
harness resolves it to a Document id at run time to score retrieval quality.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LabeledTicket:
    subject: str
    body: str
    expected_severity: str
    expected_category: str
    expected_team: str
    expected_escalated: bool
    relevant_doc_title: str | None = None


DATASET: list[LabeledTicket] = [
    LabeledTicket(
        subject="Production API completely down",
        body=(
            "All requests to api.ourapp.com are returning 503 errors. This is affecting all of "
            "our customers right now and we need this fixed immediately."
        ),
        expected_severity="P1-critical",
        expected_category="technical_bug",
        expected_team="engineering_support_escalation",
        expected_escalated=True,
        relevant_doc_title="Runbook - API 500 Errors",
    ),
    LabeledTicket(
        subject="Charged twice this month",
        body=(
            "I upgraded my plan mid-month and got billed twice for the difference. Please refund "
            "the duplicate charge."
        ),
        expected_severity="P3-medium",
        expected_category="billing",
        expected_team="billing_support",
        expected_escalated=False,
        relevant_doc_title="Runbook - Billing Discrepancy",
    ),
    LabeledTicket(
        subject="Can't log into my account",
        body="I've tried resetting my password three times and I'm still locked out of my account.",
        expected_severity="P2-high",
        expected_category="account_access",
        expected_team="account_support",
        expected_escalated=False,
        relevant_doc_title="Runbook - Account Lockout",
    ),
    LabeledTicket(
        subject="Suspicious login attempts",
        body=(
            "I'm getting emails about login attempts from countries I've never been to. I think "
            "someone is trying to break into my account."
        ),
        expected_severity="P1-critical",
        expected_category="security",
        expected_team="security_team",
        expected_escalated=True,
        relevant_doc_title="Resolved - Suspicious login attempts on account",
    ),
    LabeledTicket(
        subject="How do I export my data?",
        body="I need to download all of my account data for a compliance audit. What's the process?",
        expected_severity="P4-low",
        expected_category="how_to",
        expected_team="general_support",
        expected_escalated=False,
        relevant_doc_title="KB - How to export your data",
    ),
    LabeledTicket(
        subject="Feature request: Salesforce integration",
        body="Would love to see a native Salesforce integration added to the product roadmap.",
        expected_severity="P4-low",
        expected_category="feature_request",
        expected_team="product_backlog",
        expected_escalated=False,
        relevant_doc_title="KB - Requesting a new integration",
    ),
]
