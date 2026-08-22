from __future__ import annotations

from pathlib import Path

import pytest

from dataviz.errors import WorkspaceError
from dataviz.workspace.naming import (
    dashboard_trash_id,
    dashboard_trash_name,
    decode_dashboard_name,
    decode_dashboard_path,
    encode_dashboard_name,
    folder_id,
    folder_segments,
    folder_trash_id,
    folder_trash_segments,
    validate_segment,
)


def test_dashboard_directory_protocol_round_trips():
    assert encode_dashboard_name(("sales",)) == "sales"
    assert encode_dashboard_name(("Adol", "sales")) == "Adol##sales"
    assert encode_dashboard_name(("Adol", "sales"), trashed=True) == "__TRASH__##Adol##sales"

    location = decode_dashboard_name("__TRASH__##Adol##sales")
    assert location.trashed is True
    assert location.segments == ("Adol", "sales")
    assert location.folder_segments == ("Adol",)


def test_legacy_nested_physical_path_is_read_as_one_logical_path(tmp_path: Path):
    dashboards = tmp_path / "dashboards"
    dashboard = dashboards / "Adol" / "weekly##sales"
    dashboard.mkdir(parents=True)
    location = decode_dashboard_path(dashboards, dashboard)
    assert location.segments == ("Adol", "weekly", "sales")


@pytest.mark.parametrize(
    "value",
    ["", "a##b", "__TRASH__", "CON", "aux.txt", "bad/name", "bad:name", "trailing."],
)
def test_segments_reject_cross_platform_or_reserved_names(value: str):
    with pytest.raises(WorkspaceError):
        validate_segment(value)


def test_navigation_identifiers_are_url_safe_and_round_trip():
    identifier = folder_id(("经营分析", "周报"))
    assert "#" not in identifier and "/" not in identifier
    assert folder_segments(identifier) == ("经营分析", "周报")

    trash_identifier = folder_trash_id(("经营分析", "周报"))
    assert folder_trash_segments(trash_identifier) == ("经营分析", "周报")

    dashboard_identifier = dashboard_trash_id("__TRASH__##经营分析##sales")
    assert dashboard_trash_name(dashboard_identifier) == "__TRASH__##经营分析##sales"
