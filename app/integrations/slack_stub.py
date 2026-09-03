"""Slack integration surface.

Ticket ingestion and human-in-the-loop escalation approval would, in a real
deployment, run through a Slack app (Events API + bot token). Since no Slack
app is provisioned here, `Notifier` is the stable interface the rest of the
agent depends on; `LoggingNotifier` satisfies it by logging + recording
in-memory instead of calling the Slack Web API. `SlackWebNotifier` is a real
implementation that activates automatically once SLACK_BOT_TOKEN is set.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.agent.schemas import TicketInput
from app.config import get_settings

logger = logging.getLogger("integrations.slack")
settings = get_settings()


class Notifier(ABC):
    """Interface for posting a message to a human-facing channel (Slack, email, etc.)."""

    @abstractmethod
    async def notify(self, channel: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        """Returns True if the notification was delivered (or accepted for delivery)."""


class LoggingNotifier(Notifier):
    """Default stub notifier: logs and records messages instead of calling Slack."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def notify(self, channel: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        record = {"channel": channel, "text": text, "metadata": metadata or {}}
        self.sent_messages.append(record)
        logger.info("slack_stub.notify channel=%s text=%s", channel, text)
        return True


class SlackWebNotifier(Notifier):
    """Real Slack Web API notifier (chat.postMessage), used once a bot token is configured."""

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    async def notify(self, channel: str, text: str, metadata: dict[str, Any] | None = None) -> bool:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self._token}"},
                json={"channel": channel, "text": text},
            )
        ok = response.status_code == 200 and response.json().get("ok", False)
        if not ok:
            logger.warning("slack.notify failed: %s", response.text)
        return ok


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        _notifier = SlackWebNotifier(settings.slack_bot_token) if settings.slack_bot_token else LoggingNotifier()
    return _notifier


def parse_slack_event(payload: dict[str, Any]) -> TicketInput | None:
    """Best-effort mapping of a Slack `message` event into a new TicketInput.

    Real deployments would verify the request signature (SLACK_SIGNING_SECRET)
    before this is ever called; that verification lives in api/routes/slack.py.
    """
    event = payload.get("event", {})
    if event.get("type") != "message" or event.get("bot_id"):
        return None
    text = event.get("text", "").strip()
    if not text:
        return None
    return TicketInput(
        subject=text[:120],
        body=text,
        customer_id=event.get("user"),
        channel="slack",
    )
