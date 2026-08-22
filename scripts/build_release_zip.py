from __future__ import annotations

import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
OUTPUT = ROOT / "dist" / f"workspace-dataviz-{PROJECT['version']}.zip"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}


def included_files() -> list[Path]:
    files = [ROOT / "pyproject.toml", ROOT / "README.md"]
    files.extend(
        path
        for path in (ROOT / "src" / "dataviz").rglob("*")
        if path.is_file()
        and not EXCLUDED_PARTS.intersection(path.parts)
        and path.suffix not in EXCLUDED_SUFFIXES
        and path.name not in EXCLUDED_SUFFIXES
    )
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()
    files = included_files()
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    size = OUTPUT.stat().st_size
    print(f"Built {OUTPUT}")
    print(f"Files: {len(files)}")
    print(f"Bytes: {size}")
    print(f"Install: python -m pip install {OUTPUT.name}")


if __name__ == "__main__":
    main()
