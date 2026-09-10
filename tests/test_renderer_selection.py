from pathlib import Path
import subprocess


def test_selection_only_dependencies_update_writers_and_value_consumers():
    script = Path(__file__).parent / "js" / "renderer-selection.mjs"
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
