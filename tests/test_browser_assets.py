import importlib.util
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('browser_runner', ROOT / 'scripts/test_browsers.py')
runner = importlib.util.module_from_spec(spec)
with patch.object(sys, 'path', [str(ROOT / 'scripts'), *sys.path]):
    spec.loader.exec_module(runner)


def test_asset_manifest_is_unique_and_versioned():
    assets = json.loads(runner.MANIFEST.read_text())
    assert len({a['file'] for a in assets}) == len(assets)
    assert len({a['url'] for a in assets}) == len(assets)
    for asset in assets:
        assert not Path(asset['file']).is_absolute()
        assert '..' not in Path(asset['file']).parts
        assert len(bytes.fromhex(asset['sha256'])) == 32
        assert asset['url'].startswith('https://')
    from dataviz.workspace.models import RuntimeDefinition
    assert all(f"@{RuntimeDefinition().perspective_version}/" in a['url']
               for a in assets if a['file'].startswith('perspective/'))


def test_cache_missing_or_modified_bytes_fail_without_network(tmp_path, monkeypatch):
    content = b'real pinned fixture'
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps([{'file': 'asset.js', 'url': 'https://invalid.example/asset.js',
                                   'sha256': hashlib.sha256(content).hexdigest()}]))
    monkeypatch.setattr(runner, 'MANIFEST', manifest)
    def forbidden(*args, **kwargs):
        raise AssertionError('Existing cache must not access network')
    monkeypatch.setattr(runner, 'urlopen', forbidden)
    directory = tmp_path / 'cache'
    with pytest.raises(RuntimeError, match='Missing'):
        runner.prepare_assets(directory, False)
    directory.mkdir()
    asset = directory / 'asset.js'
    asset.write_bytes(content)
    runner.prepare_assets(directory, False)
    asset.write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='Checksum mismatch'):
        runner.prepare_assets(directory, True)
    assert asset.read_bytes() == b'changed'


def test_runner_continues_after_failure_and_preserves_logs(tmp_path, monkeypatch):
    output = tmp_path / 'evidence'
    monkeypatch.setattr(runner.sys, 'argv', ['test_browsers.py', '--output-dir', str(output)])
    monkeypatch.setattr(runner, 'prepare_assets', lambda *args: None)
    calls = []
    def run(command, *, cwd, env, log, progress, timeout):
        browser = env['DATAVIZ_BROWSER']
        calls.append(browser)
        log.write_text(f'{browser}: real command stand-in\n')
        return {'exit_code':124 if browser == 'firefox' else 0, 'timed_out':browser == 'firefox', 'last_phase':{}}
    monkeypatch.setattr(runner, 'run_supervised', run)
    assert runner.main() == 1
    assert sorted(calls) == ['chromium', 'firefox', 'webkit']
    summary = json.loads((output / 'summary.json').read_text())
    assert [item['exit_code'] for item in summary['results']] == [0, 124, 0]
    assert summary['results'][1]['timed_out']
    assert 'tests/e2e' in summary['command']
    assert not any(arg.startswith('--ignore=') for arg in summary['results'][0]['command'])
    for result in summary['results'][1:]:
        assert all(f'--ignore={path}' in result['command'] for path in runner.CHROMIUM_CLI_TESTS)
    original = (output / 'chromium.log').read_bytes()
    with pytest.raises(RuntimeError, match='Refusing to overwrite'):
        runner.main()
    assert (output / 'chromium.log').read_bytes() == original


@pytest.mark.parametrize('suite', ['components', 'core', 'extended', 'full'])
def test_runner_limits_requested_suite_and_engine(tmp_path, monkeypatch, suite):
    monkeypatch.setattr(runner.sys, 'argv', [
        'test_browsers.py', '--suite', suite, '--browsers', 'firefox',
        '--output-dir', str(tmp_path / 'evidence'), '--', '-k', 'specific_case',
    ])
    monkeypatch.setattr(runner, 'prepare_assets', lambda *args: None)
    calls = []
    def run(command, *, cwd, env, log, progress, timeout):
        calls.append((command, env['DATAVIZ_BROWSER']))
        log.write_text('ok\n')
        return {'exit_code':0, 'timed_out':False, 'last_phase':{}}
    monkeypatch.setattr(runner, 'run_supervised', run)
    assert runner.main() == 0
    assert len(calls) == 1
    command, browser = calls[0]
    assert browser == 'firefox'
    expected = ['tests/e2e'] if suite == 'full' else [f'tests/e2e/{suite}']
    if suite == 'extended':
        expected += ['tests/e2e/test_failure_artifacts.py']
    assert command[3:command.index('-q')] == expected
    assert command[command.index('-k'):command.index('-k') + 2] == ['-k', 'specific_case']
    ignored = [arg for arg in command if arg.startswith('--ignore=')]
    assert ignored == ([f'--ignore={path}' for path in runner.CHROMIUM_CLI_TESTS]
                       if suite in {'extended', 'full'} else [])
