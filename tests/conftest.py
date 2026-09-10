from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Callable

import pytest
import yaml


@pytest.fixture
def stable_analysis(tmp_path):
    """One small catalog, a server-only fact table and isolated durable labels."""
    from dataviz.action_examples import ACTION, RENDERER
    from dataviz.protocols import DASHBOARD_SCHEMA
    from dataviz.standalone import prepare_input

    database = tmp_path / "annotations.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("create table annotations (id text primary key, label text, revision integer not null)")
        db.executemany("insert into annotations values (?, NULL, 0)", [(f"{c}{n}",) for c in "AB" for n in range(1, 4)])
    auth = tmp_path / "connections.yaml"
    auth.write_text(yaml.safe_dump({"adapters": {"labels": {"type": "sqlalchemy", "url": f"sqlite:///{database}"}}}))
    source = tmp_path / "analysis.yaml"
    item_filter = {"selected": {"mode": "filter", "control": "dashboard.item", "field": "item", "inputs": ["main"], "empty": "match_none"}}
    definition = {
        "schema": DASHBOARD_SCHEMA, "id": "stability",
        "controls": [
            {"id": "category", "type": "single_select", "value_type": "text", "field": "category_nbr",
             "initial": {"mode": "value", "value": "A"}, "options": {"mode": "static", "choices":
                [{"value": c, "label": c} for c in ["A", "B", "EMPTY", "FAIL"]]}},
            {"id": "item", "type": "single_select", "value_type": "text", "field": "item", "clearable": True,
             "initial": {"mode": "first"}, "depends_on": ["dashboard.category"],
             "options": {"mode": "infer", "source": "source:catalog/main"}},
        ],
        "sources": [
            {"id": "facts", "type": "python", "code": {"inline": "def load(context):\n    return [{'category_nbr': 'AB'[i % 2], 'item': 'AB'[i % 2] + str(i % 3 + 1), 'qty': 1} for i in range(100001)]\n"}, "outputs": {"main": {"kind": "table"}}},
            {"id": "catalog", "type": "python", "code": {"inline": "def load(context):\n    return [{'category_nbr': c, 'item': c + str(n)} for c in 'AB' for n in range(1, 4)]\n"}, "outputs": {"main": {"kind": "table"}}},
            {"id": "annotations", "type": "sql", "adapter": "labels", "code": {"inline": "select id, id as item, label, revision from annotations order by id"}, "outputs": {"main": {"kind": "table"}}},
        ],
        "interactive_transforms": [{"id": "slice", "runtime": "server-python", "trigger": "auto", "debounce_ms": 0,
            "inputs": {"rows": "source:facts/main"}, "control_inputs": {"category": {"mode": "value", "control": "dashboard.category"}},
            "code": {"inline": "def transform(context):\n    category = context.control_inputs['category']\n    if category == 'FAIL':\n        raise ValueError('fixture slice failure')\n    rows = context.table('rows')\n    return {'main': rows[rows.category_nbr == category].groupby('item', as_index=False).qty.sum()}\n"},
            "outputs": {"main": {"kind": "table"}}, "export": {"mode": "snapshot"}}],
        "server_actions": [{"id": "save_label", "resources": {"store": "labels"}, "code": {"inline": ACTION}, "invalidates": ["source:annotations"]}],
        "canvas": {"scripts": [{"inline": RENDERER}]},
        "views": [
            {"id": "items", "template": "table", "input": "interactive:slice/main", "control_binding": {"control": "dashboard.item", "field": "item"}},
            {"id": "detail", "template": "bar", "input": "interactive:slice/main", "x": "item", "y": "qty", "control_inputs": item_filter},
            {"id": "editor", "template": "custom", "renderer": "annotation.editor", "input": "source:annotations/main", "control_inputs": item_filter},
        ],
    }
    source.write_text(yaml.safe_dump(definition))
    root, _ = prepare_input(source, auth=auth)
    return root, database


@pytest.fixture(scope="module")
def isolated_workspace(tmp_path_factory) -> Callable[[Path], Path]:
    """Copy repository workspaces before a test can create Runtime state in them."""
    root = tmp_path_factory.mktemp("workspace-fixtures")
    copies: dict[Path, Path] = {}

    def copy(source: Path) -> Path:
        resolved = source.resolve()
        if resolved not in copies:
            destination = root / f"{len(copies):02d}-{resolved.name}"
            shutil.copytree(
                resolved,
                destination,
                ignore=shutil.ignore_patterns(
                    ".dataviz",
                    "dist",
                    "__pycache__",
                    "*.pyc",
                    ".DS_Store",
                ),
            )
            copies[resolved] = destination
        return copies[resolved]

    return copy
