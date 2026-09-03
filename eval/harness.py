"""Runs the labeled dataset end-to-end through the director agent and reports metrics:
classification accuracy/F1, routing accuracy, retrieval Recall@K/NDCG@K, response
groundedness, escalation accuracy, tool success rate, and latency.

Usage: python -m eval.harness
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from statistics import mean

from sqlalchemy import select

from app.agent.director import run_triage
from app.cohere_client.client import chat
from app.db.models import AuditLog, Document, EvalRun, Ticket
from app.db.session import AsyncSessionLocal
from eval.dataset import DATASET
from eval.metrics import (
    classification_metrics,
    escalation_accuracy,
    groundedness_score,
    ndcg_at_k,
    recall_at_k,
    routing_accuracy,
    tool_success_rate,
)


async def _resolve_doc_id(session, title: str | None) -> str | None:
    if not title:
        return None
    row = (await session.execute(select(Document).where(Document.title == title))).scalar_one_or_none()
    return str(row.id) if row else None


async def run_eval() -> dict:
    started_wall = time.perf_counter()
    started_at = datetime.now(UTC)

    async with AsyncSessionLocal() as session:
        y_true_severity: list[str] = []
        y_pred_severity: list[str] = []
        y_true_category: list[str] = []
        y_pred_category: list[str] = []
        y_true_team: list[str] = []
        y_pred_team: list[str] = []
        y_true_escalated: list[bool] = []
        y_pred_escalated: list[bool] = []
        relevant_ids: list[str | None] = []
        retrieved_ids_per_case: list[list[str]] = []
        groundedness_scores: list[float] = []
        latencies: list[int] = []

        for case in DATASET:
            ticket = Ticket(subject=case.subject, body=case.body, channel="eval")
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)

            result = await run_triage(session, ticket)

            y_true_severity.append(case.expected_severity)
            y_pred_severity.append(result.severity.value)
            y_true_category.append(case.expected_category)
            y_pred_category.append(result.category.value)
            y_true_team.append(case.expected_team)
            y_pred_team.append(result.routed_team)
            y_true_escalated.append(case.expected_escalated)
            y_pred_escalated.append(result.escalated)
            latencies.append(result.latency_ms)

            relevant_ids.append(await _resolve_doc_id(session, case.relevant_doc_title))
            retrieved_ids_per_case.append(result.retrieved_doc_ids)

            context_docs: list[str] = []
            if result.retrieved_doc_ids:
                rows = (
                    (await session.execute(select(Document).where(Document.id.in_(result.retrieved_doc_ids))))
                    .scalars()
                    .all()
                )
                context_docs = [d.content for d in rows]
            groundedness_scores.append(await groundedness_score(chat, result.draft_response, context_docs))

        audit_rows = (await session.execute(select(AuditLog))).scalars().all()

        severity_metrics = classification_metrics(y_true_severity, y_pred_severity)
        category_metrics = classification_metrics(y_true_category, y_pred_category)
        sorted_latencies = sorted(latencies)
        p95_index = min(len(sorted_latencies) - 1, int(len(sorted_latencies) * 0.95))

        metrics = {
            "n_cases": len(DATASET),
            "severity_accuracy": severity_metrics["accuracy"],
            "severity_f1_macro": severity_metrics["f1_macro"],
            "category_accuracy": category_metrics["accuracy"],
            "category_f1_macro": category_metrics["f1_macro"],
            "routing_accuracy": routing_accuracy(y_true_team, y_pred_team),
            "escalation_accuracy": escalation_accuracy(y_true_escalated, y_pred_escalated),
            "retrieval_recall_at_k": recall_at_k(relevant_ids, retrieved_ids_per_case),
            "retrieval_ndcg_at_k": ndcg_at_k(relevant_ids, retrieved_ids_per_case),
            "groundedness_mean": mean(groundedness_scores) if groundedness_scores else 0.0,
            "tool_success_rate": tool_success_rate(audit_rows),
            "latency_ms_mean": mean(latencies) if latencies else 0.0,
            "latency_ms_p95": sorted_latencies[p95_index] if sorted_latencies else 0.0,
            "wall_clock_seconds": round(time.perf_counter() - started_wall, 2),
        }

        session.add(
            EvalRun(
                dataset_version="v1",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                metrics=metrics,
            )
        )
        await session.commit()

    return metrics


def _print_report(metrics: dict) -> None:
    print("\n=== Ticket Triage Agent — Evaluation Report ===")
    for key, value in metrics.items():
        formatted = f"{value:.3f}" if isinstance(value, float) else str(value)
        print(f"  {key:26s}: {formatted}")


async def main() -> None:
    metrics = await run_eval()
    _print_report(metrics)


if __name__ == "__main__":
    asyncio.run(main())
