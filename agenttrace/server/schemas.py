from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


WORKFLOW_EVENT_TYPES = frozenset({
    "task.started",
    "task.completed",
    "route.selected",
    "action.started",
    "action.completed",
    "action.failed",
    "verification.passed",
    "verification.failed",
    "recovery.started",
    "human.decision",
    "workflow.stopped",
})


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
    agent_summary: list["AgentSummaryResponse"] = Field(default_factory=list)


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
    error_type: str | None = None
    error_message: str | None = None
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
    cost_usd: float

    model_config = {"from_attributes": True}

class ExecutionDetailResponse(ExecutionResponse):
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    error: str | None = None
    retry_count: int
    duration_seconds: float = 0.0
    timeline_left_percent: float = 0.0
    timeline_width_percent: float = 0.0
    timeline_depth: int = 0
    tool_calls: list["ToolCallDetailResponse"] = Field(default_factory=list)


class AgentSummaryResponse(BaseModel):
    agent_name: str
    calls: int
    failures: int
    total_duration_seconds: float
    total_tokens: int
    tokens_in: int
    tokens_out: int
    total_cost_usd: float


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


# --- WorkflowEvent ---

class WorkflowEventCreate(BaseModel):
    event_type: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    task_id: str | None = None
    parent_event_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if value not in WORKFLOW_EVENT_TYPES:
            allowed = ", ".join(sorted(WORKFLOW_EVENT_TYPES))
            raise ValueError(f"event_type must be one of: {allowed}")
        return value


class WorkflowEventResponse(BaseModel):
    id: str
    run_id: str
    event_type: str
    occurred_at: datetime
    task_id: str | None
    parent_event_id: str | None
    causation_id: str | None
    idempotency_key: str | None
    payload: dict[str, Any]
