from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agenttrace.server.db import Base, engine
from agenttrace.server.models import AgentExecution, Message, ToolCall, WorkflowRun  # noqa: F401
from agenttrace.server.routes_ingest import router as ingest_router
from agenttrace.server.routes_query import dashboard_router, router as query_router

app = FastAPI(title="AgentTrace")

# Create all tables on startup if they don't already exist.
# To reset the schema, delete agenttrace.db and restart.
Base.metadata.create_all(bind=engine)

app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(dashboard_router)
app.mount("/static", StaticFiles(directory="agenttrace/server/static"), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}
