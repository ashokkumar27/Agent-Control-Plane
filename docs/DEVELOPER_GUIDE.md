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

## Durable approvals for pilots

The default approval queue is in-memory for simple examples. For local pilots,
use SQLite so pending approvals and idempotency records survive process
restarts:

```python
from agent_control_plane import (
    ControlPlaneProject,
    SQLiteApprovalQueue,
    SQLiteAuditLedger,
    SQLiteIdempotencyStore,
)

project = ControlPlaneProject.load("my_agent_project")
approvals = SQLiteApprovalQueue("var/agent-control-plane/approvals.db")
ledger = SQLiteAuditLedger("var/agent-control-plane/audit.db")
idempotency = SQLiteIdempotencyStore("var/agent-control-plane/idempotency.db")
plane = project.build_control_plane(
    handlers={"issue_refund": issue_refund},
    approvals=approvals,
    ledger=ledger,
    idempotency=idempotency,
)
```

Approval decisions still re-authorize final arguments before execution, so an
approver cannot silently change a request into a higher-risk action.

For side-effecting tools, pass a stable idempotency key from the caller or
framework tool-call ID. Retries with the same key and same request replay the
stored terminal result instead of executing the handler again:

```python
result = plane.execute_tool(
    agent_id="customer_support_refund_agent",
    tool_name="issue_refund",
    args={"order_id": "A123", "amount": 25, "reason": "Late delivery"},
    idempotency_key="refund:A123:25",
    context={"user": {"fraud_flag": False}},
)
```

If the same idempotency key is reused with different arguments, the control
plane returns `idempotency_conflict` and does not call the tool handler.

All runtime control-plane decisions are recorded as structured audit events:
tool proposals, policy outcomes, approval requests and decisions, approval
rechecks, executions, tool errors, and idempotency started, completed, replayed,
conflicted, and in-progress states. Verify the hash chain before exporting
evidence:

```python
ledger_check = plane.ledger.verify()
if not ledger_check.valid:
    raise RuntimeError(ledger_check.to_dict())
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
