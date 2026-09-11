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
        # Keep one authored source; materialize the standard skill layout only
        # in the build tree. MANIFEST.in carries the source through sdist builds.
        skill = Path(__file__).resolve().parent / "dataviz-skill.md"
        destination = target / "skills" / "dataviz" / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(skill.read_bytes())

    def get_outputs(self, include_bytecode: bool = True) -> list[str]:
        outputs = super().get_outputs(include_bytecode)
        skill = str(Path(self.build_lib) / "dataviz" / "skills" / "dataviz" / "SKILL.md")
        return outputs if skill in outputs else [*outputs, skill]


setup(cmdclass={"build_py": CleanBuildPy})
