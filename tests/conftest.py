from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import pytest


@pytest.fixture(scope="module")
def isolated_workspace(tmp_path_factory) -> Callable[[Path], Path]:
    """Copy repository workspaces before a test can create Runtime state in them."""
    root = tmp_path_factory.mktemp("workspace-fixtures")
    copies: dict[Path, Path] = {}

    def copy(source: Path) -> Path:
        resolved = source.resolve()
        if resolved not in copies:
            destination = root / f"{len(copies):02d}-{resolved.name}"
            shutil.copytree(
                resolved,
                destination,
                ignore=shutil.ignore_patterns(
                    ".dataviz",
                    "dist",
                    "__pycache__",
                    "*.pyc",
                    ".DS_Store",
                ),
            )
            copies[resolved] = destination
        return copies[resolved]

    return copy
