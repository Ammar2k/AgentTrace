from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agenttrace.server.db import Base, get_db
from agenttrace.server.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def test_get_run_returns_nested_trace_data(client):
    run = client.post(
        "/api/runs",
        json={"name": "query-test", "metadata": {"source": "test"}},
    )
    run_id = run.json()["id"]

    execution = client.post(
        f"/api/runs/{run_id}/executions",
        json={
            "agent_name": "researcher",
            "model": "demo-model",
            "input": {"topic": "observability"},
        },
    )
    execution_id = execution.json()["id"]

    client.post(
        f"/api/executions/{execution_id}/tool-calls",
        json={
            "tool_name": "web_search",
            "arguments": {"q": "observability"},
            "result": {"hits": 2},
        },
    )
    client.post(
        f"/api/runs/{run_id}/messages",
        json={
            "from_agent": "researcher",
            "to_agent": "writer",
            "content": {"notes": "done"},
        },
    )
    client.patch(
        f"/api/executions/{execution_id}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "output": {"result": "done"},
            "tokens_in": 10,
            "tokens_out": 5,
        },
    )
    client.patch(
        f"/api/runs/{run_id}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "total_tokens": 15,
        },
    )

    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "query-test"
    assert body["metadata"] == {"source": "test"}
    assert body["total_tokens"] == 15
    assert body["executions"][0]["agent_name"] == "researcher"
    assert body["executions"][0]["input"] == {"topic": "observability"}
    assert body["executions"][0]["output"] == {"result": "done"}
    assert body["executions"][0]["tokens_in"] == 10
    assert body["executions"][0]["tokens_out"] == 5
    assert body["executions"][0]["tool_calls"][0]["tool_name"] == "web_search"
    assert body["executions"][0]["tool_calls"][0]["arguments"] == {"q": "observability"}
    assert body["messages"][0]["from_agent"] == "researcher"
    assert body["messages"][0]["to_agent"] == "writer"
    assert body["messages"][0]["content"] == {"notes": "done"}


def test_list_runs_returns_newest_first(client):
    first = client.post("/api/runs", json={"name": "first"}).json()
    second = client.post("/api/runs", json={"name": "second"}).json()

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert [run["id"] for run in response.json()] == [second["id"], first["id"]]


def test_get_run_returns_404_for_unknown_id(client):
    response = client.get("/api/runs/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_dashboard_home_renders_runs(client):
    client.post("/api/runs", json={"name": "dashboard-run"})

    response = client.get("/")

    assert response.status_code == 200
    assert "dashboard-run" in response.text
    assert "AgentTrace" in response.text


def test_dashboard_run_detail_renders_nested_trace_data(client):
    run = client.post("/api/runs", json={"name": "dashboard-detail"}).json()
    execution = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher"},
    ).json()
    client.post(
        f"/api/executions/{execution['id']}/tool-calls",
        json={"tool_name": "web_search"},
    )
    client.post(
        f"/api/runs/{run['id']}/messages",
        json={"from_agent": "researcher", "to_agent": "writer"},
    )

    response = client.get(f"/runs/{run['id']}")

    assert response.status_code == 200
    assert "dashboard-detail" in response.text
    assert "researcher" in response.text
    assert "web_search" in response.text
    assert "writer" in response.text


def test_dashboard_run_graph_groups_messages(client):
    run = client.post("/api/runs", json={"name": "graph-run"}).json()
    client.post(
        f"/api/runs/{run['id']}/messages",
        json={"from_agent": "researcher", "to_agent": "writer", "content": {"n": 1}},
    )
    client.post(
        f"/api/runs/{run['id']}/messages",
        json={"from_agent": "researcher", "to_agent": "writer", "content": {"n": 2}},
    )
    client.post(
        f"/api/runs/{run['id']}/messages",
        json={"from_agent": "planner", "to_agent": "researcher", "content": {"n": 3}},
    )

    response = client.get(f"/runs/{run['id']}/graph")

    assert response.status_code == 200
    assert "graph-run Communication" in response.text
    assert "researcher" in response.text
    assert "writer" in response.text
    assert "<td>2</td>" in response.text
    assert "planner" in response.text


def test_run_detail_includes_execution_timeline(client):
    run = client.post("/api/runs", json={"name": "timeline-run"}).json()
    first = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "planner"},
    ).json()
    second = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher", "parent_id": first["id"]},
    ).json()
    client.patch(
        f"/api/executions/{first['id']}",
        json={
            "status": "completed",
            "ended_at": "2026-06-28T10:00:02",
        },
    )
    client.patch(
        f"/api/executions/{second['id']}",
        json={
            "status": "completed",
            "ended_at": "2026-06-28T10:00:03",
        },
    )

    api_response = client.get(f"/api/runs/{run['id']}")
    page_response = client.get(f"/runs/{run['id']}")

    executions = api_response.json()["executions"]
    assert "timeline_left_percent" in executions[0]
    assert "timeline_width_percent" in executions[0]
    assert executions[1]["timeline_depth"] == 1
    assert page_response.status_code == 200
    assert "Timeline" in page_response.text
    assert "timeline-bar completed" in page_response.text
