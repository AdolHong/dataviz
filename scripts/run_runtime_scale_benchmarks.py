"""Run the fixed 10K/100K/1M browser Runtime matrix and save raw evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "benchmarks" / "scale-workspace"
SIZES = (10_000, 100_000, 1_000_000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", default="chromium", choices=("chromium", "firefox", "webkit"))
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    runs = []
    for row_count in SIZES:
        command = [
            sys.executable,
            "-m",
            "dataviz.cli",
            "benchmark",
            str(WORKSPACE),
            "runtime-scale",
            "--browser-runtime",
            "--browser",
            args.browser,
            "--repeat",
            str(args.repeat),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--query-param",
            f"row_count={row_count}",
            "--format",
            "json",
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        runs.append({"row_count": row_count, "result": payload["browser_runtime"]})
        print(f"completed {row_count:,} rows", flush=True)

    evidence = {
        "schema": "dataviz/runtime-scale-matrix/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(WORKSPACE.relative_to(ROOT)),
        "browser": args.browser,
        "repeat": args.repeat,
        "sizes": list(SIZES),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
