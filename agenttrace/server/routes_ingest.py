import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agenttrace.server.db import get_db
from agenttrace.server.models import AgentExecution, Message, ToolCall, WorkflowEvent, WorkflowRun
from agenttrace.server.pricing import cost_of
from agenttrace.server.schemas import (
    ExecutionCreate, ExecutionResponse, ExecutionUpdate,
    MessageCreate, MessageResponse,
    RunCreate, RunResponse, RunUpdate,
    ToolCallCreate, ToolCallResponse,
    WorkflowEventCreate, WorkflowEventResponse,
)

router = APIRouter(prefix="/api")


# --- WorkflowRun ---

@router.post("/runs", response_model=RunResponse, status_code=201)
def create_run(body: RunCreate, db: Session = Depends(get_db)):
    run = WorkflowRun(
        name=body.name,
        metadata_=json.dumps(body.metadata),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.patch("/runs/{run_id}", response_model=RunResponse)
def finish_run(run_id: str, body: RunUpdate, db: Session = Depends(get_db)):
    run = db.get(WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = body.status
    run.ended_at = body.ended_at
    run.total_tokens = sum(execution.tokens_in + execution.tokens_out for execution in run.executions)
    run.total_cost_usd = sum(execution.cost_usd for execution in run.executions)
    db.commit()
    db.refresh(run)
    return run


# --- AgentExecution ---

@router.post("/runs/{run_id}/executions", response_model=ExecutionResponse, status_code=201)
def create_execution(run_id: str, body: ExecutionCreate, db: Session = Depends(get_db)):
    if not db.get(WorkflowRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    execution = AgentExecution(
        run_id=run_id,
        parent_id=body.parent_id,
        agent_name=body.agent_name,
        model=body.model,
        input_=json.dumps(body.input) if body.input is not None else None,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


@router.patch("/executions/{execution_id}", response_model=ExecutionResponse)
def finish_execution(execution_id: str, body: ExecutionUpdate, db: Session = Depends(get_db)):
    execution = db.get(AgentExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    execution.status = body.status
    execution.ended_at = body.ended_at
    execution.output = json.dumps(body.output) if body.output is not None else None
    execution.error_type = body.error_type
    execution.error_message = body.error_message
    execution.error = body.error
    execution.tokens_in = body.tokens_in
    execution.tokens_out = body.tokens_out
    execution.cost_usd = cost_of(execution.model, body.tokens_in, body.tokens_out)
    execution.retry_count = body.retry_count
    db.commit()
    db.refresh(execution)
    return execution


# --- ToolCall ---

@router.post("/executions/{execution_id}/tool-calls", response_model=ToolCallResponse, status_code=201)
def create_tool_call(execution_id: str, body: ToolCallCreate, db: Session = Depends(get_db)):
    if not db.get(AgentExecution, execution_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    tool_call = ToolCall(
        execution_id=execution_id,
        tool_name=body.tool_name,
        arguments=json.dumps(body.arguments) if body.arguments is not None else None,
        result=json.dumps(body.result) if body.result is not None else None,
        status=body.status,
        error=body.error,
        started_at=body.started_at,
        ended_at=body.ended_at,
    )
    db.add(tool_call)
    db.commit()
    db.refresh(tool_call)
    return tool_call


# --- Message ---

@router.post("/runs/{run_id}/messages", response_model=MessageResponse, status_code=201)
def create_message(run_id: str, body: MessageCreate, db: Session = Depends(get_db)):
    if not db.get(WorkflowRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    message = Message(
        run_id=run_id,
        from_agent=body.from_agent,
        to_agent=body.to_agent,
        content=json.dumps(body.content) if body.content is not None else None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# --- WorkflowEvent ---

@router.post("/runs/{run_id}/events", response_model=WorkflowEventResponse, status_code=201)
def create_workflow_event(
    run_id: str,
    body: WorkflowEventCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    if not db.get(WorkflowRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    existing_event = _event_by_idempotency_key(db, run_id, body.idempotency_key)
    if existing_event is not None:
        response.status_code = 200
        return _workflow_event_response(existing_event)

    _validate_event_reference(db, run_id, body.parent_event_id, "parent_event_id")
    _validate_event_reference(db, run_id, body.causation_id, "causation_id")

    event = WorkflowEvent(
        run_id=run_id,
        event_type=body.event_type,
        occurred_at=body.occurred_at,
        task_id=body.task_id,
        parent_event_id=body.parent_event_id,
        causation_id=body.causation_id,
        idempotency_key=body.idempotency_key,
        payload_=json.dumps(body.payload),
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_event = _event_by_idempotency_key(db, run_id, body.idempotency_key)
        if existing_event is None:
            raise
        response.status_code = 200
        return _workflow_event_response(existing_event)
    db.refresh(event)
    return _workflow_event_response(event)


def _validate_event_reference(
    db: Session,
    run_id: str,
    event_id: str | None,
    field_name: str,
) -> None:
    if event_id is None:
        return

    event = db.get(WorkflowEvent, event_id)
    if event is None:
        raise HTTPException(status_code=422, detail=f"{field_name} does not reference an event")
    if event.run_id != run_id:
        raise HTTPException(status_code=422, detail=f"{field_name} must reference an event in the same run")


def _event_by_idempotency_key(
    db: Session,
    run_id: str,
    idempotency_key: str | None,
) -> WorkflowEvent | None:
    if idempotency_key is None:
        return None
    return (
        db.query(WorkflowEvent)
        .filter(
            WorkflowEvent.run_id == run_id,
            WorkflowEvent.idempotency_key == idempotency_key,
        )
        .first()
    )


def _workflow_event_response(event: WorkflowEvent) -> dict:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "task_id": event.task_id,
        "parent_event_id": event.parent_event_id,
        "causation_id": event.causation_id,
        "idempotency_key": event.idempotency_key,
        "payload": json.loads(event.payload_),
    }
