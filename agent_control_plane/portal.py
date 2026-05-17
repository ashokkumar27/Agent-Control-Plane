from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .project import ControlPlaneProject
from .io import write_structured_file

STYLE = """
<style>
body { font-family: system-ui, -apple-system, Segoe UI, sans-serif; max-width: 1100px; margin: 32px auto; padding: 0 20px; line-height: 1.5; }
header { border-bottom: 1px solid #ddd; margin-bottom: 24px; }
.card { border: 1px solid #ddd; border-radius: 12px; padding: 18px; margin: 16px 0; background: #fff; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
.badge { display: inline-block; padding: 3px 8px; border: 1px solid #aaa; border-radius: 999px; font-size: 12px; margin-right: 5px; }
label { display: block; font-weight: 600; margin-top: 12px; }
input, textarea, select { width: 100%; padding: 9px; border: 1px solid #bbb; border-radius: 8px; }
textarea { min-height: 90px; }
button { margin-top: 14px; padding: 10px 14px; border: 0; border-radius: 8px; cursor: pointer; }
pre { white-space: pre-wrap; background: #f7f7f7; padding: 14px; border-radius: 10px; overflow: auto; }
a { color: #0645ad; }
</style>
"""


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>{STYLE}</head>
<body><header><h1>Agent Control Plane</h1><p>A non-technical onboarding portal for AI agent governance.</p>
<nav><a href='/'>Dashboard</a> · <a href='/review'>Plain-language review</a> · <a href='/new-agent'>New agent intake</a> · <a href='/new-tool'>New tool intake</a></nav></header>{body}</body></html>""".encode("utf-8")


def run_portal(project_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    project_root = Path(project_path).resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, title: str, body: str) -> None:
            payload = _page(title, body)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _project(self) -> ControlPlaneProject:
            return ControlPlaneProject.load(project_root)

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                project = self._project()
                cards = [
                    f"<div class='card'><h3>Agents</h3><p>{len(project.agents)} registered</p><pre>{html.escape(json.dumps([a.agent_id for a in project.agents], indent=2))}</pre></div>",
                    f"<div class='card'><h3>Tools</h3><p>{len(project.tools)} registered</p><pre>{html.escape(json.dumps([t.name for t in project.tools], indent=2))}</pre></div>",
                    f"<div class='card'><h3>Policies</h3><p>{len(project.policies)} rules</p><pre>{html.escape(json.dumps([p.rule_id for p in project.policies], indent=2))}</pre></div>",
                ]
                body = "<div class='grid'>" + "".join(cards) + "</div><div class='card'><h2>What to do next</h2><ol><li>Open the plain-language review.</li><li>Check missing owners, high-risk tools, and approval rules.</li><li>Use the intake forms to add agents or tools.</li></ol></div>"
                return self._send(200, "Dashboard", body)
            if path == "/review":
                project = self._project()
                body = ""
                for agent in project.agents:
                    body += f"<div class='card'><pre>{html.escape(project.review_markdown(agent.agent_id))}</pre></div>"
                return self._send(200, "Review", body or "<p>No agents found.</p>")
            if path == "/new-agent":
                body = """
                <div class='card'><h2>New agent intake</h2>
                <form method='post' action='/create-agent'>
                <label>Agent ID</label><input name='agent_id' placeholder='customer_support_agent' required>
                <label>Business owner</label><input name='business_owner' placeholder='Head of Support' required>
                <label>Technical owner</label><input name='technical_owner' placeholder='AI Platform Team' required>
                <label>Purpose in plain language</label><textarea name='purpose' required></textarea>
                <label>Risk tier</label><select name='risk_tier'><option>low</option><option>medium</option><option selected>high</option><option>critical</option></select>
                <label>Allowed tools, comma separated</label><input name='allowed_tools' placeholder='get_order, issue_refund'>
                <label>Data processed, comma separated</label><input name='data_processed' placeholder='pii, confidential'>
                <button type='submit'>Create AgentCard YAML</button>
                </form></div>
                """
                return self._send(200, "New agent", body)
            if path == "/new-tool":
                body = """
                <div class='card'><h2>New tool intake</h2>
                <form method='post' action='/create-tool'>
                <label>Tool name</label><input name='name' placeholder='issue_refund' required>
                <label>Description</label><textarea name='description' required></textarea>
                <label>Tool type</label><select name='tool_type'><option>read_only</option><option>side_effecting</option><option>external_communication</option><option>database</option><option>code_execution</option></select>
                <label>Risk tier</label><select name='risk_tier'><option>low</option><option>medium</option><option selected>high</option><option>critical</option></select>
                <label>Side effect?</label><select name='side_effect'><option value='false'>No</option><option value='true'>Yes</option></select>
                <label>Data access, comma separated</label><input name='data_access' placeholder='pii, confidential'>
                <button type='submit'>Create ToolCard YAML</button>
                </form></div>
                """
                return self._send(200, "New tool", body)
            return self._send(404, "Not found", "<p>Page not found.</p>")

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            def field(name: str, default: str = "") -> str:
                return data.get(name, [default])[0].strip()
            def csv(name: str) -> list[str]:
                return [x.strip() for x in field(name).split(",") if x.strip()]

            path = urlparse(self.path).path
            if path == "/create-agent":
                agent_id = field("agent_id")
                payload = {
                    "agent_id": agent_id,
                    "owner": field("business_owner", "unknown_owner").replace(" ", "_").lower(),
                    "business_owner": field("business_owner"),
                    "technical_owner": field("technical_owner"),
                    "purpose": field("purpose"),
                    "risk_tier": field("risk_tier", "medium"),
                    "affected_users": ["to_be_confirmed"],
                    "data_processed": csv("data_processed"),
                    "allowed_tools": csv("allowed_tools"),
                    "prohibited_tools": [],
                    "human_oversight": {"required_for": ["high-impact actions", "sensitive data access"]},
                }
                target = project_root / "agents" / f"{agent_id}.yaml"
                write_structured_file(target, payload)
                return self._send(200, "Created", f"<div class='card'><h2>Created</h2><p>Saved {html.escape(str(target))}</p><pre>{html.escape(json.dumps(payload, indent=2))}</pre><p><a href='/review'>Review now</a></p></div>")

            if path == "/create-tool":
                name = field("name")
                payload = {
                    "name": name,
                    "description": field("description"),
                    "tool_type": field("tool_type", "read_only"),
                    "risk_tier": field("risk_tier", "low"),
                    "side_effect": field("side_effect") == "true",
                    "data_access": csv("data_access"),
                    "allowed_roles": [],
                    "approval_rules": [],
                    "tags": [],
                }
                target = project_root / "tools" / f"{name}.yaml"
                write_structured_file(target, payload)
                return self._send(200, "Created", f"<div class='card'><h2>Created</h2><p>Saved {html.escape(str(target))}</p><pre>{html.escape(json.dumps(payload, indent=2))}</pre><p><a href='/'>Dashboard</a></p></div>")
            return self._send(404, "Not found", "<p>Page not found.</p>")

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Agent Control Plane portal running at http://{host}:{port}")
    print(f"Project: {project_root}")
    server.serve_forever()
