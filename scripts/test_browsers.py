"""One entry point for verified real assets and the three-browser E2E matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
from browser_watchdog import run_supervised


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tests/e2e/assets.json'
CHROMIUM_CLI_TESTS = [
    'tests/e2e/test_analysis_browser.py',
    'tests/e2e/test_visual_check_cli.py',
]


def prepare_assets(directory: Path, fetch: bool) -> None:
    for asset in json.loads(MANIFEST.read_text()):
        target = directory / asset['file']
        if target.is_file():
            content = target.read_bytes()
        elif fetch:
            print(f"Fetching {asset['file']}", flush=True)
            with urlopen(asset['url'], timeout=60) as response:
                content = response.read()
        else:
            raise RuntimeError(f'Missing {target}; run with --fetch-assets once')
        if hashlib.sha256(content).hexdigest() != asset['sha256']:
            raise RuntimeError(f'Checksum mismatch: {target}; inspect upstream changes, do not bypass')
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-assets', action='store_true', help='Fetch missing pinned upstream files')
    parser.add_argument('--browsers', nargs='+', choices=['chromium', 'firefox', 'webkit'],
                        default=['chromium', 'firefox', 'webkit'])
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--suite', choices=['components', 'core', 'extended', 'full'], default='full',
                        help='Choose scope explicitly; full retained for existing CI callers')
    parser.add_argument('--jobs', type=int, choices=[1, 2, 3], default=3,
                        help='Isolated browser processes in parallel; use 1 for serial diagnosis')
    parser.add_argument('--phase-timeout', type=float, default=180,
                        help='Maximum seconds per setup/call/teardown phase; default 180, no retries')
    parser.add_argument('pytest_args', nargs=argparse.REMAINDER, help='Optional targeted arguments after --')
    args = parser.parse_args()
    if args.phase_timeout <= 0 or not math.isfinite(args.phase_timeout):
        parser.error('--phase-timeout must be a positive finite number')
    assets = Path(os.environ.get('DATAVIZ_E2E_ASSET_DIR', ROOT / '.browser-test-assets')).resolve()
    prepare_assets(assets, args.fetch_assets)
    output = args.output_dir or ROOT / '.test-evidence' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=True)
    extra = args.pytest_args
    if extra[:1] == ['--']:
        extra = extra[1:]
    targets = ['tests/e2e'] if args.suite == 'full' else [f'tests/e2e/{args.suite}']
    if args.suite == 'extended':
        targets += ['tests/e2e/test_analysis_browser.py', 'tests/e2e/test_visual_check_cli.py',
                    'tests/e2e/test_failure_artifacts.py']
    command = [sys.executable, '-m', 'pytest', *targets, '-q', '-o', 'addopts=',
               '--durations=10', *extra]
    results = []
    for browser in args.browsers:
        if (output / f'{browser}.log').exists():
            raise RuntimeError(f'Refusing to overwrite evidence: {output / f"{browser}.log"}')

    def run_browser(browser):
        log = output / f'{browser}.log'
        print(f'{browser}: running; log {log}', flush=True)
        env = {**os.environ, 'DATAVIZ_BROWSER': browser, 'DATAVIZ_E2E_ASSET_DIR': str(assets),
               'DATAVIZ_E2E_ARTIFACT_DIR': str(output.resolve() / 'failures')}
        browser_command = list(command)
        if browser != 'chromium' and args.suite in {'extended', 'full'}:
            # These CLI contracts explicitly launch Chromium regardless of the
            # matrix engine. Run them once, in the Chromium lane, not three times.
            # Remove explicit targets as --ignore does not exclude direct paths.
            browser_command = [part for part in browser_command if part not in CHROMIUM_CLI_TESTS]
            browser_command += [f'--ignore={path}' for path in CHROMIUM_CLI_TESTS]
            print(f'{browser}: Chromium-only CLI contracts belong to the chromium lane', flush=True)
        result = run_supervised(browser_command, cwd=ROOT, env=env, log=log,
                                progress=output / f'{browser}.progress.json', timeout=args.phase_timeout)
        print(f'{browser}: exit {result["exit_code"]}\n' + '\n'.join(log.read_text().splitlines()[-3:]), flush=True)
        return {'browser': browser, **result, 'log': str(log),
                'command': browser_command}

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for future in as_completed([executor.submit(run_browser, browser) for browser in args.browsers]):
            results.append(future.result())
            results.sort(key=lambda result: args.browsers.index(result['browser']))
            (output / 'summary.json').write_text(json.dumps({'command': command, 'results': results}, indent=2))
    return int(any(result['exit_code'] for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
