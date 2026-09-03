"""Metric implementations for the evaluation harness."""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

from sklearn.metrics import accuracy_score, f1_score

from app.cohere_client.client import extract_text


def classification_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, float]:
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
    }


def routing_accuracy(y_true: list[str], y_pred: list[str]) -> float:
    return accuracy_score(y_true, y_pred)


def escalation_accuracy(y_true: list[bool], y_pred: list[bool]) -> float:
    return accuracy_score(y_true, y_pred)


def recall_at_k(relevant_ids: list[str | None], retrieved_ids: list[list[str]]) -> float:
    """Fraction of cases (with a known relevant doc) where it appears anywhere in the retrieved set."""
    scored = [(rel, ret) for rel, ret in zip(relevant_ids, retrieved_ids, strict=True) if rel]
    if not scored:
        return 0.0
    hits = sum(1 for rel, ret in scored if rel in ret)
    return hits / len(scored)


def ndcg_at_k(relevant_ids: list[str | None], retrieved_ids: list[list[str]]) -> float:
    """NDCG assuming a single relevant document per case (ideal rank = 1)."""
    scores = []
    for rel, ret in zip(relevant_ids, retrieved_ids, strict=True):
        if not rel:
            continue
        if rel in ret:
            rank = ret.index(rel) + 1
            scores.append(1.0 / math.log2(rank + 1))
        else:
            scores.append(0.0)
    return sum(scores) / len(scores) if scores else 0.0


def tool_success_rate(audit_rows: list[Any]) -> float:
    if not audit_rows:
        return 1.0
    successes = sum(1 for r in audit_rows if r.success)
    return successes / len(audit_rows)


ChatFn = Callable[..., Awaitable[Any]]

_GROUNDEDNESS_PROMPT = """You are grading whether a support-agent reply is grounded in the \
provided context. Score from 0 to 1 how much of the reply's factual content is directly \
supported by the context (1 = fully grounded, 0 = entirely fabricated). A reply that honestly \
says it can't fully resolve the issue without inventing facts should score high.

Respond with ONLY a JSON object: {{"score": <float>}}

Context:
{context}

Reply:
{reply}"""


async def groundedness_score(chat_fn: ChatFn, draft: str, context_docs: list[str]) -> float:
    """LLM-as-judge groundedness score in [0, 1], using Command A as the judge."""
    if not draft.strip():
        return 0.0
    context_text = "\n\n".join(context_docs) or "(no context was provided to the drafting tool)"
    prompt = _GROUNDEDNESS_PROMPT.format(context=context_text, reply=draft)
    response = await chat_fn(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        data = json.loads(extract_text(response))
        return max(0.0, min(1.0, float(data.get("score", 0.0))))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0
