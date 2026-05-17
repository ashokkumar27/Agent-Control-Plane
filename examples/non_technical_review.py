from pathlib import Path
from agent_control_plane import ControlPlaneProject

ROOT = Path(__file__).resolve().parents[1] / "sample_project"
project = ControlPlaneProject.load(ROOT)

print(project.review_markdown())
print(project.readiness_report().to_markdown())
