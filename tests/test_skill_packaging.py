"""Exercise our build hook without requiring setuptools in the test runtime."""
from pathlib import Path
import runpy
import sys
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_build_hook_refreshes_skill_and_declares_output(tmp_path, monkeypatch):
    class BaseBuild:
        def run(self):
            pass

        def get_outputs(self, include_bytecode=True):
            return []

    for name in ('setuptools', 'setuptools.command', 'setuptools.command.build_py'):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules['setuptools'].setup = lambda **kwargs: None
    sys.modules['setuptools.command.build_py'].build_py = BaseBuild
    setup = tmp_path / 'setup.py'
    setup.write_bytes((ROOT / 'setup.py').read_bytes())
    source = tmp_path / 'dataviz-skill.md'
    source.write_bytes((ROOT / 'dataviz-skill.md').read_bytes())
    build = runpy.run_path(str(setup))['CleanBuildPy']()
    build.build_lib = str(tmp_path / 'build' / 'lib')
    output = Path(build.build_lib) / 'dataviz' / 'skills' / 'dataviz' / 'SKILL.md'
    build.run()
    assert output.read_bytes() == source.read_bytes()
    assert str(output) in build.get_outputs()
    source.write_text('updated skill\n')
    build.run()
    assert output.read_text() == 'updated skill\n'
    source.unlink()
    with pytest.raises(FileNotFoundError):
        build.run()
