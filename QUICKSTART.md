# Quickstart

## 1. Install locally

```bash
python -m pip install -e .
```

## 2. Use the included sample project

```bash
agentctl inventory sample_project
agentctl review sample_project
agentctl assess sample_project
```

## 3. Simulate a governed tool call

Small refund, allowed:

```bash
agentctl simulate sample_project \
  --agent customer_support_refund_agent \
  --tool issue_refund \
  --args '{"order_id":"A123","amount":25,"reason":"Late delivery"}' \
  --user '{"fraud_flag":false}'
```

Large refund, approval required:

```bash
agentctl simulate sample_project \
  --agent customer_support_refund_agent \
  --tool issue_refund \
  --args '{"order_id":"A123","amount":280,"reason":"Damaged item"}' \
  --user '{"fraud_flag":false}'
```

Fraud-flagged account, denied:

```bash
agentctl simulate sample_project \
  --agent customer_support_refund_agent \
  --tool issue_refund \
  --args '{"order_id":"A123","amount":25,"reason":"Late delivery"}' \
  --user '{"fraud_flag":true}'
```

## 4. Create your own project

```bash
agentctl init my_agent_project
agentctl review my_agent_project
agentctl assess my_agent_project
agentctl portal my_agent_project
```

## 5. Developer SDK example

```bash
python examples/developer_friendly_sdk.py
```

## 6. Run tests

```bash
python -m unittest discover -s tests -v
```
