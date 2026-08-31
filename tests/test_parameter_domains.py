from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from typer.testing import CliRunner

from dataviz.artifacts import ArtifactStore
from dataviz.cli import app
from dataviz.errors import ExecutionFailure, ValidationFailure
from dataviz.execution import Executor
import dataviz.execution.parameter_domains as parameter_domains
from dataviz.execution.parameter_domains import (
    ParameterDomainCache,
    resolve_parameter_domains,
)
from dataviz.server import create_app
from dataviz.workspace import load_workspace, validate_workspace


def _workspace(root: Path) -> Path:
    dashboard = root / "dashboards" / "domain-lab"
    domains = dashboard / "parameter_domains"
    sources = dashboard / "sources"
    domains.mkdir(parents=True)
    sources.mkdir()
    (root / "auth").mkdir()
    (root / "workspace.yaml").write_text(
        "schema: dataviz/workspace/v1\nkind: workspace\nid: domain-tests\ntitle: Domain tests\n",
        encoding="utf-8",
    )
    (root / "auth" / "adapters.yaml").write_text(
        "adapters:\n  demo:\n    type: duckdb\n    database: ':memory:'\n",
        encoding="utf-8",
    )
    (dashboard / "dashboard.yaml").write_text(
        """schema: dataviz/dashboard/v13
kind: dashboard
id: domain-lab
title: Domain lab
adapters: {warehouse: demo}
parameter_domains: [parameter_domains/locations.yaml]
query_parameters:
  - id: province
    type: multiple_select
    value_type: text
    required: true
    initial: {mode: values, values: [GD]}
    options: {mode: domain, source: locations, value_field: province_code, label_field: province_name}
  - id: city
    type: multiple_select
    value_type: text
    initial: {mode: all}
    options:
      mode: domain
      source: locations
      value_field: city_code
      label_field: city_name
      depends_on: {province: {field: province_code}}
sources: [sources/metrics.yaml]
views:
  - {id: rows, title: Rows, template: table, input: source:metrics/main}
sections:
  - {id: main, title: Main, views: [rows]}
""",
        encoding="utf-8",
    )
    (domains / "locations.yaml").write_text(
        """schema: dataviz/parameter-domain/v1
kind: parameter_domain
id: locations
type: sql
adapter: warehouse
code: locations.sql
cache: {mode: session}
""",
        encoding="utf-8",
    )
    (domains / "locations.sql").write_text(
        """select * from (values
('GD', '广东', 'SZ', '深圳'),
('GD', '广东', 'GZ', '广州'),
('HN', '湖南', 'CS', '长沙')
) as locations(province_code, province_name, city_code, city_name)
""",
        encoding="utf-8",
    )
    (sources / "metrics.yaml").write_text(
        """schema: dataviz/source/v3
kind: source
id: metrics
type: sql
adapter: warehouse
code: metrics.sql
query_inputs:
  province: province
  city: city
  province_intent: {parameter: province, projection: intent}
  city_intent: {parameter: city, projection: intent}
outputs: {main: {kind: table}}
cache: {mode: none}
""",
        encoding="utf-8",
    )
    (sources / "metrics.sql").write_text(
        """select province_code, city_code, value,
  :province_intent as province_intent,
  :city_intent as city_intent
from (values
('GD', 'SZ', 10), ('GD', 'GZ', 8), ('HN', 'CS', 7)
) as metrics(province_code, city_code, value)
where list_contains(:province, province_code) and list_contains(:city, city_code)
""",
        encoding="utf-8",
    )
    return root


def test_shared_domain_projects_cascading_choices_and_reconciles_values(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")
    assert validate_workspace(workspace) == []
    contract = dashboard.parameter_domain_contract.as_dict()
    assert contract["schema"] == "dataviz/parameter-domain-contract/v2"
    assert contract["order"] == ["province", "city"]
    assert contract["projection_dependencies"] == {
        "province": [],
        "city": ["province"],
    }
    assert contract["projection_descendants"] == {
        "province": ["city"],
        "city": [],
    }
    assert contract["query_domains"] == {"province": [], "city": []}

    initial = resolve_parameter_domains(
        workspace,
        dashboard,
        {},
        timezone_name="UTC",
        initialized_parameters=set(),
        strict=False,
        cache=ParameterDomainCache(),
    )
    assert initial.values == {"province": ["GD"], "city": ["SZ", "GZ"]}
    assert [item["label"] for item in initial.choices["province"]] == ["广东", "湖南"]
    assert [item["value"] for item in initial.choices["city"]] == ["SZ", "GZ"]
    assert list(initial.domains) == ["locations"]
    payload = initial.as_dict()
    assert payload["schema"] == "dataviz/parameter-domain-resolution/v2"
    client_projection = payload["client_projection"]
    assert client_projection["contract_hash"] == contract["contract_hash"]
    assert list(client_projection["parameters"]) == ["city"]
    assert client_projection["capacity"]["rows"] == 3
    assert client_projection["capacity"]["max_rows"] == 50_000
    assert client_projection["capacity"]["max_serialized_bytes"] == 8 * 1024 * 1024
    assert client_projection["parameters"]["city"]["rows"][0] == {
        "signature": '"SZ"',
        "choice": {"value": "SZ", "label": "深圳"},
        "parents": {"province": '"GD"'},
    }
    serialized_projection = json.dumps(client_projection, ensure_ascii=False)
    assert "province_name" not in serialized_projection
    assert "locations.sql" not in serialized_projection

    cascaded = resolve_parameter_domains(
        workspace,
        dashboard,
        {"province": ["HN"], "city": ["SZ"]},
        timezone_name="UTC",
        initialized_parameters={"province", "city"},
        intents={"province": "explicit", "city": "explicit"},
        strict=False,
        cache=ParameterDomainCache(),
    )
    assert cascaded.values == {"province": ["HN"], "city": ["CS"]}
    assert [item["value"] for item in cascaded.choices["city"]] == ["CS"]


def test_contract_separates_query_edges_from_local_projection_edges(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    dashboard_path = root / "dashboards/domain-lab/dashboard.yaml"
    dashboard_yaml = dashboard_path.read_text(encoding="utf-8")
    dashboard_path.write_text(
        dashboard_yaml.replace(
            "query_parameters:\n",
            "query_parameters:\n"
            "  - id: search\n"
            "    type: single_input\n"
            "    value_type: text\n"
            "    default: ''\n",
            1,
        ),
        encoding="utf-8",
    )
    domain_path = root / "dashboards/domain-lab/parameter_domains/locations.yaml"
    domain_yaml = domain_path.read_text(encoding="utf-8")
    domain_path.write_text(
        domain_yaml.replace(
            "code: locations.sql\n",
            "code: locations.sql\nquery_inputs:\n  search_term: search\n",
            1,
        ),
        encoding="utf-8",
    )

    dashboard = load_workspace(root).dashboard("domain-lab")
    contract = dashboard.parameter_domain_contract.as_dict()

    assert contract["projection_descendants"]["province"] == ["city"]
    assert contract["query_domains"]["search"] == ["locations"]
    assert contract["domain_input_bindings"] == {
        "locations": {"search_term": {"parameter": "search"}}
    }
    assert contract["dependencies"]["city"] == ["province", "search"]


def test_contract_rejects_same_parent_domain_projection_and_query_edge(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    domain_path = root / "dashboards/domain-lab/parameter_domains/locations.yaml"
    domain_yaml = domain_path.read_text(encoding="utf-8")
    domain_path.write_text(
        domain_yaml.replace(
            "code: locations.sql\n",
            "code: locations.sql\nquery_inputs:\n  province_filter: province\n",
            1,
        ),
        encoding="utf-8",
    )

    dashboard = load_workspace(root).dashboard("domain-lab")
    with pytest.raises(ValidationFailure) as raised:
        _ = dashboard.parameter_domain_contract

    assert raised.value.details == {
        "code": "parameter_domain_dependency_mode_conflict",
        "domain": "locations",
        "parameter": "city",
        "parents": ["province"],
    }


@pytest.mark.parametrize(
    "limit_name",
    [
        "PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_ROWS",
        "PARAMETER_DOMAIN_CLIENT_PROJECTION_MAX_BYTES",
    ],
)
def test_client_projection_capacity_fails_without_truncation_or_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    monkeypatch.setattr(parameter_domains, limit_name, 1)

    with pytest.raises(ExecutionFailure) as raised:
        resolve_parameter_domains(
            workspace,
            workspace.dashboard("domain-lab"),
            {},
            timezone_name="UTC",
            initialized_parameters=set(),
            strict=False,
        )

    details = raised.value.details
    assert details["code"] == "parameter_domain_client_projection_limit"
    assert details["rows"] == 3
    assert details["serialized_bytes"] > 1
    assert details["domains"] == ["locations"]
    assert details["consumers"] == ["city"]
    assert "query_inputs" in details["suggestions"][0]


def test_explicit_empty_selection_survives_domain_refresh(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")

    resolution = resolve_parameter_domains(
        workspace,
        dashboard,
        {"province": ["GD"], "city": []},
        timezone_name="UTC",
        initialized_parameters={"province", "city"},
        intents={"province": "explicit", "city": "explicit"},
        strict=False,
    )

    assert resolution.values["city"] == []
    assert resolution.intents["city"] == "explicit"


def test_committed_snapshot_rehydration_preserves_unavailable_cascade_values(
    tmp_path: Path,
):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")
    domain_sql = root / "dashboards/domain-lab/parameter_domains/locations.sql"
    domain_sql.write_text(
        """select * from (values
('HN', '湖南', 'CS', '长沙')
) as locations(province_code, province_name, city_code, city_name)
""",
        encoding="utf-8",
    )

    restored = resolve_parameter_domains(
        workspace,
        dashboard,
        {"province": ["GD"], "city": ["SZ"]},
        timezone_name="UTC",
        initialized_parameters={"province", "city"},
        intents={"province": "explicit", "city": "all_available"},
        strict=False,
        preserve_unavailable=True,
    )

    assert restored.values == {"province": ["GD"], "city": ["SZ"]}
    assert restored.intents == {
        "province": "explicit",
        "city": "all_available",
    }
    assert restored.choices["province"][-1] == {
        "value": "GD",
        "label": "GD",
        "description": "Unavailable in the current Parameter Domain",
        "disabled": True,
        "unavailable": True,
    }
    assert restored.choices["city"] == [
        {
            "value": "SZ",
            "label": "SZ",
            "description": "Unavailable in the current Parameter Domain",
            "disabled": True,
            "unavailable": True,
        }
    ]


@pytest.mark.parametrize(
    ("category_type", "selected", "empty"),
    [
        ("single_select", "food", None),
        ("multiple_select", ["food"], []),
    ],
)
def test_static_single_or_multiple_parent_filters_two_fields_from_one_domain(
    tmp_path: Path,
    category_type: str,
    selected: object,
    empty: object,
):
    root = _workspace(tmp_path / "workspace")
    dashboard_path = root / "dashboards/domain-lab/dashboard.yaml"
    dashboard_path.write_text(
        f"""schema: dataviz/dashboard/v13
kind: dashboard
id: domain-lab
title: Shared item candidates
adapters: {{warehouse: demo}}
parameter_domains: [parameter_domains/locations.yaml]
query_parameters:
  - id: category
    type: {category_type}
    value_type: text
    required: false
    initial: {{mode: empty}}
    options:
      mode: static
      choices:
        - {{value: food, label: 食品}}
        - {{value: beauty, label: 美妆}}
  - id: subcategory
    type: multiple_select
    value_type: text
    required: false
    initial: {{mode: all}}
    options:
      mode: domain
      source: locations
      value_field: subcategory
      depends_on: {{category: {{field: category}}}}
  - id: item_nbr
    type: multiple_select
    value_type: text
    required: false
    initial: {{mode: all}}
    options:
      mode: domain
      source: locations
      value_field: item_nbr
      label_field: item_name
      depends_on: {{category: {{field: category}}}}
sources: [sources/metrics.yaml]
views:
  - {{id: rows, title: Rows, template: table, input: source:metrics/main}}
sections:
  - {{id: main, title: Main, views: [rows]}}
""",
        encoding="utf-8",
    )
    domain_sql = root / "dashboards/domain-lab/parameter_domains/locations.sql"
    domain_sql.write_text(
        """select * from (values
('food', 'snack', 'F1', '饼干'),
('food', 'candy', 'F2', '糖果'),
('beauty', 'skin', 'B1', '面霜')
) as items(category, subcategory, item_nbr, item_name)
""",
        encoding="utf-8",
    )
    workspace = load_workspace(root)
    dashboard = workspace.dashboard("domain-lab")

    populated = resolve_parameter_domains(
        workspace,
        dashboard,
        {"category": selected},
        timezone_name="UTC",
        initialized_parameters={"category"},
        intents={"category": "explicit"},
        strict=False,
    )
    assert [choice["value"] for choice in populated.choices["subcategory"]] == [
        "snack",
        "candy",
    ]
    assert [choice["value"] for choice in populated.choices["item_nbr"]] == [
        "F1",
        "F2",
    ]
    assert list(populated.frames) == ["locations"]
    assert len(populated.frames["locations"]) == 3

    cleared = resolve_parameter_domains(
        workspace,
        dashboard,
        {"category": empty},
        timezone_name="UTC",
        initialized_parameters={"category"},
        intents={"category": "explicit"},
        strict=False,
    )
    assert cleared.choices["subcategory"] == []
    assert cleared.choices["item_nbr"] == []
    assert cleared.values["subcategory"] == []
    assert cleared.values["item_nbr"] == []


def test_executor_accepts_typed_values_without_executing_the_ui_domain(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    workspace = load_workspace(root)
    domain_sql = root / "dashboards" / "domain-lab" / "parameter_domains" / "locations.sql"
    domain_sql.write_text("this is deliberately not executable SQL", encoding="utf-8")

    result = Executor(workspace).run(
        "domain-lab",
        query_parameters={"province": ["GD"], "city": ["OUTSIDE_UI_DOMAIN"]},
        query_parameter_intents={
            "province": "all_available",
            "city": "explicit",
        },
    )

    assert result.status == "ready"
    assert result.query_parameters == {
        "province": ["GD"],
        "city": ["OUTSIDE_UI_DOMAIN"],
    }
    assert result.query_parameter_intents == {
        "province": "all_available",
        "city": "explicit",
    }
    frame = ArtifactStore(root, result.run_id).read_table(result.outputs["source:metrics/main"])
    assert list(frame.columns[-2:]) == ["province_intent", "city_intent"]
    assert result.nodes["source:metrics"].status == "empty"


def test_parameters_options_is_explicit_optional_candidate_discovery(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")

    result = CliRunner().invoke(
        app,
        [
            "parameters",
            "options",
            str(root),
            "domain-lab",
            "--query-param",
            'province=["HN"]',
            "--parameter",
            "city",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "dataviz/parameter-options/v1"
    assert payload["tables"][0]["domain"] == "locations"
    assert payload["tables"][0]["rows"] == 3
    assert len(payload["tables"][0]["preview"]) == 3
    options_id = payload["options_id"]
    assert "optional" in payload["note"].lower()
    assert "does not execute or enforce" in payload["note"]

    domain_sql = root / "dashboards/domain-lab/parameter_domains/locations.sql"
    domain_sql.write_text("this SQL must not be executed again", encoding="utf-8")
    filtered = CliRunner().invoke(
        app,
        [
            "parameters",
            "filter",
            str(root),
            options_id,
            "--domain",
            "locations",
            "--where",
            'province_code="HN"',
            "--column",
            "city_code",
            "--column",
            "city_name",
            "--format",
            "json",
        ],
    )

    assert filtered.exit_code == 0, filtered.output
    page = json.loads(filtered.output)
    assert page["rows"] == [{"city_code": "CS", "city_name": "长沙"}]


def test_server_resolver_uses_tab_cache_and_reload_bypasses_it(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    client = TestClient(create_app(root, watch=False))
    endpoint = "/api/dashboards/domain-lab/parameter-domains/resolve"
    request = {
        "session_id": "domain_test_session",
        "query_parameters": {},
        "initialized_parameters": [],
        "intents": {},
    }

    first = client.post(endpoint, json=request)
    second = client.post(endpoint, json=request)
    refreshed = client.post(endpoint, json={**request, "refresh": True})

    assert first.status_code == second.status_code == refreshed.status_code == 200
    assert first.json()["domains"]["locations"]["cached"] is False
    assert second.json()["domains"]["locations"]["cached"] is True
    assert refreshed.json()["domains"]["locations"]["cached"] is False
    assert first.json()["query_parameters"] == {
        "province": ["GD"],
        "city": ["SZ", "GZ"],
    }
    assert first.json()["contract"]["dependencies"] == {
        "province": [],
        "city": ["province"],
    }


def test_server_resolver_accepts_committed_snapshot_reconciliation(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    client = TestClient(create_app(root, watch=False))
    response = client.post(
        "/api/dashboards/domain-lab/parameter-domains/resolve",
        json={
            "session_id": "committed_domain_session",
            "query_parameters": {"province": ["outside"], "city": ["legacy"]},
            "initialized_parameters": ["province", "city"],
            "intents": {"province": "explicit", "city": "explicit"},
            "reconciliation": "committed_snapshot",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_parameters"] == {
        "province": ["outside"],
        "city": ["legacy"],
    }
    assert payload["choices"]["province"][-1]["unavailable"] is True
    assert payload["choices"]["city"][-1]["unavailable"] is True


def test_dashboard_shell_exposes_contract_but_not_domain_rows_or_sql(tmp_path: Path):
    root = _workspace(tmp_path / "workspace")
    client = TestClient(create_app(root, watch=False))

    payload = client.get("/api/workspace").json()
    dashboard = next(item for item in payload["dashboards"] if item["id"] == "domain-lab")
    serialized = str(dashboard)

    assert dashboard["parameter_domain_contract"]["dependencies"]["city"] == ["province"]
    assert "locations.sql" not in serialized
    assert "深圳" not in serialized
