from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


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
