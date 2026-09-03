import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes.triage as triage_route
from app.agent.schemas import Category, Severity, TriageResult
from app.db.session import get_session
from app.main import app


class _FakeSession:
    """Minimal in-memory stand-in for AsyncSession, enough for the ticket/triage routes."""

    def __init__(self):
        self._store: list = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(UTC)
        if getattr(obj, "status", None) is None:
            obj.status = "open"
        self._store.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def get(self, model, obj_id):
        for obj in self._store:
            if isinstance(obj, model) and str(obj.id) == str(obj_id):
                return obj
        return None


@pytest.fixture
def fake_session():
    return _FakeSession()


@pytest.fixture(autouse=True)
def override_session(fake_session):
    async def _get_session():
        yield fake_session

    app.dependency_overrides[get_session] = _get_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_and_fetch_ticket():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/tickets", json={"subject": "Can't log in", "body": "help please"})
        assert resp.status_code == 201
        ticket_id = resp.json()["id"]

        resp2 = await client.get(f"/tickets/{ticket_id}")
        assert resp2.status_code == 200
        assert resp2.json()["subject"] == "Can't log in"


@pytest.mark.asyncio
async def test_get_ticket_404_for_unknown_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/tickets/{uuid.uuid4()}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_triage_endpoint_delegates_to_orchestrator(monkeypatch):
    fake_result = TriageResult(
        ticket_id="00000000-0000-0000-0000-000000000000",
        severity=Severity.P3_MEDIUM,
        category=Category.OTHER,
        routed_team="general_support",
        confidence=0.5,
        rationale="ok",
        draft_response="hi",
        retrieved_doc_ids=[],
        tool_trace=[],
        escalated=False,
    )

    class _FakeOrchestrator:
        async def handle_new_ticket(self, session, ticket):
            return fake_result

    monkeypatch.setattr(triage_route, "get_orchestrator", lambda: _FakeOrchestrator())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/tickets", json={"subject": "s", "body": "b"})
        ticket_id = create_resp.json()["id"]

        run_resp = await client.post(f"/triage/{ticket_id}/run")
        assert run_resp.status_code == 200
        assert run_resp.json()["routed_team"] == "general_support"


@pytest.mark.asyncio
async def test_run_triage_endpoint_404_for_unknown_ticket(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/triage/{uuid.uuid4()}/run")
        assert resp.status_code == 404
