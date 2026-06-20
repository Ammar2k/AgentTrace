from contextlib import contextmanager
from datetime import datetime
from functools import wraps
import traceback
from typing import Any, Callable

from agenttrace.sdk.client import AgentTraceClient


class AgentTrace:
    """User-facing tracer for recording agent workflows."""

    def __init__(self, api_url: str = "http://127.0.0.1:8000"):
        self.client = AgentTraceClient(api_url=api_url)
        self.current_run_id: str | None = None
        self.execution_stack: list[str] = []
        self._warned_unavailable = False

    @contextmanager
    def trace_run(self, name: str, metadata: dict[str, Any] | None = None):
        run = self._safe_call(self.client.create_run, name, metadata)
        previous_run_id = self.current_run_id
        previous_execution_stack = self.execution_stack

        self.current_run_id = run["id"] if run else None
        self.execution_stack = []

        try:
            yield
        except Exception:
            if self.current_run_id:
                self._safe_call(
                    self.client.finish_run,
                    self.current_run_id,
                    "failed",
                    datetime.utcnow(),
                )
            raise
        else:
            if self.current_run_id:
                self._safe_call(
                    self.client.finish_run,
                    self.current_run_id,
                    "completed",
                    datetime.utcnow(),
                )
        finally:
            self.current_run_id = previous_run_id
            self.execution_stack = previous_execution_stack

    def trace_agent(self, agent_name: str, model: str | None = None):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                execution = None
                if self.current_run_id:
                    execution = self._safe_call(
                        self.client.create_execution,
                        self.current_run_id,
                        agent_name,
                        model,
                        self._current_execution_id(),
                        _summarize_call(args, kwargs),
                    )

                execution_id = execution["id"] if execution else None
                if execution_id:
                    self.execution_stack.append(execution_id)

                try:
                    raw_result = func(*args, **kwargs)
                except Exception as exc:
                    if execution_id:
                        self._safe_call(
                            self.client.finish_execution,
                            execution_id,
                            "failed",
                            datetime.utcnow(),
                            error=traceback.format_exc(),
                        )
                    raise
                else:
                    result, usage = _split_result_and_usage(raw_result)
                    if execution_id:
                        self._safe_call(
                            self.client.finish_execution,
                            execution_id,
                            "completed",
                            datetime.utcnow(),
                            output={"result": repr(result)},
                            tokens_in=usage["tokens_in"],
                            tokens_out=usage["tokens_out"],
                        )
                    return result
                finally:
                    if execution_id:
                        self.execution_stack.pop()

            return wrapper

        return decorator

    def log_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        status: str = "completed",
        error: str | None = None,
    ):
        execution_id = self._current_execution_id()
        if not execution_id:
            return

        now = datetime.utcnow()
        self._safe_call(
            self.client.create_tool_call,
            execution_id,
            tool_name,
            arguments,
            result,
            status,
            error,
            now,
            now,
        )

    def log_message(
        self,
        from_agent: str,
        to_agent: str,
        content: dict[str, Any] | None = None,
    ):
        if not self.current_run_id:
            return

        self._safe_call(
            self.client.create_message,
            self.current_run_id,
            from_agent,
            to_agent,
            content,
        )

    def close(self):
        self.client.close()

    def _current_execution_id(self) -> str | None:
        if not self.execution_stack:
            return None
        return self.execution_stack[-1]

    def _safe_call(self, func: Callable, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not self._warned_unavailable:
                print(f"AgentTrace warning: could not send trace data ({exc})")
                self._warned_unavailable = True
            return None


def _summarize_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "args": [repr(arg) for arg in args],
        "kwargs": {key: repr(value) for key, value in kwargs.items()},
    }


def _split_result_and_usage(result: Any) -> tuple[Any, dict[str, int]]:
    if _looks_like_usage_result(result):
        value, usage = result
        return value, {
            "tokens_in": int(usage.get("tokens_in", 0)),
            "tokens_out": int(usage.get("tokens_out", 0)),
        }

    return result, {"tokens_in": 0, "tokens_out": 0}


def _looks_like_usage_result(result: Any) -> bool:
    return (
        isinstance(result, tuple)
        and len(result) == 2
        and isinstance(result[1], dict)
        and ("tokens_in" in result[1] or "tokens_out" in result[1])
    )
