from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from dataviz.rendering import CanvasRenderer
from dataviz.workspace import load_workspace
from dataviz.workspace.models import PresentationControlPanelDefinition, PresentationControlPanelsDefinition


ROOT = Path(__file__).resolve().parents[1]


def test_context_placement_inheritance_does_not_follow_section_override():
    workspace = load_workspace(ROOT / "examples/feature-showcase")
    dashboard = workspace.dashboard("cascade-explorer")
    renderer = CanvasRenderer(workspace)
    result = SimpleNamespace(control_state={})
    render = lambda scope, owner: renderer._context_controls(dashboard, result, scope, owner)
    assert 'data-controls-placement="sidebar"' in render("view", "city-detail")
    dashboard.presentation.control_panels.view.placement = "popover"
    assert 'data-controls-placement="popover"' in render("view", "city-detail")
    dashboard.presentation.control_panels.view.placement = None
    assert 'data-control-parent-section="geography"' in render("view", "city-detail")
    assert 'data-controls-placement="sidebar"' in render("section", "geography")
    from dataviz.workspace.models import PresentationSectionDefinition, PresentationViewDefinition
    dashboard.presentation.sections["geography"] = PresentationSectionDefinition(
        controls=PresentationControlPanelDefinition(placement="popover"))
    assert 'data-controls-placement="sidebar"' in render("view", "city-detail")
    dashboard.presentation.views["city-detail"] = PresentationViewDefinition(
        controls=PresentationControlPanelDefinition(placement="popover"))
    assert 'data-controls-placement="popover"' in render("view", "city-detail")


@pytest.mark.parametrize("scope", ["query", "dashboard"])
def test_placement_rejects_unsupported_scopes(scope):
    with pytest.raises(ValidationError, match="only configurable"):
        PresentationControlPanelsDefinition.model_validate({scope: {"placement": "sidebar"}})


def test_placement_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        PresentationControlPanelDefinition(placement="modal")
