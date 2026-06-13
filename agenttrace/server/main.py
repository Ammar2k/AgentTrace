from fastapi import FastAPI

from agenttrace.server.db import Base, engine
from agenttrace.server.models import AgentExecution, Message, ToolCall, WorkflowRun  # noqa: F401

app = FastAPI(title="AgentTrace")

# Create all tables on startup if they don't already exist.
# To reset the schema, delete agenttrace.db and restart.
Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
