from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io import iter_config_files, read_structured_file
from .ledger import AuditLedger
from .models import DecisionType
from .project import ControlPlaneProject


@dataclass(slots=True)
class ScenarioFailure:
    scenario: str
    step: str | None
    code: str
    message: str
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "step": self.step,
            "code": self.code,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(slots=True)
class ScenarioStepResult:
    name: str
    mode: str
    status: str | None
    passed: bool
    result: dict[str, Any]
    failures: list[ScenarioFailure] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "status": self.status,
            "passed": self.passed,
            "result": self.result,
            "failures": [failure.to_dict() for failure in self.failures],
        }


@dataclass(slots=True)
class ScenarioResult:
    name: str
    source: str
    passed: bool
    steps: list[ScenarioStepResult] = field(default_factory=list)
    failures: list[ScenarioFailure] = field(default_factory=list)
    ledger_valid: bool = True
    ledger_issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "passed": self.passed,
            "steps": [step.to_dict() for step in self.steps],
            "failures": [failure.to_dict() for failure in self.failures],
            "ledger_valid": self.ledger_valid,
            "ledger_issues": self.ledger_issues,
        }


@dataclass(slots=True)
class ScenarioTestReport:
    project_root: str
    scenarios_path: str
    scenarios: list[ScenarioResult] = field(default_factory=list)
    failures: list[ScenarioFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures and all(scenario.passed for scenario in self.scenarios)

    @property
    def status(self) -> str:
        return "passed" if self.passed else "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "scenarios_path": self.scenarios_path,
            "status": self.status,
            "scenario_count": len(self.scenarios),
            "passed_count": sum(1 for scenario in self.scenarios if scenario.passed),
            "failed_count": sum(1 for scenario in self.scenarios if not scenario.passed) + len(self.failures),
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "failures": [failure.to_dict() for failure in self.failures],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Scenario test report: {self.status}",
            "",
            f"- Project: `{self.project_root}`",
            f"- Scenarios path: `{self.scenarios_path}`",
            f"- Scenarios: {len(self.scenarios)}",
            f"- Passed: {sum(1 for scenario in self.scenarios if scenario.passed)}",
            f"- Failed: {sum(1 for scenario in self.scenarios if not scenario.passed) + len(self.failures)}",
            "",
        ]
        for failure in self.failures:
            lines.append(f"- [FAIL] {failure.code}: {failure.message}")
        for scenario in self.scenarios:
            marker = "PASS" if scenario.passed else "FAIL"
            lines.append(f"- [{marker}] {scenario.name}")
            for step in scenario.steps:
                step_marker = "PASS" if step.passed else "FAIL"
                lines.append(f"  - [{step_marker}] {step.name}: `{step.status}`")
            for failure in scenario.failures:
                location = f" step `{failure.step}`" if failure.step else ""
                lines.append(f"  - {failure.code}{location}: {failure.message}")
        return "\n".join(lines).rstrip() + "\n"


def run_scenario_tests(project_path: str | Path, scenarios_path: str | Path | None = None) -> ScenarioTestReport:
    project = ControlPlaneProject.load(project_path)
    runner = ScenarioRunner(project)
    return runner.run_path(scenarios_path or (project.root / "scenarios"))


class ScenarioRunner:
    def __init__(self, project: ControlPlaneProject) -> None:
        self.project = project

    def run_path(self, scenarios_path: str | Path) -> ScenarioTestReport:
        path = Path(scenarios_path)
        report = ScenarioTestReport(project_root=str(self.project.root), scenarios_path=str(path))
        loaded = _load_scenarios(path)
        if not loaded:
            report.failures.append(
                ScenarioFailure(
                    scenario="",
                    step=None,
                    code="no_scenarios",
                    message="No scenario files were found.",
                    expected="one or more YAML or JSON scenario files",
                    actual=str(path),
                )
            )
            return report
        for scenario, source in loaded:
            report.scenarios.append(self.run_scenario(scenario, source=source))
        return report

    def run_scenario(self, scenario: dict[str, Any], *, source: str) -> ScenarioResult:
        scenario_name = str(scenario.get("name") or Path(source).stem)
        current_step: dict[str, Any] = {}
        handlers = {tool.name: _mock_handler(tool.name, current_step) for tool in self.project.tools}
        plane = self.project.build_control_plane(handlers=handlers)
        raw_steps = scenario.get("steps")
        has_steps = isinstance(raw_steps, list)
        steps = raw_steps if has_steps else [scenario]
        common = {k: v for k, v in scenario.items() if k not in {"name", "description", "expected", "steps"}}
        scenario_result = ScenarioResult(name=scenario_name, source=source, passed=True)
        named_results: dict[str, dict[str, Any]] = {}
        last_result: dict[str, Any] | None = None

        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                failure = ScenarioFailure(
                    scenario=scenario_name,
                    step=f"step_{index + 1}",
                    code="invalid_step",
                    message="Scenario step must be an object.",
                    expected="object",
                    actual=raw_step,
                )
                scenario_result.failures.append(failure)
                continue

            step = {**common, **raw_step} if has_steps else raw_step
            step_name = str(step.get("name") or (scenario_name if not has_steps else f"step_{index + 1}"))
            mode = str(step.get("mode") or "simulate")
            current_step.clear()
            current_step.update(step)
            result, execution_failures = self._run_step(
                plane=plane,
                scenario_name=scenario_name,
                step_name=step_name,
                mode=mode,
                step=step,
                last_result=last_result,
                named_results=named_results,
            )
            failures = execution_failures + _evaluate_expectations(
                scenario=scenario_name,
                step=step_name,
                expected=step.get("expected") or {},
                result=result,
                ledger=plane.ledger,
            )
            step_result = ScenarioStepResult(
                name=step_name,
                mode=mode,
                status=result.get("status"),
                passed=not failures,
                result=result,
                failures=failures,
            )
            scenario_result.steps.append(step_result)
            scenario_result.failures.extend(failures)
            named_results[step_name] = result
            last_result = result

        if has_steps and scenario.get("expected"):
            scenario_result.failures.extend(
                _evaluate_expectations(
                    scenario=scenario_name,
                    step=None,
                    expected=scenario.get("expected") or {},
                    result=last_result or {},
                    ledger=plane.ledger,
                )
            )

        ledger_check = plane.ledger.verify()
        scenario_result.ledger_valid = ledger_check.valid
        scenario_result.ledger_issues = [issue.to_dict() for issue in ledger_check.issues]
        if not ledger_check.valid:
            scenario_result.failures.append(
                ScenarioFailure(
                    scenario=scenario_name,
                    step=None,
                    code="ledger_verification_failed",
                    message="Scenario audit ledger failed hash-chain verification.",
                    expected=True,
                    actual=ledger_check.to_dict(),
                )
            )
        scenario_result.passed = not scenario_result.failures and all(step.passed for step in scenario_result.steps)
        return scenario_result

    def _run_step(
        self,
        *,
        plane,
        scenario_name: str,
        step_name: str,
        mode: str,
        step: dict[str, Any],
        last_result: dict[str, Any] | None,
        named_results: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], list[ScenarioFailure]]:
        try:
            if mode == "simulate":
                return _simulate_with_plane(plane, step), []
            if mode == "execute":
                return _execute_with_plane(plane, step), []
            if mode == "approve":
                approval_id = _resolve_approval_id(step, last_result, named_results)
                return (
                    plane.approve_and_execute(
                        approval_id,
                        approver_id=str(step.get("approver_id") or "scenario_approver"),
                        approver_role=step.get("approver_role"),
                        modified_args=step.get("modified_args"),
                        idempotency_key=step.get("idempotency_key"),
                        notes=step.get("notes"),
                    ),
                    [],
                )
            if mode == "reject":
                approval_id = _resolve_approval_id(step, last_result, named_results)
                return (
                    plane.reject_approval(
                        approval_id,
                        approver_id=str(step.get("approver_id") or "scenario_approver"),
                        approver_role=step.get("approver_role"),
                        notes=step.get("notes"),
                    ),
                    [],
                )
        except Exception as exc:  # noqa: BLE001 - scenario failures must be captured in reports
            return (
                {"status": "scenario_error", "error": str(exc)},
                [
                    ScenarioFailure(
                        scenario=scenario_name,
                        step=step_name,
                        code="scenario_error",
                        message=str(exc),
                    )
                ],
            )

        return (
            {"status": "scenario_error", "error": f"Unsupported scenario mode: {mode}"},
            [
                ScenarioFailure(
                    scenario=scenario_name,
                    step=step_name,
                    code="unsupported_mode",
                    message=f"Unsupported scenario mode: {mode}",
                    expected=["simulate", "execute", "approve", "reject"],
                    actual=mode,
                )
            ],
        )


def _load_scenarios(path: Path) -> list[tuple[dict[str, Any], str]]:
    files = [path] if path.is_file() else iter_config_files(path)
    loaded: list[tuple[dict[str, Any], str]] = []
    for file in files:
        data = read_structured_file(file)
        items: list[Any]
        if isinstance(data, dict) and isinstance(data.get("scenarios"), list):
            items = data["scenarios"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items:
            if isinstance(item, dict):
                loaded.append((item, str(file)))
    return loaded


def _mock_handler(tool_name: str, current_step: dict[str, Any]):
    def _handler(**kwargs: Any) -> Any:
        if current_step.get("mock_error") is not None:
            raise RuntimeError(str(current_step["mock_error"]))
        if "mock_output" in current_step:
            return current_step["mock_output"]
        return {"tool_name": tool_name, "args": kwargs}

    return _handler


def _runtime_context(step: dict[str, Any]) -> dict[str, Any]:
    context = dict(step.get("context") or {})
    user = step.get("user")
    if user is not None:
        context["user"] = {**dict(context.get("user") or {}), **dict(user)}
    else:
        context.setdefault("user", {})
    return context


def _simulate_with_plane(plane, step: dict[str, Any]) -> dict[str, Any]:
    context = _runtime_context(step)
    call, decision = plane.propose_tool_call(
        agent_id=str(step["agent_id"]),
        tool_name=str(step["tool_name"]),
        args=dict(step.get("args") or {}),
        user_id=step.get("user_id") or context.get("user", {}).get("user_id"),
        run_id=step.get("run_id"),
        idempotency_key=step.get("idempotency_key"),
        context=context,
    )
    if decision.decision == DecisionType.ALLOW:
        status = "allowed"
        would_execute = True
    elif decision.decision == DecisionType.REQUIRE_APPROVAL:
        status = "approval_required"
        would_execute = False
    elif decision.decision == DecisionType.DENY:
        status = "denied"
        would_execute = False
    else:
        status = decision.decision.value
        would_execute = False
    return {
        "status": status,
        "simulated": True,
        "would_execute": would_execute,
        "reason": decision.reason,
        "approver_role": decision.approver_role,
        "tool_call": call.to_dict(),
        "decision": decision.to_dict(),
    }


def _execute_with_plane(plane, step: dict[str, Any]) -> dict[str, Any]:
    context = _runtime_context(step)
    return plane.execute_tool(
        agent_id=str(step["agent_id"]),
        tool_name=str(step["tool_name"]),
        args=dict(step.get("args") or {}),
        user_id=step.get("user_id") or context.get("user", {}).get("user_id"),
        run_id=step.get("run_id"),
        idempotency_key=step.get("idempotency_key"),
        context=context,
    )


def _resolve_approval_id(
    step: dict[str, Any],
    last_result: dict[str, Any] | None,
    named_results: dict[str, dict[str, Any]],
) -> str:
    if step.get("approval_id"):
        return str(step["approval_id"])
    if step.get("approval_from"):
        source = named_results[str(step["approval_from"])]
        return str(source["approval_id"])
    if last_result and last_result.get("approval_id"):
        return str(last_result["approval_id"])
    raise ValueError("Approval step needs approval_id, approval_from, or a prior approval_required result.")


def _evaluate_expectations(
    *,
    scenario: str,
    step: str | None,
    expected: dict[str, Any],
    result: dict[str, Any],
    ledger: AuditLedger,
) -> list[ScenarioFailure]:
    failures: list[ScenarioFailure] = []
    if not expected:
        return failures

    if "status" in expected and result.get("status") != expected["status"]:
        failures.append(
            ScenarioFailure(
                scenario=scenario,
                step=step,
                code="status_mismatch",
                message="Scenario status did not match.",
                expected=expected["status"],
                actual=result.get("status"),
            )
        )

    if "approver_role" in expected:
        actual_role = result.get("approver_role") or result.get("decision", {}).get("approver_role")
        if actual_role != expected["approver_role"]:
            failures.append(
                ScenarioFailure(
                    scenario=scenario,
                    step=step,
                    code="approver_role_mismatch",
                    message="Approver role did not match.",
                    expected=expected["approver_role"],
                    actual=actual_role,
                )
            )

    failures.extend(
        _check_collection(
            scenario=scenario,
            step=step,
            field="matched_rules",
            actual=result.get("decision", {}).get("matched_rules", []),
            expected=expected.get("matched_rules"),
        )
    )
    failures.extend(
        _check_collection(
            scenario=scenario,
            step=step,
            field="controls",
            actual=result.get("decision", {}).get("controls", []),
            expected=expected.get("controls"),
        )
    )
    failures.extend(
        _check_collection(
            scenario=scenario,
            step=step,
            field="ledger_events",
            actual=[record.event_type for record in ledger.list_records()],
            expected=expected.get("ledger_events"),
        )
    )

    if "idempotency" in expected:
        for key, expected_value in dict(expected["idempotency"]).items():
            actual_value = result.get("idempotency", {}).get(key)
            if actual_value != expected_value:
                failures.append(
                    ScenarioFailure(
                        scenario=scenario,
                        step=step,
                        code="idempotency_mismatch",
                        message=f"Idempotency field `{key}` did not match.",
                        expected=expected_value,
                        actual=actual_value,
                    )
                )

    if "output" in expected and result.get("output") != expected["output"]:
        failures.append(
            ScenarioFailure(
                scenario=scenario,
                step=step,
                code="output_mismatch",
                message="Tool output did not match.",
                expected=expected["output"],
                actual=result.get("output"),
            )
        )

    if "ledger_verifies" in expected:
        ledger_check = ledger.verify()
        if ledger_check.valid != bool(expected["ledger_verifies"]):
            failures.append(
                ScenarioFailure(
                    scenario=scenario,
                    step=step,
                    code="ledger_verification_mismatch",
                    message="Ledger verification result did not match.",
                    expected=bool(expected["ledger_verifies"]),
                    actual=ledger_check.to_dict(),
                )
            )

    return failures


def _check_collection(
    *,
    scenario: str,
    step: str | None,
    field: str,
    actual: list[Any],
    expected: Any,
) -> list[ScenarioFailure]:
    failures: list[ScenarioFailure] = []
    if expected is None:
        return failures
    if isinstance(expected, dict):
        includes = _as_list(expected.get("includes"))
        excludes = _as_list(expected.get("excludes"))
        equals = expected.get("equals")
    else:
        includes = _as_list(expected)
        excludes = []
        equals = None
    if equals is not None and list(actual) != list(equals):
        failures.append(
            ScenarioFailure(
                scenario=scenario,
                step=step,
                code=f"{field}_mismatch",
                message=f"`{field}` did not exactly match.",
                expected=equals,
                actual=actual,
            )
        )
    missing = [item for item in includes if item not in actual]
    if missing:
        failures.append(
            ScenarioFailure(
                scenario=scenario,
                step=step,
                code=f"{field}_missing",
                message=f"`{field}` is missing expected item(s).",
                expected=includes,
                actual=actual,
            )
        )
    present = [item for item in excludes if item in actual]
    if present:
        failures.append(
            ScenarioFailure(
                scenario=scenario,
                step=step,
                code=f"{field}_unexpected",
                message=f"`{field}` contains excluded item(s).",
                expected={"excludes": excludes},
                actual=actual,
            )
        )
    return failures


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
