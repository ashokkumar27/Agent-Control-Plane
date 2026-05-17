# Agent Control Plane

A developer-friendly and governance-team-friendly control plane for AI agents.

The goal is simple:

> **Let AI agents decide how to complete a task, while the control plane decides what they are allowed to do.**

This project is not another agent framework. It is a governance layer that can sit around OpenAI Agents, LangGraph, CrewAI, AutoGen, LlamaIndex, custom agent loops, or MCP-style tools.

## Who this is for

### Governance / risk / compliance teams

Use the plain-language workflow:

```bash
agentctl init my_agent_project
agentctl review my_agent_project
agentctl assess my_agent_project
agentctl portal my_agent_project
```

You will get:

- agent intake forms
- tool intake forms
- plain-language reviews
- readiness scoring
- policy explanations
- approval threshold examples
- audit/evidence-ready structure

### Developers

Use the Python SDK:

```python
from agent_control_plane import ControlPlaneProject

project = ControlPlaneProject.load("my_agent_project")
plane = project.build_control_plane(handlers={"issue_refund": issue_refund})

result = plane.execute_tool(
    agent_id="customer_support_refund_agent",
    tool_name="issue_refund",
    args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
    context={"user": {"fraud_flag": False}},
)
```

Or wrap a tool as a normal callable:

```python
refund = plane.guarded_callable(agent_id="customer_support_refund_agent", tool_name="issue_refund")
result = refund(order_id="A123", amount=25, reason="Late delivery")
```

## The operating model

```text
Agent proposes
  ↓
Policy decides
  ↓
Human approves when needed
  ↓
Gateway executes
  ↓
Ledger records
```

## Project layout

A governance project is just a folder:

```text
my_agent_project/
  agents/
    customer_support_refund_agent.yaml
  tools/
    get_order.yaml
    issue_refund.yaml
  policies/
    refund_controls.yaml
  risk_assessments/
    customer_support_refund_agent.yaml
```

YAML is used because non-technical reviewers can read it like a form.

## CLI commands

```bash
agentctl init my_agent_project
agentctl inventory my_agent_project
agentctl review my_agent_project
agentctl assess my_agent_project
agentctl simulate my_agent_project --agent customer_support_refund_agent --tool issue_refund --args '{"order_id":"A123","amount":280,"reason":"Damaged item"}'
agentctl portal my_agent_project
agentctl init-intake blank_forms
```

## Governance positioning

This framework supports AI governance readiness by creating runtime controls and evidence: agent inventory, tool catalog, deterministic policies, human approvals, audit events, and readiness reviews.

It should not be described as automatic legal compliance. It is a technical and operational control layer that helps teams implement governance requirements.

## Try it

```bash
python -m pip install -e .
agentctl review sample_project
agentctl assess sample_project
python examples/developer_friendly_sdk.py
python -m unittest discover -s tests -v
```
