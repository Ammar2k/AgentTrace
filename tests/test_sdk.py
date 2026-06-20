import pytest

from agenttrace import AgentTrace


class FakeClient:
    def __init__(self):
        self.calls = []
        self.run_count = 0
        self.execution_count = 0

    def create_run(self, name, metadata=None):
        self.run_count += 1
        run = {"id": f"run-{self.run_count}", "name": name}
        self.calls.append(("create_run", name, metadata))
        return run

    def finish_run(self, run_id, status, ended_at, total_tokens=0, total_cost_usd=0.0):
        self.calls.append(("finish_run", run_id, status))
        return {"id": run_id, "status": status}

    def create_execution(self, run_id, agent_name, model=None, parent_id=None, input=None):
        self.execution_count += 1
        execution = {"id": f"execution-{self.execution_count}"}
        self.calls.append(("create_execution", run_id, agent_name, model, parent_id, input))
        return execution

    def finish_execution(
        self,
        execution_id,
        status,
        ended_at,
        output=None,
        error=None,
        tokens_in=0,
        tokens_out=0,
        retry_count=0,
    ):
        self.calls.append(
            (
                "finish_execution",
                execution_id,
                status,
                output,
                error,
                tokens_in,
                tokens_out,
                retry_count,
            )
        )
        return {"id": execution_id, "status": status}

    def create_tool_call(
        self,
        execution_id,
        tool_name,
        arguments=None,
        result=None,
        status="completed",
        error=None,
        started_at=None,
        ended_at=None,
    ):
        self.calls.append(("create_tool_call", execution_id, tool_name, arguments, result, status, error))
        return {"id": "tool-call-1"}

    def create_message(self, run_id, from_agent, to_agent, content=None):
        self.calls.append(("create_message", run_id, from_agent, to_agent, content))
        return {"id": "message-1"}

    def close(self):
        self.calls.append(("close",))


class FailingClient:
    def create_run(self, name, metadata=None):
        raise ConnectionError("server down")

    def close(self):
        pass


def make_tracer(client):
    tracer = AgentTrace()
    tracer.client.close()
    tracer.client = client
    return tracer


def test_trace_agent_records_tokens_tool_call_and_message():
    client = FakeClient()
    tracer = make_tracer(client)

    @tracer.trace_agent("researcher", model="demo-model")
    def research(topic):
        tracer.log_tool_call("web_search", {"q": topic}, {"hits": 2})
        return "notes", {"tokens_in": 12, "tokens_out": 7}

    with tracer.trace_run("demo-run", metadata={"example": True}):
        result = research("agent tracing")
        tracer.log_message("researcher", "writer", {"notes": result})

    assert result == "notes"
    assert ("create_run", "demo-run", {"example": True}) in client.calls
    assert ("create_tool_call", "execution-1", "web_search", {"q": "agent tracing"}, {"hits": 2}, "completed", None) in client.calls
    assert ("create_message", "run-1", "researcher", "writer", {"notes": "notes"}) in client.calls
    assert ("finish_execution", "execution-1", "completed", {"result": "'notes'"}, None, 12, 7, 0) in client.calls
    assert ("finish_run", "run-1", "completed") in client.calls


def test_trace_agent_records_failure_and_reraises():
    client = FakeClient()
    tracer = make_tracer(client)

    @tracer.trace_agent("writer")
    def write():
        raise ValueError("bad draft")

    with pytest.raises(ValueError):
        with tracer.trace_run("failing-run"):
            write()

    finish_execution = [
        call for call in client.calls
        if call[0] == "finish_execution"
    ][0]
    assert finish_execution[2] == "failed"
    assert "Traceback (most recent call last)" in finish_execution[4]
    assert "ValueError: bad draft" in finish_execution[4]
    assert ("finish_run", "run-1", "failed") in client.calls


def test_server_unavailable_warns_once_and_does_not_crash(capsys):
    tracer = make_tracer(FailingClient())

    @tracer.trace_agent("offline-agent")
    def work():
        return "still ran"

    with tracer.trace_run("offline-run"):
        result = work()

    captured = capsys.readouterr()
    assert result == "still ran"
    assert captured.out.count("AgentTrace warning") == 1
