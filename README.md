# AgentTrace

AgentTrace is a lightweight observability dashboard for multi-agent AI workflows.

It records workflow runs, agent executions, agent-to-agent messages, tool calls, token usage, estimated cost, retry metadata, and failures. The current implementation is intentionally small: a Python SDK, a FastAPI server, SQLite storage, and server-rendered dashboard pages.

## What You Can See

- Run history with status, tokens, and estimated cost
- Per-run execution timeline
- Per-agent summary with calls, failures, duration, tokens, and cost
- Agent communication graph
- Tool call arguments/results
- Structured failure details and tracebacks
- Failure groups by agent and error type
- Home-page metrics charts for cost and latency

## Quickstart

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the server:

```powershell
uvicorn agenttrace.server.main:app --reload
```

Open the dashboard:

```text
http://127.0.0.1:8000/
```

In a second terminal, populate the dashboard with demo runs:

```powershell
.\.venv\Scripts\Activate.ps1
python examples\research_pipeline.py --runs 10 --fail-rate 0.2
```

Then refresh the dashboard. You should see completed and failed runs, execution timelines, cost charts, communication data, and grouped failures at:

```text
http://127.0.0.1:8000/failures
```

## SDK Example

```python
from agenttrace import AgentTrace

tracer = AgentTrace(api_url="http://127.0.0.1:8000")

@tracer.trace_agent("researcher", model="demo-model")
def research(topic):
    tracer.log_tool_call(
        "web_search",
        arguments={"q": topic},
        result={"sources": ["paper-1", "paper-2"]},
    )
    return "notes", {
        "tokens_in": 120,
        "tokens_out": 45,
        "retry_count": 1,
    }

with tracer.trace_run("demo-run", metadata={"example": True}):
    notes = research("multi-agent observability")
    tracer.log_message("researcher", "writer", {"notes": notes})

tracer.close()
```

`retry_count` is optional metadata for workflows that already track retry attempts.

## Architecture

```text
Your agent workflow
      |
      v
AgentTrace SDK
      |
      v
FastAPI observability API
      |
      v
SQLite database
      |
      v
Server-rendered dashboard
```

The server owns pricing and cost calculation. The SDK reports facts such as model name, token counts, outputs, tool calls, messages, and exceptions.

## Pricing

Model prices live in:

```text
agenttrace/server/pricing.py
```

Prices are configured as USD per 1 million input/output tokens. Unknown models cost `0.0` so tracing continues even when pricing is incomplete.

## Development

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Reset the local dev database:

```powershell
Remove-Item .\agenttrace.db
```

The database is recreated automatically when the FastAPI app starts.

## Future Improvements

- Add configurable HTTP timeouts, logging, and a circuit breaker for unavailable servers.
- Make tracer run and execution state safe for concurrent threads and async tasks.
- Add sensitive-data redaction, capture controls, and payload-size limits.
- Make the database URL configurable and tune SQLite for concurrent ingestion.
- Validate statuses, token counts, and parent execution relationships at the API boundary.
- Add run pagination, database indexes, and retention or deletion tools for growing datasets.

## Dependencies

`requirements.txt` is kept deliberately small:

- FastAPI and Uvicorn for the API/server
- SQLAlchemy for SQLite persistence
- Pydantic for request/response schemas
- Jinja2 for dashboard templates
- HTTPX for the SDK client
- Pytest for tests
