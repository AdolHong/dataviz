from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "src"
    / "dataviz"
    / "vendor"
    / "tanstack-table"
    / "tanstack-table-core-9.2.4.min.js"
)
OUTPUT = ROOT / "src" / "dataviz" / "server" / "static" / "tanstack-table-runtime.js"


def build() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    return source if source.endswith("\n") else f"{source}\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the pinned, bundled TanStack Table Core browser Runtime asset."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when tanstack-table-runtime.js differs from the vendored source.",
    )
    args = parser.parse_args()
    content = build()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
        if current != content:
            print(
                "tanstack-table-runtime.js is stale; run: "
                "python tools/build_tanstack_table_runtime.py",
                file=sys.stderr,
            )
            return 1
        print(f"tanstack-table-runtime.js is current ({digest})")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
