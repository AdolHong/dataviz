from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from build_release_zip import PROJECT, ROOT, source_version


def main() -> int:
    expected = str(PROJECT["version"])
    source = source_version()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, dataviz; "
                "print(json.dumps({'version': dataviz.__version__, 'path': dataviz.__file__}))"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        print(completed.stderr.strip() or "Could not import dataviz.", file=sys.stderr)
        return 1
    active = json.loads(completed.stdout)
    print(f"project {expected}")
    print(f"source  {source}")
    print(f"active  {active['version']}  {Path(active['path']).resolve()}")
    if expected == source == active["version"]:
        return 0
    print(
        "Version drift detected.\n"
        "Run current source:\n"
        "  PYTHONPATH=src .venv/bin/python -m dataviz.cli version\n"
        "Refresh installed CLI:\n"
        "  uv sync --extra dev --no-editable --reinstall-package ai-dataviz",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
