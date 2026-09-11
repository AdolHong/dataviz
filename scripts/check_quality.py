"""Explicit, inspectable test profiles; never silently retry or publish."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "shell": ["tests/test_context_controls.py", "tests/test_server.py"],
    "interaction": ["tests/test_interaction_stability.py", "tests/test_control_filter.py", "tests/test_state_snapshot.py"],
    "actions": ["tests/test_action_save.py", "tests/test_server_actions.py", "tests/test_server_action_api.py"],
    "docs": ["tests/test_documentation_search.py", "tests/test_authoring.py", "tests/test_ai_release.py", "tests/test_quality_workflow.py"],
}
JOURNEYS = [
    "analysis_stability_workflow", "operation_panel_shortcuts",
    "navigation_supersedes_slow_page", "query_reload_restores_visible",
    "server_compute_waits_for_required_control_domain",
    "server_action_updates_canvas_in_place", "shared_action_marks_sibling_page",
    "portable_query_tray",
]


def commands(profile: str, area: str | None = None) -> list[list[str]]:
    pytest = [sys.executable, "-m", "pytest", "-o", "addopts="]
    if profile == "targeted":
        if area not in TARGETS:
            raise ValueError("targeted requires an explicit --area")
        return [pytest + TARGETS[area] + ["-m", "not e2e"]]
    if area:
        raise ValueError("--area is only valid for targeted")
    if profile == "journeys":
        return [pytest + ["tests/e2e/test_browser_runtime.py", "-k", " or ".join(JOURNEYS)]]
    if profile == "full":
        return [pytest + ["-m", "not e2e"], pytest + ["tests/e2e"]]
    raise ValueError(f"Unknown profile: {profile}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["targeted", "journeys", "full"])
    parser.add_argument("--area", choices=sorted(TARGETS))
    parser.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="chromium")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        steps = commands(args.profile, args.area)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"profile": args.profile, "area": args.area, "browser": args.browser,
                      "commands": steps, "retries": 0}, ensure_ascii=False), flush=True)
    if args.dry_run:
        return 0
    env = {**os.environ, "DATAVIZ_BROWSER": args.browser}
    for command in steps:
        completed = subprocess.run(command, cwd=ROOT, env=env)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
