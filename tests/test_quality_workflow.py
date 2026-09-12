"""Keep the CI entry points executable, not merely documented strings."""
from pathlib import Path
import shlex

import yaml
from typer.testing import CliRunner

from dataviz.cli import app


ROOT = Path(__file__).resolve().parents[1]


def test_workflow_cli_commands_parse_against_installed_contract():
    workflow = yaml.safe_load((ROOT / ".github/workflows/quality.yml").read_text())
    commands = set()
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            for line in step.get("run", "").splitlines():
                if 'dataviz components' not in line and '"$environment/bin/dataviz" components' not in line:
                    continue
                tokens = shlex.split(line)
                if "dataviz" in tokens:
                    args = tokens[tokens.index("dataviz") + 1:]
                elif '"$environment/bin/dataviz"' in line:
                    args = tokens[1:]
                else:
                    continue
                if args[:1] == ["components"]:
                    commands.add(tuple(args))
    assert commands == {("components", "check", "--format", "json")}
    for command in commands:
        result = CliRunner().invoke(app, list(command))
        assert result.exit_code == 0, result.output


def test_distribution_publication_waits_for_quality_jobs():
    jobs = yaml.safe_load((ROOT / ".github/workflows/quality.yml").read_text())["jobs"]
    assert set(jobs["distributions"]["needs"]) == {
        "python-contracts", "macos-noneditable", "javascript-syntax", "browsers",
    }


def test_browser_failure_upload_is_conditional_and_bounded():
    jobs = yaml.safe_load((ROOT / '.github/workflows/quality.yml').read_text())['jobs']
    install = next(step['run'] for step in jobs['browsers']['steps'] if 'playwright install' in step.get('run', ''))
    assert 'chromium ${{ matrix.browser }}' in install
    browser_steps = jobs['browsers']['steps']
    run = next(step['run'] for step in browser_steps if step.get('name') == 'Run verified browser suite')
    assert 'scripts/test_browsers.py --fetch-assets' in run
    assert '--browsers ${{ matrix.browser }}' in run
    assert '--output-dir' in run
    cache = next(step for step in browser_steps if step.get('uses', '').startswith('actions/cache'))
    assert cache['with']['path'] == '.browser-test-assets'
    assert "hashFiles('tests/e2e/assets.json')" in cache['with']['key']
    upload = next(step for step in jobs['browsers']['steps'] if step.get('uses', '').startswith('actions/upload-artifact'))
    assert upload['if'] == 'failure()'
    assert upload['with']['retention-days'] == 7
    assert 'matrix.browser' in upload['with']['name']
    distribution = jobs['distributions']['steps']
    manifest = next(index for index, step in enumerate(distribution) if step.get('name') == 'Bind artifacts to successful quality gates')
    smoke = next(index for index, step in enumerate(distribution) if step.get('name') == 'Clean-install and smoke-test each format')
    assert smoke < manifest
    assert 'release-evidence.json' in distribution[-1]['with']['path']
