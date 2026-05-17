from __future__ import annotations

import argparse
import json
from typing import Any

from .io import read_structured_file
from .models import AgentCard, ToolCard
from .policy import load_policy_file
from .project import ControlPlaneProject
from .templates import write_starter_project
from .onboarding import write_intake_templates
from .portal import run_portal
from .scenarios import run_scenario_tests
from .validation import validate_project


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=False, default=str))


def validate_agent(path: str) -> None:
    data = read_structured_file(path)
    agent = AgentCard(**data)
    _print_json({"status": "valid", "agent": agent.to_dict()})


def validate_tool(path: str) -> None:
    data = read_structured_file(path)
    tool = ToolCard(**data)
    _print_json({"status": "valid", "tool": tool.to_dict()})


def validate_policy(path: str) -> None:
    rules = load_policy_file(path)
    _print_json({"status": "valid", "rules": [rule.to_dict() for rule in rules]})


def validate_project_command(path: str, json_output: bool = False) -> int:
    report = validate_project(path)
    if json_output:
        _print_json(report.to_dict())
    else:
        print(report.to_markdown())
    return 0 if report.valid else 1


def init_project(path: str, overwrite: bool = False) -> None:
    target = write_starter_project(path, overwrite=overwrite)
    print(f"Created Agent Control Plane starter project at {target}")
    print("Next steps:")
    print(f"  agentctl validate {target}")
    print(f"  agentctl test {target}")
    print(f"  agentctl review {target}")
    print(f"  agentctl assess {target}")
    print(f"  agentctl portal {target}")


def init_intake(path: str) -> None:
    target = write_intake_templates(path)
    print(f"Created non-technical intake templates at {target}")


def review_project(path: str, agent_id: str | None = None) -> None:
    project = ControlPlaneProject.load(path)
    if agent_id:
        print(project.review_markdown(agent_id))
    else:
        for agent in project.agents:
            print(project.review_markdown(agent.agent_id))
            print("\n" + "=" * 80 + "\n")


def assess_project(path: str, agent_id: str | None = None, json_output: bool = False) -> None:
    project = ControlPlaneProject.load(path)
    reports = []
    agents = [project.get_agent(agent_id)] if agent_id else project.agents
    for agent in agents:
        report = project.readiness_report(agent.agent_id)
        reports.append(report)
    if json_output:
        _print_json([r.to_dict() for r in reports])
    else:
        for report in reports:
            print(report.to_markdown())
            print("\n" + "=" * 80 + "\n")


def inventory(path: str) -> None:
    project = ControlPlaneProject.load(path)
    _print_json(project.inventory_summary())


def simulate(
    path: str,
    agent_id: str,
    tool_name: str,
    args_json: str,
    user_json: str | None = None,
    context_json: str | None = None,
) -> None:
    project = ControlPlaneProject.load(path)
    args = json.loads(args_json)
    user = json.loads(user_json) if user_json else {}
    context = json.loads(context_json) if context_json else {}
    result = project.simulate(agent_id=agent_id, tool_name=tool_name, args=args, user=user, context=context)
    _print_json(result)


def test_project(path: str, scenarios_path: str | None = None, json_output: bool = False) -> int:
    report = run_scenario_tests(path, scenarios_path)
    if json_output:
        _print_json(report.to_dict())
    else:
        print(report.to_markdown())
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentctl", description="Agent Control Plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a human-friendly starter project")
    p_init.add_argument("path")
    p_init.add_argument("--overwrite", action="store_true")

    p_intake = sub.add_parser("init-intake", help="Create blank intake templates for governance teams")
    p_intake.add_argument("path")

    p_inv = sub.add_parser("inventory", help="Show project inventory")
    p_inv.add_argument("path")

    p_validate = sub.add_parser("validate", help="Validate a project as a production gate")
    p_validate.add_argument("path")
    p_validate.add_argument("--json", action="store_true")

    p_review = sub.add_parser("review", help="Plain-language review for non-technical reviewers")
    p_review.add_argument("path")
    p_review.add_argument("--agent")

    p_assess = sub.add_parser("assess", help="Readiness assessment for governance onboarding")
    p_assess.add_argument("path")
    p_assess.add_argument("--agent")
    p_assess.add_argument("--json", action="store_true")

    p_sim = sub.add_parser("simulate", help="Dry-run a tool call and see the policy decision")
    p_sim.add_argument("path")
    p_sim.add_argument("--agent", required=True)
    p_sim.add_argument("--tool", required=True)
    p_sim.add_argument("--args", required=True, help='JSON object, e.g. {"amount": 25}')
    p_sim.add_argument("--user", help='Optional JSON user context, e.g. {"fraud_flag": false}')
    p_sim.add_argument("--context", help='Optional JSON runtime context, e.g. {"input": "user message"}')

    p_test = sub.add_parser("test", help="Run YAML governance scenario regression tests")
    p_test.add_argument("path")
    p_test.add_argument("--scenarios", help="Scenario file or directory. Defaults to <project>/scenarios.")
    p_test.add_argument("--json", action="store_true")

    p_portal = sub.add_parser("portal", help="Run a local non-technical onboarding portal")
    p_portal.add_argument("path")
    p_portal.add_argument("--host", default="127.0.0.1")
    p_portal.add_argument("--port", type=int, default=8765)

    p_agent = sub.add_parser("validate-agent", help="Validate an AgentCard JSON/YAML file")
    p_agent.add_argument("path")

    p_tool = sub.add_parser("validate-tool", help="Validate a ToolCard JSON/YAML file")
    p_tool.add_argument("path")

    p_policy = sub.add_parser("validate-policy", help="Validate a policy JSON/YAML file")
    p_policy.add_argument("path")

    args = parser.parse_args(argv)
    if args.command == "init":
        init_project(args.path, args.overwrite)
    elif args.command == "init-intake":
        init_intake(args.path)
    elif args.command == "inventory":
        inventory(args.path)
    elif args.command == "validate":
        return validate_project_command(args.path, args.json)
    elif args.command == "review":
        review_project(args.path, args.agent)
    elif args.command == "assess":
        assess_project(args.path, args.agent, args.json)
    elif args.command == "simulate":
        simulate(args.path, args.agent, args.tool, args.args, args.user, args.context)
    elif args.command == "test":
        return test_project(args.path, args.scenarios, args.json)
    elif args.command == "portal":
        run_portal(args.path, host=args.host, port=args.port)
    elif args.command == "validate-agent":
        validate_agent(args.path)
    elif args.command == "validate-tool":
        validate_tool(args.path)
    elif args.command == "validate-policy":
        validate_policy(args.path)
    else:  # pragma: no cover
        parser.error("unknown command")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
