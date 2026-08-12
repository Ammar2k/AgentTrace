import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from agenttrace.server.db import get_db
from agenttrace.server.models import AgentExecution, WorkflowEvent, WorkflowRun
from agenttrace.server.schemas import RunDetailResponse, RunResponse, WorkflowEventResponse

router = APIRouter(prefix="/api")
dashboard_router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/runs", response_model=list[RunResponse])
def list_runs(db: Session = Depends(get_db)):
    return (
        db.query(WorkflowRun)
        .order_by(WorkflowRun.started_at.desc())
        .all()
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return _run_detail(run)


@router.get("/runs/{run_id}/events", response_model=list[WorkflowEventResponse])
def list_workflow_events(run_id: str, db: Session = Depends(get_db)):
    if not db.get(WorkflowRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    events = (
        db.query(WorkflowEvent)
        .filter(WorkflowEvent.run_id == run_id)
        .order_by(WorkflowEvent.occurred_at.asc(), WorkflowEvent.id.asc())
        .all()
    )
    return [
        {
            "id": event.id,
            "run_id": event.run_id,
            "event_type": event.event_type,
            "occurred_at": event.occurred_at,
            "task_id": event.task_id,
            "parent_event_id": event.parent_event_id,
            "causation_id": event.causation_id,
            "idempotency_key": event.idempotency_key,
            "payload": _load_json(event.payload_) or {},
        }
        for event in events
    ]


@dashboard_router.get("/")
def dashboard_home(request: Request, db: Session = Depends(get_db)):
    runs = (
        db.query(WorkflowRun)
        .order_by(WorkflowRun.started_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "runs": runs,
            "cost_chart": _cost_chart(runs),
            "latency_chart": _latency_chart(runs),
        },
    )


@dashboard_router.get("/runs/{run_id}")
def dashboard_run_detail(run_id: str, request: Request, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": _run_detail(run),
        },
    )


@dashboard_router.get("/failures")
def dashboard_failures(request: Request, db: Session = Depends(get_db)):
    failed_executions = (
        db.query(AgentExecution)
        .filter(AgentExecution.status == "failed")
        .order_by(AgentExecution.ended_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "failures.html",
        {
            "failure_groups": _failure_groups(failed_executions),
        },
    )


@dashboard_router.get("/runs/{run_id}/graph")
def dashboard_run_graph(run_id: str, request: Request, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return templates.TemplateResponse(
        request,
        "run_graph.html",
        {
            "run": _run_detail(run),
            "message_edges": _message_edges(run),
        },
    )


def _run_detail(run: WorkflowRun) -> dict[str, Any]:
    executions = [
        {
            "id": execution.id,
            "run_id": execution.run_id,
            "parent_id": execution.parent_id,
            "agent_name": execution.agent_name,
            "model": execution.model,
            "status": execution.status,
            "started_at": execution.started_at,
            "ended_at": execution.ended_at,
            "tokens_in": execution.tokens_in,
            "tokens_out": execution.tokens_out,
            "cost_usd": execution.cost_usd,
            "input": _load_json(execution.input_),
            "output": _load_json(execution.output),
            "error_type": execution.error_type,
            "error_message": execution.error_message,
            "error": execution.error,
            "retry_count": execution.retry_count,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "execution_id": tool_call.execution_id,
                    "tool_name": tool_call.tool_name,
                    "status": tool_call.status,
                    "started_at": tool_call.started_at,
                    "ended_at": tool_call.ended_at,
                    "arguments": _load_json(tool_call.arguments),
                    "result": _load_json(tool_call.result),
                    "error": tool_call.error,
                }
                for tool_call in sorted(execution.tool_calls, key=lambda item: item.started_at)
            ],
        }
        for execution in sorted(run.executions, key=lambda item: item.started_at)
    ]
    _add_timeline_fields(executions)

    return {
        "id": run.id,
        "name": run.name,
        "status": run.status,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "total_tokens": run.total_tokens,
        "total_cost_usd": run.total_cost_usd,
        "metadata": _load_json(run.metadata_),
        "executions": executions,
        "agent_summary": _agent_summary(executions),
        "messages": [
            {
                "id": message.id,
                "run_id": message.run_id,
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "timestamp": message.timestamp,
                "content": _load_json(message.content),
            }
            for message in sorted(run.messages, key=lambda item: item.timestamp)
        ],
    }


def _load_json(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return json.loads(value)


def _add_timeline_fields(executions: list[dict[str, Any]]) -> None:
    if not executions:
        return

    start = min(execution["started_at"] for execution in executions)
    end = max((execution["ended_at"] or execution["started_at"]) for execution in executions)
    total_seconds = max((end - start).total_seconds(), 0.001)

    for execution in executions:
        execution_end = execution["ended_at"] or execution["started_at"]
        duration_seconds = max((execution_end - execution["started_at"]).total_seconds(), 0.0)
        execution["duration_seconds"] = duration_seconds
        execution["timeline_left_percent"] = ((execution["started_at"] - start).total_seconds() / total_seconds) * 100
        execution["timeline_width_percent"] = max((duration_seconds / total_seconds) * 100, 1.0)
        execution["timeline_depth"] = _execution_depth(execution, executions)


def _execution_depth(execution: dict[str, Any], executions: list[dict[str, Any]]) -> int:
    by_id = {item["id"]: item for item in executions}
    depth = 0
    parent_id = execution["parent_id"]

    while parent_id in by_id:
        depth += 1
        parent_id = by_id[parent_id]["parent_id"]

    return depth


def _agent_summary(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_agent: dict[str, dict[str, Any]] = {}

    for execution in executions:
        agent_name = execution["agent_name"]
        if agent_name not in by_agent:
            by_agent[agent_name] = {
                "agent_name": agent_name,
                "calls": 0,
                "failures": 0,
                "total_duration_seconds": 0.0,
                "total_tokens": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "total_cost_usd": 0.0,
            }

        summary = by_agent[agent_name]
        summary["calls"] += 1
        summary["failures"] += 1 if execution["status"] == "failed" else 0
        summary["total_duration_seconds"] += execution["duration_seconds"]
        summary["tokens_in"] += execution["tokens_in"]
        summary["tokens_out"] += execution["tokens_out"]
        summary["total_tokens"] += execution["tokens_in"] + execution["tokens_out"]
        summary["total_cost_usd"] += execution["cost_usd"]

    return sorted(
        by_agent.values(),
        key=lambda summary: (-summary["total_cost_usd"], summary["agent_name"]),
    )


def _cost_chart(runs: list[WorkflowRun]) -> dict[str, list[Any]]:
    ordered_runs = sorted(runs, key=lambda run: run.started_at)

    return {
        "labels": [run.name for run in ordered_runs],
        "values": [run.total_cost_usd for run in ordered_runs],
    }


def _latency_chart(runs: list[WorkflowRun]) -> dict[str, list[Any]]:
    by_agent: dict[str, dict[str, float | int]] = {}

    for run in runs:
        for execution in run.executions:
            if execution.ended_at is None:
                continue

            duration_seconds = max((execution.ended_at - execution.started_at).total_seconds(), 0.0)
            if execution.agent_name not in by_agent:
                by_agent[execution.agent_name] = {
                    "total_duration_seconds": 0.0,
                    "calls": 0,
                }

            by_agent[execution.agent_name]["total_duration_seconds"] += duration_seconds
            by_agent[execution.agent_name]["calls"] += 1

    summaries = [
        {
            "agent_name": agent_name,
            "average_duration_seconds": values["total_duration_seconds"] / values["calls"],
        }
        for agent_name, values in by_agent.items()
        if values["calls"] > 0
    ]
    summaries.sort(key=lambda summary: (-summary["average_duration_seconds"], summary["agent_name"]))

    return {
        "labels": [summary["agent_name"] for summary in summaries],
        "values": [summary["average_duration_seconds"] for summary in summaries],
    }


def _failure_groups(executions: list[AgentExecution]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for execution in executions:
        error_type = execution.error_type or "UnknownError"
        key = (execution.agent_name, error_type)
        ended_at = execution.ended_at or execution.started_at

        if key not in groups:
            groups[key] = {
                "agent_name": execution.agent_name,
                "error_type": error_type,
                "count": 0,
                "last_seen": ended_at,
                "latest_error_message": execution.error_message or "",
                "latest_run_id": execution.run_id,
            }

        group = groups[key]
        group["count"] += 1
        if ended_at >= group["last_seen"]:
            group["last_seen"] = ended_at
            group["latest_error_message"] = execution.error_message or ""
            group["latest_run_id"] = execution.run_id

    return sorted(
        groups.values(),
        key=lambda group: (-group["count"], group["agent_name"], group["error_type"]),
    )


def _message_edges(run: WorkflowRun) -> list[dict[str, Any]]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for message in run.messages:
        key = (message.from_agent, message.to_agent)
        if key not in edges:
            edges[key] = {
                "from_agent": message.from_agent,
                "to_agent": message.to_agent,
                "count": 0,
                "last_message_at": message.timestamp,
            }
        edges[key]["count"] += 1
        if message.timestamp > edges[key]["last_message_at"]:
            edges[key]["last_message_at"] = message.timestamp

    return sorted(
        edges.values(),
        key=lambda edge: (-edge["count"], edge["from_agent"], edge["to_agent"]),
    )
