import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agenttrace import AgentTrace


TOPICS = [
    "multi-agent observability",
    "tool reliability in agent systems",
    "failure analysis for AI workflows",
    "cost tracking for LLM applications",
    "agent communication debugging",
]

tracer = AgentTrace(api_url="http://127.0.0.1:8000")


@tracer.trace_agent("planner", model="demo-model")
def plan_research(topic: str):
    time.sleep(random.uniform(0.05, 0.15))
    plan = {
        "topic": topic,
        "questions": [
            f"What makes {topic} hard to debug?",
            "Which signals should the dashboard show first?",
            "Where do failures usually originate?",
        ],
    }
    return plan, {
        "tokens_in": random.randint(80, 140),
        "tokens_out": random.randint(40, 90),
        "retry_count": 0,
    }


@tracer.trace_agent("researcher", model="demo-model")
def research(plan: dict[str, object]):
    topic = str(plan["topic"])
    time.sleep(random.uniform(0.08, 0.22))
    tracer.log_tool_call(
        "web_search",
        arguments={"q": topic, "limit": 3},
        result={"sources": [f"{topic}-paper", f"{topic}-blog", f"{topic}-case-study"]},
    )
    notes = {
        "topic": topic,
        "findings": [
            "Capture each agent execution as a timed span.",
            "Keep model, tokens, tool calls, and errors together.",
            "Summaries are useful, but raw traces remain the source of truth.",
        ],
    }
    return notes, {
        "tokens_in": random.randint(180, 320),
        "tokens_out": random.randint(90, 180),
        "retry_count": random.choice([0, 0, 1]),
    }


@tracer.trace_agent("writer", model="demo-model")
def write_summary(notes: dict[str, object], fail_rate: float):
    time.sleep(random.uniform(0.06, 0.18))
    retry_count = random.choice([0, 0, 1, 2])

    if random.random() < fail_rate:
        raise ValueError(f"could not turn notes into a stable summary for {notes['topic']}")

    summary = (
        f"{notes['topic']}: trace every agent step, connect tool calls and messages, "
        "and surface failures where developers already inspect runs."
    )
    return summary, {
        "tokens_in": random.randint(150, 260),
        "tokens_out": random.randint(70, 140),
        "retry_count": retry_count,
    }


def run_once(index: int, fail_rate: float) -> None:
    topic = random.choice(TOPICS)
    run_name = f"demo-research-pipeline-{index}"

    try:
        with tracer.trace_run(run_name, metadata={"example": True, "topic": topic}):
            plan = plan_research(topic)
            tracer.log_message("planner", "researcher", {"plan": plan})

            notes = research(plan)
            tracer.log_message("researcher", "writer", {"notes": notes})

            summary = write_summary(notes, fail_rate)
            tracer.log_message("writer", "planner", {"summary": summary})
    except Exception as exc:
        print(f"{run_name}: failed ({type(exc).__name__}: {exc})")
    else:
        print(f"{run_name}: completed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate AgentTrace with realistic demo runs.")
    parser.add_argument("--runs", type=int, default=5, help="number of workflow runs to record")
    parser.add_argument("--fail-rate", type=float, default=0.2, help="writer failure probability from 0.0 to 1.0")
    args = parser.parse_args()

    try:
        for index in range(1, args.runs + 1):
            run_once(index, max(0.0, min(args.fail_rate, 1.0)))
    finally:
        tracer.close()


if __name__ == "__main__":
    main()
