import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agenttrace.server.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="running")  # running | completed | failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)  # stored as JSON string

    executions: Mapped[list["AgentExecution"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("agent_executions.id"), nullable=True)  # nested agents
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")  # running | completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # traceback on failure
    input_: Mapped[str | None] = mapped_column("input", Text, nullable=True)   # stored as JSON string
    output: Mapped[str | None] = mapped_column(Text, nullable=True)            # stored as JSON string
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped["WorkflowRun"] = relationship(back_populates="executions")
    children: Mapped[list["AgentExecution"]] = relationship(back_populates="parent")
    parent: Mapped["AgentExecution | None"] = relationship(back_populates="children", remote_side="AgentExecution.id")
    tool_calls: Mapped[list["ToolCall"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    execution_id: Mapped[str] = mapped_column(ForeignKey("agent_executions.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    arguments: Mapped[str | None] = mapped_column(Text, nullable=True)  # stored as JSON string
    result: Mapped[str | None] = mapped_column(Text, nullable=True)      # stored as JSON string
    status: Mapped[str] = mapped_column(String, default="completed")     # completed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    execution: Mapped["AgentExecution"] = relationship(back_populates="tool_calls")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    from_agent: Mapped[str] = mapped_column(String, nullable=False)
    to_agent: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)  # stored as JSON string
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["WorkflowRun"] = relationship(back_populates="messages")
