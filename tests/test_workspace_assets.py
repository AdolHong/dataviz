from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.authoring import build_context_payload
from dataviz.errors import WorkspaceError
from dataviz.execution import Executor
from dataviz.protocols import DASHBOARD_SCHEMA, SOURCE_SCHEMA, WORKSPACE_SCHEMA
from dataviz.rendering import CanvasRenderer
from dataviz.server import create_app
from dataviz.validation import validate_workspace
from dataviz.workspace import bundle_dashboard, load_workspace
import dataviz.workspace.bundle as workspace_bundle


def _asset_workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "asset-map"
    (root / "assets" / "maps").mkdir(parents=True)
    (root / "assets" / "data").mkdir(parents=True)
    (dashboard / "assets").mkdir(parents=True)
    (root / "assets" / "maps" / "china-city.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "深圳"},
                        "geometry": {"type": "Point", "coordinates": [114.1, 22.5]},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "assets" / "data" / "sales.csv").write_text(
        "city,revenue\n深圳,120\n广州,90\n", encoding="utf-8"
    )
    (root / "assets" / "unused.txt").write_text("must-not-bundle", encoding="utf-8")
    (root / "workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": WORKSPACE_SCHEMA,
                "kind": "workspace",
                "id": "asset-workspace",
                "title": "Asset Workspace",
                "assets": {
                    "china-city": {
                        "path": "assets/maps/china-city.geojson",
                        "media_type": "application/geo+json",
                    },
                    "shared-sales": {
                        "path": "assets/data/sales.csv",
                        "media_type": "text/csv",
                    },
                    "unused": {"path": "assets/unused.txt", "media_type": "text/plain"},
                },
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": DASHBOARD_SCHEMA,
                "kind": "dashboard",
                "id": "asset-map",
                "title": "Shared Asset Map",
                "assets": ["china-city"],
                "sources": [
                    {
                        "schema": SOURCE_SCHEMA,
                        "kind": "source",
                        "id": "sales",
                        "type": "file",
                        "path": "asset:shared-sales",
                        "format": "csv",
                        "outputs": {"main": {"kind": "table"}},
                    }
                ],
                "views": [
                    {
                        "id": "map",
                        "title": "Map",
                        "template": "custom",
                        "renderer": "asset-map",
                        "input": "source:sales/main",
                    }
                ],
                "sections": [{"id": "main", "title": "Main", "views": ["map"]}],
                "canvas": {"scripts": ["assets/map.js"]},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (dashboard / "assets" / "map.js").write_text(
        """window.datavizRuntime.registerRenderer('asset-map', {
  async mount(context) {
    const geo = await context.assets.json('china-city');
    context.body.dataset.assetFeature = geo.features[0].properties.name;
    context.body.textContent = `${geo.type}: ${geo.features.length}`;
    return {};
  },
  async update(context) { return this.mount(context); },
  dispose() {},
});
""",
        encoding="utf-8",
    )
    return root


def test_workspace_asset_file_source_server_route_report_and_bundle(tmp_path: Path):
    root = _asset_workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    assert not [item for item in validate_workspace(workspace) if item.level == "error"]
    dashboard = workspace.dashboard("asset-map")

    context = build_context_payload(workspace, dashboard)
    assert set(context["workspace"]["assets"]) == {"china-city", "shared-sales"}
    assert context["workspace_assets"]["china-city"]["browser_available"] is True
    assert context["workspace_assets"]["shared-sales"]["browser_available"] is False
    assert "features" not in json.dumps(context["workspace_assets"], ensure_ascii=False)
    source_context = build_context_payload(workspace, dashboard, focus="source:sales")
    assert set(source_context["workspace_assets"]) == {"china-city", "shared-sales"}
    assert source_context["sources"]["sales"]["data_file"]["reference"] == (
        "asset:shared-sales"
    )

    result = Executor(workspace).run("asset-map")
    assert result.status == "ready"
    table = result.outputs["source:sales/main"]
    assert table.metadata["row_count"] == 2

    client = TestClient(create_app(root))
    response = client.get("/api/dashboards/asset-map/assets/china-city")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    assert response.json()["features"][0]["properties"]["name"] == "深圳"
    etag = response.headers["etag"]
    assert client.get(
        "/api/dashboards/asset-map/assets/china-city",
        headers={"If-None-Match": etag},
    ).status_code == 304
    assert client.get("/api/dashboards/asset-map/assets/shared-sales").status_code == 404
    assert client.get("/api/dashboards/asset-map/assets/unused").status_code == 404

    report = CanvasRenderer(workspace).write_report(
        dashboard,
        result,
        tmp_path / "asset-report.html",
    )
    html = report.read_text(encoding="utf-8")
    assert '"china-city": {"id": "china-city"' in html
    assert '"transport": "text"' in html
    assert "must-not-bundle" not in html
    manifest = json.loads(report.with_suffix(".html.manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"]["china-city"]["media_type"] == "application/geo+json"

    destination = tmp_path / "bundle"
    source_before = {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    payload = bundle_dashboard(workspace, "asset-map", destination)
    assert payload["status"] == "ready"
    assert (destination / "assets" / "maps" / "china-city.geojson").is_file()
    assert (destination / "assets" / "data" / "sales.csv").is_file()
    assert not (destination / "assets" / "unused.txt").exists()
    bundle_manifest = json.loads(
        (destination / "dataviz-bundle.json").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in bundle_manifest["dashboards"][0]["assets"]] == [
        "china-city",
        "shared-sales",
    ]
    assert payload["reused"] == []
    assert source_before == {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(WorkspaceError) as repeated:
        bundle_dashboard(workspace, "asset-map", destination)
    assert repeated.value.details["code"] == "dashboard_bundle_destination_not_empty"
    bundled = load_workspace(destination)
    assert Executor(bundled).run("asset-map").status == "ready"


def test_bundle_accepts_empty_destination_and_never_overwrites_nonempty_directory(
    tmp_path: Path,
):
    root = _asset_workspace(tmp_path / "workspace")
    workspace = load_workspace(root)

    empty = tmp_path / "empty-bundle"
    empty.mkdir()
    assert bundle_dashboard(workspace, "asset-map", empty)["status"] == "ready"

    occupied = tmp_path / "occupied-bundle"
    occupied.mkdir()
    existing = occupied / "shared.sql"
    existing.write_text("select 'newer workspace logic'", encoding="utf-8")
    with pytest.raises(WorkspaceError) as failure:
        bundle_dashboard(workspace, "asset-map", occupied)
    assert failure.value.details["code"] == "dashboard_bundle_destination_not_empty"
    assert existing.read_text(encoding="utf-8") == "select 'newer workspace logic'"
    assert sorted(path.name for path in occupied.iterdir()) == ["shared.sql"]


def test_bundle_rejects_source_change_without_publishing_partial_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    root = _asset_workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    destination = tmp_path / "racing-bundle"
    original_copy = workspace_bundle.atomic_copy_file

    def mutate_after_copy(source: Path, target: Path) -> None:
        original_copy(source, target)
        if source.name == "sales.csv":
            source.write_text(
                source.read_text(encoding="utf-8") + "东莞,80\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(workspace_bundle, "atomic_copy_file", mutate_after_copy)
    with pytest.raises(WorkspaceError) as failure:
        bundle_dashboard(workspace, "asset-map", destination)
    assert failure.value.details["code"] == "dashboard_bundle_source_changed"
    assert not destination.exists()
    assert not list(tmp_path.glob(".racing-bundle.bundle-*"))


def test_unknown_dashboard_asset_invalidates_only_that_dashboard(tmp_path: Path):
    root = _asset_workspace(tmp_path / "workspace")
    definition_path = root / "dashboards" / "asset-map" / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["assets"] = ["missing-map"]
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    entry = workspace.catalog_entry("asset-map")
    assert entry.status == "invalid"
    assert entry.dashboard is None
    assert "Unknown Workspace Asset" in (entry.message or "")


def test_native_region_map_requires_dashboard_asset_exposure_and_embeds_it(
    tmp_path: Path,
):
    root = _asset_workspace(tmp_path / "workspace")
    definition_path = root / "dashboards" / "asset-map" / "dashboard.yaml"
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    definition["views"] = [
        {
            "id": "map",
            "title": "Map",
            "template": "map",
            "mark": "region",
            "input": "source:sales/main",
            "geojson": "china-city",
            "data_key": "city",
            "feature_key": "properties.name",
            "color": "revenue",
            "label": "city",
        }
    ]
    definition["canvas"] = {}
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    workspace = load_workspace(root)
    diagnostics = validate_workspace(workspace)
    assert not [item for item in diagnostics if item.level == "error"]
    dashboard = workspace.dashboard("asset-map")
    result = Executor(workspace).run("asset-map")
    html = CanvasRenderer(workspace).render(dashboard, result)
    assert '"template": "map"' in html
    assert '"china-city": {"id": "china-city"' in html
    assert "Plotly" in html

    definition["assets"] = []
    definition_path.write_text(
        yaml.safe_dump(definition, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    invalid = load_workspace(root)
    errors = [item for item in validate_workspace(invalid) if item.level == "error"]
    assert any(item.code == "map_geojson_asset_not_exposed" for item in errors)
