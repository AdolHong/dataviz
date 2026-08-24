from __future__ import annotations

import argparse
import ast
from io import BytesIO
import os
import tomllib
from hashlib import sha256
from pathlib import Path
import uuid
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".dataviz"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}
EXCLUDED_NAMES = {"adapters.local.yaml"}


def source_version() -> str:
    """Read the Runtime version without importing the package or its dependencies."""
    path = ROOT / "src" / "dataviz" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise RuntimeError(f"Could not find a literal __version__ in {path}")


def verify_release_version() -> None:
    runtime_version = source_version()
    if PROJECT["version"] != runtime_version:
        raise RuntimeError(
            "Release version mismatch: "
            f"pyproject.toml={PROJECT['version']} but dataviz.__version__={runtime_version}"
        )


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
        and path.name not in EXCLUDED_NAMES
    )
    included = sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())
    for path in included:
        if not path.is_file():
            raise FileNotFoundError(f"Required release file is missing: {path}")
        if path.is_symlink():
            raise RuntimeError(f"Release inputs cannot be symbolic links: {path}")
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError(f"Release input escapes the repository: {path}")
    return included


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _publish_release_outputs(files: dict[Path, bytes]) -> None:
    """Publish the archive and checksum together, restoring the last good pair on failure."""
    for path in files:
        if path.exists() and not path.is_file():
            raise IsADirectoryError(f"Release output is not a file: {path}")
    previous = {
        path: path.read_bytes() if path.is_file() else None
        for path in files
    }
    published: list[Path] = []
    try:
        for path, content in files.items():
            _atomic_write_bytes(path, content)
            published.append(path)
    except BaseException:
        for path in reversed(published):
            original = previous[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(path, original)
        raise


def build_release_zip(output_directory: Path) -> Path:
    verify_release_version()
    output = output_directory.resolve() / f"workspace-dataviz-{PROJECT['version']}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = included_files()
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    payload = buffer.getvalue()
    with ZipFile(BytesIO(payload)) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"Release ZIP verification failed at {corrupt}")
        expected = [path.relative_to(ROOT).as_posix() for path in files]
        if archive.namelist() != expected:
            raise RuntimeError("Release ZIP file list changed during construction")
    size = len(payload)
    digest = sha256(payload).hexdigest()
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum_payload = f"{digest}  {output.name}\n".encode()
    _publish_release_outputs({output: payload, checksum: checksum_payload})
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
