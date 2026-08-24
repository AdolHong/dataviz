from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    ROOT / "examples",
    ROOT / "src" / "dataviz" / "gallery",
    ROOT / "tests" / "fixtures",
)
GENERATED_DIRECTORIES = {".dataviz", "dist", "__pycache__"}
GENERATED_FILES = {".DS_Store", "adapters.local.yaml"}


def main() -> int:
    unexpected: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.name in GENERATED_FILES or (
                path.is_dir() and path.name in GENERATED_DIRECTORIES
            ):
                unexpected.append(path)
    if unexpected:
        print("Repository fixtures contain generated or local-only state:")
        for path in sorted(set(unexpected)):
            print(f"- {path.relative_to(ROOT)}")
        return 1
    print("Repository fixtures contain no generated or local-only state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
