from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import admin, feedback, slack, tickets, triage
from app.observability import tracing  # noqa: F401 - import configures the OTel provider

app = FastAPI(
    title="Support-Ticket Triage Agent",
    description="Command A director agent + Embed v4 / Rerank 4 retrieval over historical tickets and docs.",
    version="0.1.0",
)

app.include_router(tickets.router)
app.include_router(triage.router)
app.include_router(feedback.router)
app.include_router(slack.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}
