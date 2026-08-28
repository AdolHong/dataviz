from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dataviz.authoring import scaffold_recipe


ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "examples" / "minimal-workspace"


@pytest.mark.e2e
def test_visual_check_report_emits_geometry_contract(tmp_path: Path):
    # visual-check owns a complete synchronous Playwright lifecycle. Execute it
    # as a real CLI process so pytest-playwright's asyncio loop cannot leak into
    # that lifecycle and produce a false product failure.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dataviz.cli",
            "visual-check",
            str(MINIMAL),
            "sales-overview",
            "--target",
            "report",
            "--browser",
            "chromium",
            "--viewport",
            "1200x800",
            "--output",
            str(tmp_path),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])
            ),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "dataviz/visual-check/v1"
    assert payload["status"] == "passed"
    assert payload["diagnostics"] == []
    assert Path(payload["screenshots"][0]).is_file()
    assert (tmp_path / "visual-check.json").is_file()


@pytest.mark.e2e
@pytest.mark.parametrize("profile", ["minimal", "interactive", "custom-renderer"])
def test_progressive_scaffold_profile_passes_visual_check(
    profile: str, tmp_path: Path
):
    dashboard = f"{profile}-example"
    workspace = tmp_path / "workspace"
    for relative, content in scaffold_recipe(profile, dashboard)["files"].items():
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    output = tmp_path / "visual"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dataviz.cli",
            "visual-check",
            str(workspace),
            dashboard,
            "--target",
            "both",
            "--browser",
            "chromium",
            "--viewport",
            "1200x800",
            "--output",
            str(output),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])
            ),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["targets"] == ["report", "server"]
    assert payload["diagnostics"] == []
