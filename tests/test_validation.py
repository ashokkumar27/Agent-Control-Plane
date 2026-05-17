import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_control_plane import validate_project, write_starter_project
from agent_control_plane.cli import main


class ProjectValidationTests(unittest.TestCase):
    def assert_has_issue(self, report, code):
        self.assertTrue(any(issue.code == code for issue in report.issues), report.to_dict())

    def test_starter_project_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            report = validate_project(tmp)
            self.assertTrue(report.valid, report.to_dict())
            self.assertEqual(report.status, "valid")
            self.assertEqual(len(report.errors), 0)

    def test_unknown_allowed_tool_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            agent_path = Path(tmp) / "agents" / "customer_support_refund_agent.yaml"
            agent_path.write_text(agent_path.read_text().replace("  - issue_refund", "  - missing_tool"), encoding="utf-8")

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "unknown_allowed_tool")

    def test_duplicate_tool_name_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            source = Path(tmp) / "tools" / "issue_refund.yaml"
            duplicate = Path(tmp) / "tools" / "issue_refund_duplicate.yaml"
            duplicate.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "duplicate_tool")

    def test_invalid_enum_is_human_readable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            tool_path = Path(tmp) / "tools" / "issue_refund.yaml"
            tool_path.write_text(tool_path.read_text().replace("risk_tier: high", "risk_tier: extreme"), encoding="utf-8")

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "invalid_tool_card")
            self.assertTrue(any("extreme" in issue.message for issue in report.issues))

    def test_unsupported_policy_operator_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            policy_path = Path(tmp) / "policies" / "refund_controls.yaml"
            policy_path.write_text(policy_path.read_text().replace("        gt: 50", "        greater_than: 50"), encoding="utf-8")

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "unsupported_policy_operator")

    def test_unknown_policy_tool_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            policy_path = Path(tmp) / "policies" / "refund_controls.yaml"
            policy_path.write_text(policy_path.read_text().replace("eq: issue_refund", "eq: missing_tool", 1), encoding="utf-8")

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "unknown_policy_tool")

    def test_unknown_policy_agent_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            policy_path = Path(tmp) / "policies" / "refund_controls.yaml"
            with policy_path.open("a", encoding="utf-8") as file:
                file.write(
                    """
  - rule_id: allow_unknown_agent_lookup
    effect: allow
    description: Unknown agent example.
    when:
      agent.agent_id:
        eq: missing_agent
      tool.name:
        eq: get_order
"""
                )

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "unknown_policy_agent")

    def test_high_impact_tool_without_deny_or_approval_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            policy_path = Path(tmp) / "policies" / "refund_controls.yaml"
            policy_path.write_text(
                """
rules:
  - rule_id: allow_all_refunds
    effect: allow
    description: Allow refunds without approval.
    when:
      tool.name:
        eq: issue_refund
""".strip()
                + "\n",
                encoding="utf-8",
            )

            report = validate_project(tmp)

            self.assertFalse(report.valid)
            self.assert_has_issue(report, "high_impact_tool_uncontrolled")

    def test_cli_validate_returns_nonzero_for_invalid_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_starter_project(tmp)
            agent_path = Path(tmp) / "agents" / "customer_support_refund_agent.yaml"
            agent_path.write_text(agent_path.read_text().replace("  - issue_refund", "  - missing_tool"), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate", tmp, "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
