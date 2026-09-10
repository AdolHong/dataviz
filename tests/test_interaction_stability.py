from pathlib import Path
import subprocess
import pytest
import yaml


def test_cascade_parent_field_is_validated_without_parent_view_filter(stable_analysis):
    from dataviz.workspace import load_workspace
    from dataviz.errors import ValidationFailure

    root, _ = stable_analysis
    dashboard = load_workspace(root).dashboard("stability")
    path = dashboard.root / "dashboard.yaml"
    payload = yaml.safe_load(path.read_text())
    source = next(item for item in payload["sources"] if isinstance(item, dict) and item.get("id") == "catalog")
    source["outputs"]["main"]["schema"] = [{"name": "item", "dtype": "str"}]
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValidationFailure) as error:
        _ = load_workspace(root).dashboard("stability").dependency_contract
    assert error.value.details["code"] == "control_dependency_field_unknown"


def test_production_interaction_state_contracts():
    script = Path(__file__).parent / "js" / "interaction-stability.mjs"
    result = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_canvas_generation_watermark_is_scoped(stable_analysis):
    from dataviz.server.manager import RunManager
    from dataviz.workspace import load_workspace

    root, _ = stable_analysis
    manager = RunManager(load_workspace(root))
    manager.generations.update({
        ("tab-a", "stability", "run-a", "slice"): 7,
        ("tab-b", "stability", "run-a", "slice"): 99,
        ("tab-a", "other", "run-a", "slice"): 100,
        ("tab-a", "stability", "run-b", "slice"): 200,
    })
    assert manager.interaction_generations("tab-a", "stability", "run-a") == {"slice": 7}
    assert manager.interaction_generations("new", "stability", "run-a") == {}
