import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('release_evidence', Path(__file__).parents[1] / 'scripts/release_evidence.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_manifest_binds_bytes_and_gates(tmp_path):
    for name in ['demo.whl', 'demo.tar.gz', 'demo.zip']:
        (tmp_path / name).write_bytes(b'fixture')
    gates = {key: {'result': 'success'} for key in release.REQUIRED_GATES}
    first = release.manifest(tmp_path, 'revision', 'https://example.test/run/1', gates)
    assert len(first['artifacts']) == 3
    (tmp_path / 'demo.whl').write_bytes(b'changed')
    second = release.manifest(tmp_path, 'revision', 'https://example.test/run/1', gates)
    assert first['artifacts'] != second['artifacts']
    for result in ['failure', 'cancelled', 'skipped']:
        gates['browsers']['result'] = result
        with pytest.raises(ValueError, match='success'):
            release.manifest(tmp_path, 'revision', 'https://example.test/run/1', gates)


def test_release_manifest_rejects_incomplete_artifacts(tmp_path):
    gates = {key: {'result': 'success'} for key in release.REQUIRED_GATES}
    with pytest.raises(ValueError, match='present'):
        release.manifest(tmp_path, 'revision', 'https://example.test/run/1', gates)
