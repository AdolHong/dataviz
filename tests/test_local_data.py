import json
import sqlite3
import yaml

import pytest
from typer.testing import CliRunner

from dataviz.cli import app
from dataviz.errors import WorkspaceError
from dataviz.local_data import MAX_SAMPLE_BYTES, inspect_local_data
from dataviz.local_data import enforce_sqlite_read_only
from dataviz.standalone import prepare_input
from dataviz.protocols import DASHBOARD_SCHEMA


def local_dashboard(tmp_path, kind):
    source = {"id": "sales", "type": "file" if kind == "csv" else "sql", "data": "sales",
              "outputs": {"main": {"kind": "table"}}}
    if kind == "sqlite":
        source["code"] = {"inline": "SELECT * FROM sales"}
    path = tmp_path / "dashboard.yaml"
    path.write_text(yaml.safe_dump({"schema": DASHBOARD_SCHEMA, "id": "local",
        "sources": [source], "views": [{"id": "table", "template": "table", "input": "source:sales/main"}]}))
    return path


@pytest.mark.parametrize("kind", ["csv", "sqlite"])
def test_named_input_runs_and_preserves_old_snapshot(tmp_path, kind):
    path = local_dashboard(tmp_path, kind)
    source = tmp_path / f"sales.{kind}"
    if kind == "csv":
        source.write_text("amount\n10\n")
    else:
        with sqlite3.connect(source) as db:
            db.execute("CREATE TABLE sales (amount INTEGER)")
            db.execute("INSERT INTO sales VALUES (10)")
    args = ["--data", f"sales={source}"]
    root, _ = prepare_input(path, data=[f"sales={source}"])
    run = CliRunner().invoke(app, ["run", str(path), *args, "--format", "json"])
    assert run.exit_code == 0, run.output
    payload = json.loads(run.stdout)
    assert payload["status"] == "ready"
    if kind == "csv":
        source.write_text("amount\n20\n")
    else:
        with sqlite3.connect(source) as db:
            db.execute("UPDATE sales SET amount=20")
    new_root, _ = prepare_input(path, data=[f"sales={source}"])
    assert new_root != root
    output = tmp_path / "old.html"
    export = CliRunner().invoke(app, ["report", str(root), payload["result_id"], "--output", str(output)])
    assert export.exit_code == 0, export.output
    assert json.loads(export.stdout)["reexecuted"] is False
    assert output.is_file()


def test_binding_errors_are_explicit(tmp_path):
    path = local_dashboard(tmp_path, "csv")
    csv = tmp_path / "sales.csv"
    csv.write_text("a\n1\n")
    for values in ([], [f"wrong={csv}"], [f"sales={csv}", f"sales={csv}"],
                   [f"sales={csv}", f"unused={csv}"], [str(csv)]):
        with pytest.raises(WorkspaceError):
            prepare_input(path, data=values)


@pytest.mark.parametrize("option", [["--query-param", "minimum=1"], ["--control", "dashboard.category=food"],
                                    ["--refresh"], ["--allow-partial"], ["--page", "other"]])
def test_report_sealed_result_rejects_ignored_execution_options(tmp_path, option):
    path = local_dashboard(tmp_path, "csv")
    output = tmp_path / "report.html"
    result = CliRunner().invoke(app, ["report", str(path), "result_example", "--output", str(output), *option])
    assert result.exit_code != 0
    assert "already owns" in result.output
    assert not output.exists()


@pytest.mark.parametrize("example", ["local-csv", "local-sqlite"])
def test_local_examples_run_and_export_html(tmp_path, example):
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for name in ("local-csv", "local-sqlite"):
        shutil.copytree(root / "examples" / name, tmp_path / name)
    subprocess.run([sys.executable, str(tmp_path / "local-sqlite/create_data.py"),
                    str(tmp_path / "sales.sqlite")], check=True)
    binding = f"sales={tmp_path}/local-csv/sales.csv" if example == "local-csv" else f"warehouse={tmp_path}/sales.sqlite"
    entry = tmp_path / example  # Folder standalone, with no Workspace declaration.
    runner = CliRunner()
    check = runner.invoke(app, ["validate", str(entry), "--data", binding, "--strict", "--format", "json"])
    assert check.exit_code == 0, check.output
    output = tmp_path / "report.html"
    report = runner.invoke(app, ["report", str(entry), "--data", binding, "--output", str(output)])
    assert report.exit_code == 0, report.output
    assert output.stat().st_size > 1000
    assert "dataviz" in output.read_text().lower()


def test_local_sqlite_authorizer_rejects_writes_and_attach(tmp_path):
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE sales (amount INTEGER)")
        db.execute("INSERT INTO sales VALUES (10)")
        enforce_sqlite_read_only(db)
        assert db.execute("SELECT sum(amount) FROM sales").fetchone() == (10,)
        for sql in ("DELETE FROM sales RETURNING amount", "PRAGMA query_only=OFF",
                    f"ATTACH '{tmp_path / 'other.sqlite'}' AS other", "DROP TABLE sales"):
            with pytest.raises(sqlite3.DatabaseError):
                db.execute(sql)
    assert not (tmp_path / "other.sqlite").exists()


def test_standalone_keeps_source_directory_clean_and_receipts_stable(tmp_path, monkeypatch):
    import hashlib
    from dataviz.execution.action_journal import action_journal_path
    source_dir = tmp_path / "project"
    source_dir.mkdir()
    path = local_dashboard(source_dir, "csv")
    csv = source_dir / "sales.csv"
    csv.write_text("amount\n1\n")
    before = sorted(p.name for p in source_dir.iterdir())
    state = tmp_path / "managed"
    monkeypatch.setenv("DATAVIZ_STATE_DIR", str(state))
    root, _ = prepare_input(path, data=[f"sales={csv}"])
    assert root.is_relative_to(state)
    assert action_journal_path(root).is_relative_to(state)
    csv.write_text("amount\n2\n")
    new_root, _ = prepare_input(path, data=[f"sales={csv}"])
    assert new_root != root
    assert action_journal_path(root) == action_journal_path(new_root)
    assert sorted(p.name for p in source_dir.iterdir()) == before
    # Old active journals remain in place; never fork mutation receipts.
    identity = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    legacy = source_dir / ".dataviz" / "actions" / identity / "receipts.sqlite"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"existing-receipt")
    latest, _ = prepare_input(path, data=[f"sales={csv}"])
    assert action_journal_path(latest) == legacy
    assert legacy.read_bytes() == b"existing-receipt"


def test_csv_inspection_is_sample_only_and_preserves_identifiers(tmp_path):
    source = tmp_path / "sales.csv"
    source.write_text('\ufeffitem,qty,label\n001,2,"hello, world"\n002,3,last\n', encoding="utf-8")
    before = source.read_bytes()
    result = inspect_local_data(source, rows=1)
    assert result["rows"] == [["001", "2", "hello, world"]]
    assert result["columns"][0]["sample_type"] == "text"
    assert result["columns"][1]["sample_type"] == "integer"
    assert result["total_rows"] is None
    assert source.read_bytes() == before
    assert inspect_local_data(source, rows=0)["rows"] == []


def test_csv_limits_input_output_and_invalid_headers(tmp_path):
    source = tmp_path / "large.csv"
    source.write_text("name\n" + ("a" * 300 + "\n") * 2000)
    result = inspect_local_data(source, rows=2)
    assert result["input_truncated"]
    assert result["cells_truncated"]
    assert len(result["rows"]) == 2
    assert len(result["rows"][0][0]) == 256
    assert result["limits"]["sample_bytes"] == MAX_SAMPLE_BYTES
    source.write_text("x,x\n1,2\n")
    with pytest.raises(WorkspaceError):
        inspect_local_data(source)


def test_sqlite_inspection_lists_then_samples_without_writes(tmp_path):
    source = tmp_path / "sales ? #.sqlite"
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE "sales odd" (item TEXT, qty INTEGER, payload BLOB)')
        db.execute('INSERT INTO "sales odd" VALUES (?, ?, ?)', ('001', 2, b'private'))
        db.execute('CREATE VIEW detail AS SELECT * FROM "sales odd"')
    before = source.read_bytes()
    overview = inspect_local_data(source)
    assert overview["tables"] == [{"name": "detail", "type": "view"}, {"name": "sales odd", "type": "table"}]
    assert "rows" not in overview
    result = inspect_local_data(source, table="sales odd")
    assert result["columns"][1] == {"name": "qty", "declared_type": "INTEGER"}
    assert result["rows"] == [["001", 2, {"type": "blob", "bytes": 7}]]
    assert inspect_local_data(source, table="sales odd", rows=0)["rows"] == []
    assert source.read_bytes() == before
    for table in ('detail', 'missing', 'sales odd"; DROP TABLE "sales odd'):
        with pytest.raises(WorkspaceError):
            inspect_local_data(source, table=table)


def test_sqlite_large_cell_fails_with_budget_not_unbounded_output(tmp_path):
    source = tmp_path / "sales.db"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE sales (payload BLOB)")
        db.execute("INSERT INTO sales VALUES (zeroblob(?))", (MAX_SAMPLE_BYTES * 2,))
    with pytest.raises(WorkspaceError, match="limits"):
        inspect_local_data(source, table="sales")


def test_sqlite_binding_captures_committed_wal_and_rejects_write_query(tmp_path):
    path = local_dashboard(tmp_path, "sqlite")
    source = tmp_path / "active.sqlite"
    with sqlite3.connect(source) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE sales (amount INTEGER)")
        writer.execute("INSERT INTO sales VALUES (17)")
        writer.commit()
        root, _ = prepare_input(path, data=[f"sales={source}"])
        snapshot = root / "dashboards/main/bound_data/sales.sqlite"
        with sqlite3.connect(snapshot) as copy:
            assert copy.execute("SELECT amount FROM sales").fetchone() == (17,)
    payload = yaml.safe_load(path.read_text())
    payload["sources"][0]["code"]["inline"] = "DELETE FROM sales RETURNING amount"
    path.write_text(yaml.safe_dump(payload))
    result = CliRunner().invoke(app, ["run", str(path), "--data", f"sales={source}", "--format", "json"])
    assert result.exit_code != 0, result.output
    new_root, _ = prepare_input(path, data=[f"sales={source}"])
    with sqlite3.connect(new_root / "dashboards/main/bound_data/sales.sqlite") as copy:
        assert copy.execute("SELECT amount FROM sales").fetchone() == (17,)


def test_local_data_topic_and_search_are_available():
    runner = CliRunner()
    result = runner.invoke(app, ["docs", "local-data", "--format", "json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["csv_source"]["data"] == "sales"
    assert document["sqlite_source"]["type"] == "sql"
    search = runner.invoke(app, ["docs", "--search", "CSV SQLite", "--format", "json"])
    assert search.exit_code == 0, search.output
    assert "local-data" in search.output


def test_inspect_cli_validates_and_does_not_create_missing_database(tmp_path):
    runner = CliRunner()
    missing = tmp_path / "missing.sqlite"
    assert runner.invoke(app, ["inspect", "data", str(missing)]).exit_code != 0
    assert not missing.exists()
    source = tmp_path / "sales.csv"
    source.write_text("name\na\nb\n")
    result = runner.invoke(app, ["inspect", "data", str(source), "--rows", "1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["rows"] == [["a"]]
    assert runner.invoke(app, ["inspect", "data", str(source), "--rows", "21"]).exit_code != 0
    assert runner.invoke(app, ["inspect", "data", str(source), "--table", "sales"]).exit_code != 0
    fake = tmp_path / "fake.sqlite"
    fake.write_text("not a database")
    assert runner.invoke(app, ["inspect", "data", str(fake)]).exit_code != 0
