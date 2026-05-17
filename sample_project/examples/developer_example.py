from agent_control_plane import ControlPlaneProject


def get_order(order_id: str):
    return {"order_id": order_id, "status": "delivered", "customer_id": "C123"}


def issue_refund(order_id: str, amount: float, reason: str):
    return {"refund_id": "RF-001", "order_id": order_id, "amount": amount, "reason": reason}


project = ControlPlaneProject.load("..")
plane = project.build_control_plane(handlers={
    "get_order": get_order,
    "issue_refund": issue_refund,
})

print(plane.execute_tool(
    agent_id="customer_support_refund_agent",
    tool_name="issue_refund",
    args={"order_id": "A123", "amount": 25, "reason": "Late delivery"},
    user_id="user_1",
    context={"user": {"fraud_flag": False}},
))

print(plane.execute_tool(
    agent_id="customer_support_refund_agent",
    tool_name="issue_refund",
    args={"order_id": "A123", "amount": 280, "reason": "Damaged item"},
    user_id="user_1",
    context={"user": {"fraud_flag": False}},
))
