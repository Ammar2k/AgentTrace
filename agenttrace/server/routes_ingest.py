import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agenttrace.server.db import get_db
from agenttrace.server.models import AgentExecution, Message, ToolCall, WorkflowRun
from agenttrace.server.schemas import (
    ExecutionCreate, ExecutionResponse, ExecutionUpdate,
    MessageCreate, MessageResponse,
    RunCreate, RunResponse, RunUpdate,
    ToolCallCreate, ToolCallResponse,
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
    run.total_tokens = body.total_tokens
    run.total_cost_usd = body.total_cost_usd
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
    execution.error = body.error
    execution.tokens_in = body.tokens_in
    execution.tokens_out = body.tokens_out
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
