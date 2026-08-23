"""Small setuptools hook that keeps incremental wheels free of deleted files."""

from pathlib import Path
from shutil import rmtree

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py


class CleanBuildPy(_build_py):
    """Recreate packaged Dataviz resources instead of reusing stale build/lib data."""

    def run(self) -> None:
        target = Path(self.build_lib) / "dataviz"
        if target.is_dir():
            rmtree(target)
        super().run()


setup(cmdclass={"build_py": CleanBuildPy})
