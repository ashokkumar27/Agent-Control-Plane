import tempfile
import unittest
from pathlib import Path

from agent_control_plane import AgentCard, AgentControlPlane, PolicyEngine, PolicyRule, SQLiteIdempotencyStore, ToolCard
from agent_control_plane.adapters import LangGraphToolMiddleware, wrap_openai_tool_executor
from agent_control_plane.idempotency import InMemoryIdempotencyStore, tool_call_fingerprint


def allow_refunds_policy():
    return PolicyEngine([
        PolicyRule(
            rule_id="allow_refunds",
            effect="allow",
            description="allow",
            when={"tool.name": {"eq": "issue_refund"}},
        )
    ])


def build_plane(handler, idempotency=None):
    cp = AgentControlPlane(policy_engine=allow_refunds_policy(), idempotency=idempotency)
    cp.register_agent(AgentCard(agent_id="a1", owner="test", purpose="test", allowed_tools=["issue_refund"]))
    cp.register_tool(ToolCard(name="issue_refund", description="refund", tool_type="side_effecting"), handler)
    return cp


class IdempotencyTests(unittest.TestCase):
    def test_same_key_replays_success_without_double_execution(self):
        calls = {"count": 0}

        def refund_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            return {"refund_id": f"RF{calls['count']}", "order_id": order_id, "amount": amount, "reason": reason}

        plane = build_plane(refund_tool)
        args = {"order_id": "A1", "amount": 10, "reason": "late"}

        first = plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")
        second = plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")

        self.assertEqual(first["status"], "success")
        self.assertEqual(second["status"], "success")
        self.assertEqual(calls["count"], 1)
        self.assertFalse(first["idempotency"]["replayed"])
        self.assertTrue(second["idempotency"]["replayed"])
        self.assertEqual(second["output"]["refund_id"], "RF1")
        event_types = [record.event_type for record in plane.ledger.list_records()]
        self.assertEqual(event_types.count("idempotency_started"), 1)
        self.assertEqual(event_types.count("idempotency_completed"), 1)
        self.assertEqual(event_types.count("idempotency_replayed"), 1)

    def test_same_key_different_args_conflicts_without_execution(self):
        calls = {"count": 0}

        def refund_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            return {"refund_id": f"RF{calls['count']}", "order_id": order_id, "amount": amount, "reason": reason}

        plane = build_plane(refund_tool)
        first = plane.execute_tool(
            agent_id="a1",
            tool_name="issue_refund",
            args={"order_id": "A1", "amount": 10, "reason": "late"},
            idempotency_key="refund-A1",
        )
        conflict = plane.execute_tool(
            agent_id="a1",
            tool_name="issue_refund",
            args={"order_id": "A1", "amount": 25, "reason": "changed"},
            idempotency_key="refund-A1",
        )

        self.assertEqual(first["status"], "success")
        self.assertEqual(conflict["status"], "idempotency_conflict")
        self.assertEqual(calls["count"], 1)

    def test_sqlite_store_replays_after_restart(self):
        calls = {"count": 0}

        def refund_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            return {"refund_id": f"RF{calls['count']}", "order_id": order_id, "amount": amount, "reason": reason}

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "idempotency.db"
            args = {"order_id": "A1", "amount": 10, "reason": "late"}
            first_plane = build_plane(refund_tool, idempotency=SQLiteIdempotencyStore(db_path))
            first = first_plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")

            def should_not_run(**kwargs):
                calls["count"] += 1
                raise AssertionError("handler should not run on idempotent replay")

            restarted_plane = build_plane(should_not_run, idempotency=SQLiteIdempotencyStore(db_path))
            second = restarted_plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")

            self.assertEqual(first["status"], "success")
            self.assertEqual(second["status"], "success")
            self.assertTrue(second["idempotency"]["replayed"])
            self.assertEqual(calls["count"], 1)

    def test_tool_error_is_cached_for_same_key(self):
        calls = {"count": 0}

        def failing_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            raise RuntimeError("provider timeout after submission")

        plane = build_plane(failing_tool)
        args = {"order_id": "A1", "amount": 10, "reason": "late"}

        first = plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")
        second = plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")

        self.assertEqual(first["status"], "tool_error")
        self.assertEqual(second["status"], "tool_error")
        self.assertTrue(second["idempotency"]["replayed"])
        self.assertEqual(calls["count"], 1)

    def test_in_progress_key_fails_closed(self):
        store = InMemoryIdempotencyStore()
        args = {"order_id": "A1", "amount": 10, "reason": "late"}
        request_hash = tool_call_fingerprint(agent_id="a1", user_id=None, tool_name="issue_refund", args=args)
        store.start("refund-A1", request_hash)

        def refund_tool(**kwargs):
            raise AssertionError("handler should not run while idempotency key is in progress")

        plane = build_plane(refund_tool, idempotency=store)
        result = plane.execute_tool(agent_id="a1", tool_name="issue_refund", args=args, idempotency_key="refund-A1")

        self.assertEqual(result["status"], "idempotency_in_progress")

    def test_openai_executor_can_supply_idempotency_key(self):
        calls = {"count": 0}

        def refund_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            return {"refund_id": "RF1", "order_id": order_id, "amount": amount, "reason": reason}

        plane = build_plane(refund_tool)
        execute = wrap_openai_tool_executor(
            plane,
            agent_id="a1",
            idempotency_key_fn=lambda tool_name, args: f"{tool_name}:{args['order_id']}",
        )
        args = {"order_id": "A1", "amount": 10, "reason": "late"}

        execute("issue_refund", args)
        replayed = execute("issue_refund", args)

        self.assertEqual(calls["count"], 1)
        self.assertTrue(replayed["idempotency"]["replayed"])

    def test_langgraph_middleware_can_supply_idempotency_key(self):
        calls = {"count": 0}

        def refund_tool(order_id: str, amount: float, reason: str):
            calls["count"] += 1
            return {"refund_id": "RF1", "order_id": order_id, "amount": amount, "reason": reason}

        plane = build_plane(refund_tool)
        middleware = LangGraphToolMiddleware(plane, agent_id="a1", idempotency_key="refund-A1")
        tool = middleware.wrap_tool("issue_refund", refund_tool)
        args = {"order_id": "A1", "amount": 10, "reason": "late"}

        tool(**args)
        replayed = tool(**args)

        self.assertEqual(calls["count"], 1)
        self.assertTrue(replayed["idempotency"]["replayed"])


if __name__ == "__main__":
    unittest.main()
