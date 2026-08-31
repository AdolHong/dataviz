from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "dataviz" / "server" / "runtime_src"
OUTPUT = ROOT / "src" / "dataviz" / "server" / "static" / "canvas-runtime.js"
PARTS = (
    "00-runtime-manifest.js",
    "10-value-contracts.js",
    "20-runtime-host.js",
    "30-interactive-scheduler.js",
    "40-renderer-lifecycle.js",
    "50-output-store.js",
    "60-renderer-disposal.js",
    "70-control-binding.js",
    "80-state-and-live-scheduler.js",
    "90-bootstrap.js",
)


def build() -> str:
    chunks: list[str] = []
    for name in PARTS:
        path = SOURCE_ROOT / name
        value = path.read_text(encoding="utf-8")
        if not value.endswith("\n"):
            raise ValueError(f"Runtime source module must end with a newline: {path}")
        chunks.append(value)
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the single browser Runtime asset from ordered owner modules."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when canvas-runtime.js differs from the deterministic build.",
    )
    args = parser.parse_args()
    content = build()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
        if current != content:
            print(
                "canvas-runtime.js is stale; run: python tools/build_canvas_runtime.py",
                file=sys.stderr,
            )
            return 1
        print(f"canvas-runtime.js is current ({digest})")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
