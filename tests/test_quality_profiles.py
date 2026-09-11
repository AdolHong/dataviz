import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_quality", ROOT / "scripts/check_quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


def test_targeted_requires_explicit_scope():
    with pytest.raises(ValueError):
        quality.commands("targeted")
    with pytest.raises(ValueError):
        quality.commands("full", "docs")
    for area, files in quality.TARGETS.items():
        assert all((ROOT / file).is_file() for file in files)
        assert quality.commands("targeted", area)[0][-2:] == ["-m", "not e2e"]


def test_journey_selectors_have_real_tests():
    source = (ROOT / "tests/e2e/test_browser_runtime.py").read_text()
    for selector in quality.JOURNEYS:
        assert f"def test_{selector}" in source, selector
    command = quality.commands("journeys")[0]
    assert command[-2] == "-k"
    assert set(command[-1].split(" or ")) == set(quality.JOURNEYS)


def test_full_does_not_silently_reduce_scope():
    unit, browser = quality.commands("full")
    assert unit[-2:] == ["-m", "not e2e"]
    assert browser[-1] == "tests/e2e"
    assert "-k" not in unit + browser


def test_profile_real_pytest_collection_selects_all_named_journeys():
    import subprocess
    command = quality.commands('journeys')[0] + ['--collect-only', '-q']
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for selector in quality.JOURNEYS:
        assert f'::test_{selector}' in result.stdout, result.stdout
