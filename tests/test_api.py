from datetime import datetime
from time import sleep

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
            "total_tokens": 999,
            "total_cost_usd": 999,
        },
    )

    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "query-test"
    assert body["metadata"] == {"source": "test"}
    assert body["total_tokens"] == 15
    assert body["total_cost_usd"] == pytest.approx(0.00002)
    assert body["executions"][0]["agent_name"] == "researcher"
    assert body["executions"][0]["input"] == {"topic": "observability"}
    assert body["executions"][0]["output"] == {"result": "done"}
    assert body["executions"][0]["tokens_in"] == 10
    assert body["executions"][0]["tokens_out"] == 5
    assert body["executions"][0]["cost_usd"] == pytest.approx(0.00002)
    assert body["executions"][0]["tool_calls"][0]["tool_name"] == "web_search"
    assert body["executions"][0]["tool_calls"][0]["arguments"] == {"q": "observability"}
    assert body["messages"][0]["from_agent"] == "researcher"
    assert body["messages"][0]["to_agent"] == "writer"
    assert body["messages"][0]["content"] == {"notes": "done"}


def test_list_runs_returns_newest_first(client):
    first = client.post("/api/runs", json={"name": "first"}).json()
    sleep(0.001)
    second = client.post("/api/runs", json={"name": "second"}).json()

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert [run["id"] for run in response.json()] == [second["id"], first["id"]]


def test_get_run_returns_404_for_unknown_id(client):
    response = client.get("/api/runs/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_get_run_includes_agent_summary(client):
    run = client.post("/api/runs", json={"name": "summary-run"}).json()

    researcher_first = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher", "model": "demo-model"},
    ).json()
    researcher_second = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher", "model": "demo-model"},
    ).json()
    writer = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "writer", "model": "demo-model"},
    ).json()

    client.patch(
        f"/api/executions/{researcher_first['id']}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "tokens_in": 10,
            "tokens_out": 5,
        },
    )
    client.patch(
        f"/api/executions/{researcher_second['id']}",
        json={
            "status": "failed",
            "ended_at": datetime.utcnow().isoformat(),
            "tokens_in": 20,
            "tokens_out": 10,
        },
    )
    client.patch(
        f"/api/executions/{writer['id']}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "tokens_in": 100,
            "tokens_out": 50,
        },
    )

    response = client.get(f"/api/runs/{run['id']}")

    assert response.status_code == 200
    summary = {
        item["agent_name"]: item
        for item in response.json()["agent_summary"]
    }
    assert summary["researcher"]["calls"] == 2
    assert summary["researcher"]["failures"] == 1
    assert summary["researcher"]["tokens_in"] == 30
    assert summary["researcher"]["tokens_out"] == 15
    assert summary["researcher"]["total_tokens"] == 45
    assert summary["researcher"]["total_cost_usd"] == pytest.approx(0.00006)
    assert summary["writer"]["calls"] == 1
    assert summary["writer"]["total_tokens"] == 150
    assert summary["writer"]["total_cost_usd"] == pytest.approx(0.0002)


def test_finish_execution_stores_structured_error_fields(client):
    run = client.post("/api/runs", json={"name": "error-run"}).json()
    execution = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "writer", "model": "demo-model"},
    ).json()

    finish_response = client.patch(
        f"/api/executions/{execution['id']}",
        json={
            "status": "failed",
            "ended_at": datetime.utcnow().isoformat(),
            "error_type": "ValueError",
            "error_message": "bad draft",
            "error": "Traceback...\nValueError: bad draft",
            "retry_count": 1,
        },
    )
    run_response = client.get(f"/api/runs/{run['id']}")

    assert finish_response.status_code == 200
    body = run_response.json()
    failed_execution = body["executions"][0]
    assert failed_execution["status"] == "failed"
    assert failed_execution["error_type"] == "ValueError"
    assert failed_execution["error_message"] == "bad draft"
    assert failed_execution["error"] == "Traceback...\nValueError: bad draft"
    assert failed_execution["retry_count"] == 1


def test_dashboard_run_detail_renders_structured_error_and_retry_count(client):
    run = client.post("/api/runs", json={"name": "failed-detail"}).json()
    execution = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "writer", "model": "demo-model"},
    ).json()
    client.patch(
        f"/api/executions/{execution['id']}",
        json={
            "status": "failed",
            "ended_at": datetime.utcnow().isoformat(),
            "error_type": "ValueError",
            "error_message": "bad draft",
            "error": "Traceback...\nValueError: bad draft",
            "retry_count": 2,
        },
    )

    response = client.get(f"/runs/{run['id']}")

    assert response.status_code == 200
    assert "Retries" in response.text
    assert "<dd>2</dd>" in response.text
    assert "Error Summary" in response.text
    assert "ValueError" in response.text
    assert "bad draft" in response.text
    assert "Traceback..." in response.text


def test_failures_dashboard_groups_failed_executions(client):
    first_run = client.post("/api/runs", json={"name": "first-failure"}).json()
    second_run = client.post("/api/runs", json={"name": "second-failure"}).json()
    third_run = client.post("/api/runs", json={"name": "third-failure"}).json()

    first_writer = client.post(
        f"/api/runs/{first_run['id']}/executions",
        json={"agent_name": "writer", "model": "demo-model"},
    ).json()
    second_writer = client.post(
        f"/api/runs/{second_run['id']}/executions",
        json={"agent_name": "writer", "model": "demo-model"},
    ).json()
    critic = client.post(
        f"/api/runs/{third_run['id']}/executions",
        json={"agent_name": "critic", "model": "demo-model"},
    ).json()

    client.patch(
        f"/api/executions/{first_writer['id']}",
        json={
            "status": "failed",
            "ended_at": "2026-07-04T10:00:00",
            "error_type": "ValueError",
            "error_message": "first bad draft",
            "error": "Traceback...",
        },
    )
    client.patch(
        f"/api/executions/{second_writer['id']}",
        json={
            "status": "failed",
            "ended_at": "2026-07-04T10:05:00",
            "error_type": "ValueError",
            "error_message": "second bad draft",
            "error": "Traceback...",
        },
    )
    client.patch(
        f"/api/executions/{critic['id']}",
        json={
            "status": "failed",
            "ended_at": "2026-07-04T10:10:00",
            "error_type": "RuntimeError",
            "error_message": "review failed",
            "error": "Traceback...",
        },
    )

    response = client.get("/failures")

    assert response.status_code == 200
    assert "Failures" in response.text
    assert "writer" in response.text
    assert "ValueError" in response.text
    assert "<td>2</td>" in response.text
    assert "second bad draft" in response.text
    assert f"/runs/{second_run['id']}" in response.text
    assert "critic" in response.text
    assert "RuntimeError" in response.text
    assert "review failed" in response.text


def test_dashboard_home_renders_runs(client):
    run = client.post("/api/runs", json={"name": "dashboard-run"}).json()
    execution = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher", "model": "demo-model"},
    ).json()
    client.patch(
        f"/api/executions/{execution['id']}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "tokens_in": 10,
            "tokens_out": 5,
        },
    )
    client.patch(
        f"/api/runs/{run['id']}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "total_tokens": 999,
            "total_cost_usd": 999,
        },
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "dashboard-run" in response.text
    assert "AgentTrace" in response.text
    assert "Cost per Run" in response.text
    assert "Average Latency by Agent" in response.text
    assert "cost-chart" in response.text
    assert "latency-chart" in response.text
    assert '"labels": ["dashboard-run"]' in response.text
    assert '"values": [2e-05]' in response.text
    assert '"labels": ["researcher"]' in response.text


def test_dashboard_run_detail_renders_nested_trace_data(client):
    run = client.post("/api/runs", json={"name": "dashboard-detail"}).json()
    execution = client.post(
        f"/api/runs/{run['id']}/executions",
        json={"agent_name": "researcher", "model": "demo-model"},
    ).json()
    client.patch(
        f"/api/executions/{execution['id']}",
        json={
            "status": "completed",
            "ended_at": datetime.utcnow().isoformat(),
            "tokens_in": 10,
            "tokens_out": 5,
        },
    )
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
    assert "Agent Summary" in response.text
    assert "$0.000020" in response.text


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


def test_workflow_events_are_persisted_and_listed_chronologically(client):
    run = client.post("/api/runs", json={"name": "event-run"}).json()

    completed = client.post(
        f"/api/runs/{run['id']}/events",
        json={
            "event_type": "task.completed",
            "occurred_at": "2026-08-12T10:00:02",
            "task_id": "research",
            "idempotency_key": "research-completed",
            "payload": {"documents": 3},
        },
    )
    started = client.post(
        f"/api/runs/{run['id']}/events",
        json={
            "event_type": "task.started",
            "occurred_at": "2026-08-12T10:00:01",
            "task_id": "research",
            "idempotency_key": "research-started",
        },
    )

    response = client.get(f"/api/runs/{run['id']}/events")

    assert completed.status_code == 201
    assert started.status_code == 201
    assert response.status_code == 200
    assert [event["event_type"] for event in response.json()] == [
        "task.started",
        "task.completed",
    ]
    assert response.json()[1]["payload"] == {"documents": 3}


def test_workflow_events_support_causal_links_within_a_run(client):
    run = client.post("/api/runs", json={"name": "causal-run"}).json()
    parent = client.post(
        f"/api/runs/{run['id']}/events",
        json={"event_type": "action.failed", "task_id": "write"},
    ).json()

    recovery = client.post(
        f"/api/runs/{run['id']}/events",
        json={
            "event_type": "recovery.started",
            "task_id": "write",
            "parent_event_id": parent["id"],
            "causation_id": parent["id"],
        },
    )

    assert recovery.status_code == 201
    assert recovery.json()["parent_event_id"] == parent["id"]
    assert recovery.json()["causation_id"] == parent["id"]


def test_workflow_event_rejects_cross_run_causal_links(client):
    first_run = client.post("/api/runs", json={"name": "first"}).json()
    second_run = client.post("/api/runs", json={"name": "second"}).json()
    first_event = client.post(
        f"/api/runs/{first_run['id']}/events",
        json={"event_type": "task.started"},
    ).json()

    response = client.post(
        f"/api/runs/{second_run['id']}/events",
        json={
            "event_type": "task.completed",
            "parent_event_id": first_event["id"],
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "parent_event_id must reference an event in the same run",
    }


def test_workflow_event_rejects_unknown_run_and_event_type(client):
    missing_run = client.post(
        "/api/runs/missing/events",
        json={"event_type": "task.started"},
    )
    run = client.post("/api/runs", json={"name": "validation-run"}).json()
    invalid_type = client.post(
        f"/api/runs/{run['id']}/events",
        json={"event_type": "anything.happened"},
    )

    assert missing_run.status_code == 404
    assert missing_run.json() == {"detail": "Run not found"}
    assert invalid_type.status_code == 422


def test_workflow_event_idempotency_key_deduplicates_within_a_run(client):
    run = client.post("/api/runs", json={"name": "idempotent-run"}).json()
    payload = {
        "event_type": "task.started",
        "idempotency_key": "start-research",
    }

    first = client.post(f"/api/runs/{run['id']}/events", json=payload)
    duplicate = client.post(f"/api/runs/{run['id']}/events", json=payload)
    events = client.get(f"/api/runs/{run['id']}/events").json()

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert len(events) == 1


def test_workflow_events_have_no_mutation_endpoints(client):
    run = client.post("/api/runs", json={"name": "append-only-run"}).json()
    event = client.post(
        f"/api/runs/{run['id']}/events",
        json={"event_type": "workflow.stopped"},
    ).json()

    patch_response = client.patch(
        f"/api/runs/{run['id']}/events/{event['id']}",
        json={"event_type": "task.completed"},
    )
    delete_response = client.delete(f"/api/runs/{run['id']}/events/{event['id']}")

    assert patch_response.status_code == 404
    assert delete_response.status_code == 404
