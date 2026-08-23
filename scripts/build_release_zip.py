from __future__ import annotations

import argparse
import tomllib
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".dataviz"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}


def included_files() -> list[Path]:
    files = [
        ROOT / "pyproject.toml",
        ROOT / "setup.py",
        ROOT / "README.md",
        ROOT / "DESIGN.md",
        ROOT / "plan.md",
        ROOT / "MANIFEST.in",
        ROOT / "CHANGELOG.md",
    ]
    files.extend(path for path in (ROOT / "docs").rglob("*.md") if path.is_file())
    files.extend(
        path
        for path in (ROOT / "src" / "dataviz").rglob("*")
        if path.is_file()
        and not EXCLUDED_PARTS.intersection(path.parts)
        and path.suffix not in EXCLUDED_SUFFIXES
        and path.name not in EXCLUDED_SUFFIXES
    )
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def build_release_zip(output_directory: Path) -> Path:
    output = output_directory.resolve() / f"workspace-dataviz-{PROJECT['version']}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    files = included_files()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    size = output.stat().st_size
    digest = sha256(output.read_bytes()).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"Built {output}")
    print(f"Files: {len(files)}")
    print(f"Bytes: {size}")
    print(f"SHA256: {digest}")
    print(f"Checksum: {checksum}")
    print(f"Install: python -m pip install {output.name}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the pip-installable source ZIP")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "dist",
        help="Destination directory (default: project dist/)",
    )
    args = parser.parse_args()
    build_release_zip(args.output_dir)


if __name__ == "__main__":
    main()
