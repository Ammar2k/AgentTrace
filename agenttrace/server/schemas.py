from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- WorkflowRun ---

class RunCreate(BaseModel):
    name: str
    metadata: dict[str, Any] = {}

class RunUpdate(BaseModel):
    status: str  # completed | failed
    ended_at: datetime
    total_tokens: int = 0
    total_cost_usd: float = 0.0

class RunResponse(BaseModel):
    id: str
    name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    total_tokens: int
    total_cost_usd: float

    model_config = {"from_attributes": True}

class RunDetailResponse(RunResponse):
    metadata: dict[str, Any] | None = None
    executions: list["ExecutionDetailResponse"] = Field(default_factory=list)
    messages: list["MessageDetailResponse"] = Field(default_factory=list)


# --- AgentExecution ---

class ExecutionCreate(BaseModel):
    agent_name: str
    model: str | None = None
    parent_id: str | None = None  # set if this agent was called by another agent
    input: dict[str, Any] | None = None

class ExecutionUpdate(BaseModel):
    status: str  # completed | failed
    ended_at: datetime
    output: dict[str, Any] | None = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    retry_count: int = 0

class ExecutionResponse(BaseModel):
    id: str
    run_id: str
    parent_id: str | None
    agent_name: str
    model: str | None
    status: str
    started_at: datetime
    ended_at: datetime | None
    tokens_in: int
    tokens_out: int

    model_config = {"from_attributes": True}

class ExecutionDetailResponse(ExecutionResponse):
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int
    tool_calls: list["ToolCallDetailResponse"] = Field(default_factory=list)


# --- ToolCall ---

class ToolCallCreate(BaseModel):
    tool_name: str
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    status: str = "completed"  # completed | failed
    error: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

class ToolCallResponse(BaseModel):
    id: str
    execution_id: str
    tool_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None

    model_config = {"from_attributes": True}

class ToolCallDetailResponse(ToolCallResponse):
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


# --- Message ---

class MessageCreate(BaseModel):
    from_agent: str
    to_agent: str
    content: dict[str, Any] | None = None

class MessageResponse(BaseModel):
    id: str
    run_id: str
    from_agent: str
    to_agent: str
    timestamp: datetime

    model_config = {"from_attributes": True}

class MessageDetailResponse(MessageResponse):
    content: dict[str, Any] | None = None
