from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from dataviz.authoring import build_context_payload
from dataviz.workspace import load_workspace, validate_workspace


def context_size(payload: dict[str, object]) -> dict[str, int]:
    compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    pretty = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return {
        "characters": len(compact),
        "utf8_bytes": len(compact.encode("utf-8")),
        "pretty_lines": pretty.count("\n") + 1,
    }


def _text_metrics(path: Path) -> dict[str, int] | None:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return {
        "files": 1,
        "characters": len(value),
        "utf8_bytes": len(value.encode("utf-8")),
        "lines": len(value.splitlines()),
    }


def build_context_benchmark(workspace_path: Path, dashboard_id: str) -> dict[str, Any]:
    workspace = load_workspace(workspace_path)
    dashboard = workspace.dashboard(dashboard_id)
    full = context_size(build_context_payload(workspace, dashboard))
    focused = {
        f"view:{view_id}": context_size(
            build_context_payload(workspace, dashboard, focus=f"view:{view_id}")
        )
        for view_id in dashboard.views
    }
    focused_bytes = [value["utf8_bytes"] for value in focused.values()]
    files = []
    for path in sorted(value for value in dashboard.root.rglob("*") if value.is_file()):
        if path.suffix.lower() not in {".yaml", ".yml", ".py", ".sql", ".js", ".css", ".html", ".md"}:
            continue
        metric = _text_metrics(path)
        if metric:
            files.append({"path": path.relative_to(dashboard.root).as_posix(), **metric})
    errors = [
        item.as_dict() for item in validate_workspace(workspace) if item.level == "error"
    ]
    return {
        "schema": "dataviz/authoring-context-benchmark/v2",
        "dashboard": dashboard_id,
        "files": files,
        "context": {
            "full": full,
            "focused": focused,
            "summary": {
                "samples": len(focused_bytes),
                "minimum_utf8_bytes": min(focused_bytes, default=0),
                "median_utf8_bytes": int(median(focused_bytes)) if focused_bytes else 0,
                "mean_utf8_bytes": int(mean(focused_bytes)) if focused_bytes else 0,
                "maximum_utf8_bytes": max(focused_bytes, default=0),
            },
        },
        "validation": {"valid": not errors, "errors": errors},
        "not_measured": [
            "model-specific input/output tokens",
            "AI retries and elapsed authoring time",
            "visual quality and interaction usability",
        ],
        "stable_json_bytes": len(json.dumps(full, sort_keys=True).encode("utf-8")),
    }
