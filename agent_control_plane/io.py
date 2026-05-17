from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_structured_file(path: str | Path) -> Any:
    """Read JSON or YAML from a path.

    Governance teams usually prefer YAML because it reads like a form.
    Developers can use either JSON or YAML.
    """
    path = Path(path)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml  # type: ignore
        return yaml.safe_load(raw)
    return json.loads(raw)


def write_structured_file(path: str | Path, data: Any) -> None:
    """Write JSON or YAML based on the file suffix."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml  # type: ignore
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def iter_config_files(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in {".json", ".yaml", ".yml"}
    )


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
