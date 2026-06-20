from datetime import datetime
from typing import Any

import httpx


class AgentTraceClient:
    """Small HTTP client for the AgentTrace ingestion API."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000", timeout: float = 5.0):
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(base_url=self.api_url, timeout=timeout)

    def close(self):
        self._client.close()

    def create_run(self, name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._post(
            "/api/runs",
            {
                "name": name,
                "metadata": metadata or {},
            },
        )

    def finish_run(
        self,
        run_id: str,
        status: str,
        ended_at: datetime,
        total_tokens: int = 0,
        total_cost_usd: float = 0.0,
    ) -> dict[str, Any]:
        return self._patch(
            f"/api/runs/{run_id}",
            {
                "status": status,
                "ended_at": ended_at,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost_usd,
            },
        )

    def create_execution(
        self,
        run_id: str,
        agent_name: str,
        model: str | None = None,
        parent_id: str | None = None,
        input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/runs/{run_id}/executions",
            {
                "agent_name": agent_name,
                "model": model,
                "parent_id": parent_id,
                "input": input,
            },
        )

    def finish_execution(
        self,
        execution_id: str,
        status: str,
        ended_at: datetime,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        return self._patch(
            f"/api/executions/{execution_id}",
            {
                "status": status,
                "ended_at": ended_at,
                "output": output,
                "error": error,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "retry_count": retry_count,
            },
        )

    def create_tool_call(
        self,
        execution_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        status: str = "completed",
        error: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/executions/{execution_id}/tool-calls",
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                "status": status,
                "error": error,
                "started_at": started_at,
                "ended_at": ended_at,
            },
        )

    def create_message(
        self,
        run_id: str,
        from_agent: str,
        to_agent: str,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/runs/{run_id}/messages",
            {
                "from_agent": from_agent,
                "to_agent": to_agent,
                "content": content,
            },
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, json=_json_ready(payload))
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.patch(path, json=_json_ready(payload))
        response.raise_for_status()
        return response.json()


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
