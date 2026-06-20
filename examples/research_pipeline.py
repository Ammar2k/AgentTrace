import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agenttrace import AgentTrace


tracer = AgentTrace(api_url="http://127.0.0.1:8000")


@tracer.trace_agent("researcher", model="demo-model")
def research(topic: str):
    tracer.log_tool_call(
        "web_search",
        arguments={"q": topic},
        result={"sources": ["paper-1", "paper-2"]},
    )
    notes = f"Key notes about {topic}"
    return notes, {"tokens_in": 120, "tokens_out": 45}


@tracer.trace_agent("writer", model="demo-model")
def write_summary(notes: str):
    summary = f"Summary based on: {notes}"
    return summary, {"tokens_in": 80, "tokens_out": 35}


def main():
    with tracer.trace_run("demo-research-pipeline", metadata={"example": True}):
        notes = research("multi-agent observability")
        tracer.log_message("researcher", "writer", {"notes": notes})
        summary = write_summary(notes)

    tracer.close()
    print(summary)


if __name__ == "__main__":
    main()
