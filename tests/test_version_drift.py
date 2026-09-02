from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_version_drift_check_accepts_the_current_source_tree():
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "scripts/check_version_drift.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f"project {version}" in completed.stdout
    assert f"source  {version}" in completed.stdout
    assert f"active  {version}" in completed.stdout


def test_version_drift_check_gives_direct_source_and_reinstall_actions(tmp_path: Path):
    package = tmp_path / "dataviz"
    package.mkdir()
    (package / "__init__.py").write_text('__version__ = "0.0.0"\n')
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path)
    completed = subprocess.run(
        [sys.executable, "scripts/check_version_drift.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "PYTHONPATH=src .venv/bin/python -m dataviz.cli version" in completed.stderr
    assert "uv sync --extra dev --no-editable --reinstall-package ai-dataviz" in completed.stderr
