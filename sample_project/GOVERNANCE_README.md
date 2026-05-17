# Agent Control Plane Starter Project

This folder is designed so governance teams and developers can work together.

## For governance / risk teams

Start with these files:

- `agents/customer_support_refund_agent.yaml` — what the agent is for, who owns it, and what tools it may use.
- `tools/issue_refund.yaml` — what the tool does and why it is high impact.
- `policies/refund_controls.yaml` — what is allowed, denied, or sent for approval.
- `risk_assessments/customer_support_refund_agent.yaml` — business-friendly review questions.

You can run:

```bash
agentctl review .
agentctl assess .
agentctl simulate . --agent customer_support_refund_agent --tool issue_refund --args '{"order_id":"A123","amount":280,"reason":"Damaged item"}'
agentctl portal .
```

## For developers

Load this project in Python:

```python
from agent_control_plane import ControlPlaneProject

project = ControlPlaneProject.load(".")
plane = project.build_control_plane(handlers={"issue_refund": issue_refund})
```
