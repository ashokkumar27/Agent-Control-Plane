from pathlib import Path
from agent_control_plane import ControlPlaneProject

ROOT = Path(__file__).resolve().parents[1] / "sample_project"


def get_order(order_id: str):
    return {"order_id": order_id, "status": "delivered_late", "customer_id": "C-123"}


def issue_refund(order_id: str, amount: float, reason: str):
    return {"status": "refund_issued", "order_id": order_id, "amount": amount, "reason": reason}


project = ControlPlaneProject.load(ROOT)
plane = project.build_control_plane(handlers={
    "get_order": get_order,
    "issue_refund": issue_refund,
})

refund = plane.guarded_callable(
    agent_id="customer_support_refund_agent",
    tool_name="issue_refund",
    user_id="user_123",
    context={"user": {"fraud_flag": False}},
)

print("Small refund:")
print(refund(order_id="A123", amount=25, reason="Late delivery"))

print("Large refund:")
print(refund(order_id="A123", amount=280, reason="Damaged item"))
