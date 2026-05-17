import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agent_control_plane import run_scenario_tests, write_starter_project
from agent_control_plane.cli import main


ROOT = Path(__file__).resolve().parents[1]


class ScenarioRunnerTests(unittest.TestCase):
    def test_sample_project_scenarios_pass(self):
        report = run_scenario_tests(ROOT / "sample_project")

        self.assertTrue(report.passed, report.to_markdown())
        self.assertEqual(report.status, "passed")
        self.assertEqual(len(report.scenarios), 10)
        names = [scenario.name for scenario in report.scenarios]
        self.assertIn("idempotent_refund_replays_without_double_execution", names)
        self.assertIn("support_approval_cannot_sneak_in_finance_refund", names)
        self.assertIn("tool_error_is_logged_and_idempotently_replayed", names)

    def test_cli_test_command_returns_json_report(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main(["test", str(ROOT / "sample_project"), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["scenario_count"], 10)

    def test_generated_starter_project_includes_passing_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_starter_project(tmp)

            report = run_scenario_tests(project_path)

            self.assertTrue(report.passed, report.to_markdown())
            self.assertEqual(len(report.scenarios), 4)

    def test_scenario_failure_reports_expected_and_actual(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_starter_project(tmp)
            scenario_file = Path(tmp) / "failing_scenario.yaml"
            scenario_file.write_text(
                """
                name: wrong_status_expectation
                mode: simulate
                agent_id: customer_support_refund_agent
                tool_name: issue_refund
                args:
                  order_id: A123
                  amount: 25
                  reason: Late delivery
                user:
                  fraud_flag: false
                expected:
                  status: denied
                """,
                encoding="utf-8",
            )

            report = run_scenario_tests(project_path, scenario_file)

            self.assertFalse(report.passed)
            self.assertEqual(report.scenarios[0].failures[0].code, "status_mismatch")
            self.assertEqual(report.scenarios[0].failures[0].expected, "denied")
            self.assertEqual(report.scenarios[0].failures[0].actual, "allowed")


if __name__ == "__main__":
    unittest.main()
