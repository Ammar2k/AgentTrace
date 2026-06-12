# AgentTrace

AgentTrace is a lightweight observability platform for multi-agent AI workflows.

The goal is to provide visibility into how agent systems execute by capturing execution traces, agent communication, tool usage, latency, failures, and token consumption.

AgentTrace focuses on helping developers understand, debug, and analyze agent workflows.

## Features

### Workflow Tracing

Capture:

- Workflow runs
- Agent executions
- Agent-to-agent communication
- Tool calls
- Inputs and outputs
- Execution status

### Metrics

Track:

- Latency per agent
- Total workflow runtime
- Token usage
- Estimated cost
- Retry attempts
- Failures and exceptions

### Visualization

Dashboard views:

- Workflow execution timeline
- Agent communication graph
- Run history
- Cost breakdown
- Failure analysis

## Architecture

```text
Agent Workflow
      |
      v
AgentTrace SDK
      |
      v
Observability API
      |
      v
PostgreSQL
      |
      v
Dashboard
