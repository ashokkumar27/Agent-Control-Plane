# Developer guide

The control plane is designed to be inserted at the tool execution boundary.

## Minimal pattern

Before:

```python
result = tools[tool_name](**args)
```

After:

```python
result = plane.execute_tool(
    agent_id=agent_id,
    tool_name=tool_name,
    args=args,
    user_id=user_id,
    context=context,
)
```

## Load YAML governance project

```python
from agent_control_plane import ControlPlaneProject, validate_project

report = validate_project("my_agent_project")
if not report.valid:
    raise RuntimeError(report.to_markdown())

project = ControlPlaneProject.load("my_agent_project")
plane = project.build_control_plane(handlers={
    "get_order": get_order,
    "issue_refund": issue_refund,
})
```

The CLI form is suitable for CI:

```bash
agentctl validate my_agent_project --json
```

## Use the policy builder

```python
from agent_control_plane import rule, PolicyEngine

rules = [
    rule("Refunds above 50 require approval")
        .when_tool("issue_refund")
        .when_arg("amount", ">", 50)
        .with_control("human_oversight", "record_keeping")
        .require_approval("support_manager")
]
engine = PolicyEngine(rules)
```

## Integration points

- OpenAI-style tool loop: intercept function/tool calls before execution.
- LangGraph: wrap ToolNode or tool functions.
- CrewAI / AutoGen / LlamaIndex / custom harnesses: wrap the executor or tool registry.
- MCP: place the control plane in front of MCP tool execution.

## Adapter scenario checks

Run the framework-style scenario harness from the repository root:

```bash
python3 examples/agentic_framework_scenarios.py
```

It uses dependency-free OpenAI-style and LangGraph-style adapters to cover the
baseline flows: read-only lookup, small refund allowed, support approval,
finance approval, fraud denial, and prompt-injection escalation before a
side-effecting tool.
