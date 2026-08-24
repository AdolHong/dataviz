from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Mapping
from pathlib import Path


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Publish one complete file without exposing a partial write."""
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


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, content.encode(encoding))


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading the complete payload into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_copy_file(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Copy one file atomically while calculating and optionally checking its hash."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.tmp"
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
            while chunk := input_stream.read(chunk_size):
                output_stream.write(chunk)
                digest.update(chunk)
            output_stream.flush()
            os.fsync(output_stream.fileno())
        content_hash = digest.hexdigest()
        if expected_sha256 is not None and content_hash != expected_sha256:
            raise ValueError(f"File content hash does not match: {source.name}")
        os.replace(temporary, destination)
        return content_hash
    finally:
        temporary.unlink(missing_ok=True)


def transactional_write_texts(
    root: Path,
    files: Mapping[str, str],
    *,
    overwrite: bool = False,
    encoding: str = "utf-8",
) -> list[Path]:
    """Publish a small file set with preflight checks and rollback.

    A filesystem cannot expose several independent files atomically. This helper
    provides the useful authoring guarantee instead: every target is validated
    before the first write, each file is atomically replaced, and a failed
    publish restores every file that was already changed.
    """
    root = root.resolve()
    if root.exists() and not root.is_dir():
        raise NotADirectoryError(f"Output path is not a directory: {root}")

    targets: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for relative, content in files.items():
        relative_path = Path(relative)
        if relative_path.is_absolute():
            raise ValueError(f"Recipe path must be relative: {relative}")
        destination = (root / relative_path).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(f"Recipe path escapes output directory: {relative}")
        if destination in seen:
            raise ValueError(f"Recipe paths resolve to the same file: {relative}")
        if destination.exists() and not destination.is_file():
            raise IsADirectoryError(f"Recipe target is not a file: {relative}")
        seen.add(destination)
        targets.append((destination, content))

    conflicts = [
        str(destination.relative_to(root))
        for destination, _ in targets
        if destination.exists() and not overwrite
    ]
    if conflicts:
        raise FileExistsError(
            "Refusing to overwrite existing files: " + ", ".join(conflicts)
        )

    previous = {
        destination: destination.read_bytes() if destination.is_file() else None
        for destination, _ in targets
    }
    existing_directories: set[Path] = set()
    for destination, _ in targets:
        parent = destination.parent
        while parent.is_relative_to(root):
            if parent.exists():
                existing_directories.add(parent)
            if parent == root:
                break
            parent = parent.parent

    published: list[Path] = []
    try:
        for destination, content in targets:
            atomic_write_text(destination, content, encoding=encoding)
            published.append(destination)
    except BaseException:
        for destination in reversed(published):
            original = previous[destination]
            if original is None:
                destination.unlink(missing_ok=True)
            else:
                atomic_write_bytes(destination, original)
        created_directories = {
            parent
            for destination, _ in targets
            for parent in destination.parents
            if parent.is_relative_to(root) and parent not in existing_directories
        }
        for directory in sorted(
            created_directories,
            key=lambda value: len(value.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except (FileNotFoundError, OSError):
                pass
        raise
    return [destination for destination, _ in targets]
