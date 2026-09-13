"""Keep layers discoverable and preserve relocated behavior coverage."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_relocated_runtime_functions_remain_discoverable():
    mapping = (ROOT / 'docs/browser-test-migration.md').read_text().splitlines()
    rows = [line.split('`') for line in mapping if line.startswith('| `test_')]
    assert len(rows) == 84
    for row in rows:
        path = ROOT / row[3]
        names = {n.name for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)}
        assert row[1] in names, row[1]
    assert not (ROOT / 'tests/e2e/test_browser_runtime.py').exists()


def test_layers_have_no_duplicate_test_names_or_test_module_imports():
    names = []
    for path in (ROOT / 'tests/e2e').rglob('test_*.py'):
        tree = ast.parse(path.read_text())
        names += [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(part.startswith('test_') for part in (node.module or '').split('.'))
    assert len(names) == len(set(names))


def test_component_host_does_not_boot_dashboard_or_query():
    source = (ROOT / 'tests/e2e/components/conftest.py').read_text()
    assert 'component_runtime_assets' in source
    assert 'tanstack-table-core' in source
    assert 'create_app' not in source and 'Executor' not in source and 'CanvasRenderer' not in source
