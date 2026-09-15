"""Lower one authoring document to an ordinary, isolated Workspace snapshot.

This is an input adapter, not an execution engine. Only declared local files are
copied; credentials remain in the explicitly selected external environment.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from dataviz.errors import WorkspaceError
from dataviz.filesystem import atomic_write_bytes, atomic_write_text
from dataviz.protocols import WORKSPACE_SCHEMA
from dataviz.workspace.loading.parse_load import read_yaml


def prepare_input(path: Path, *, auth: Path | None = None,
                  data: list[str] | None = None, _dependencies: set[Path] | None = None) -> tuple[Path, str | None]:
    path = path.expanduser().resolve()
    if path.is_dir() and ((path / "workspace.yaml").is_file() or not (path / "dashboard.yaml").is_file()):
        if auth is not None or data:
            raise WorkspaceError("--auth/--data are only supported for a standalone Dashboard")
        return path, None
    source = path / "dashboard.yaml" if path.is_dir() else path
    document = read_yaml(source)
    files: dict[str, bytes] = {}
    base = source.parent
    dependencies = _dependencies if _dependencies is not None else set()
    dependencies.update((source, base / "presentation.yaml"))
    from dataviz.local_data import parse_data_bindings, local_data_kind, snapshot_local_data
    bindings = parse_data_bindings(data)
    used_bindings: set[str] = set()
    data_adapters: dict[str, str] = {}
    environment = auth.expanduser().resolve() if auth is not None else None
    if environment is not None and not environment.exists():
        raise WorkspaceError("Explicit Adapter environment does not exist", file=environment)
    private_root = None
    if environment is not None and environment.is_dir():
        private_root = environment / "auth" if (environment / "workspace.yaml").is_file() else environment
    elif environment is not None and environment.name == "workspace.yaml":
        private_root = environment.parent / "auth"

    def local(value: str, owner: Path) -> str:
        if not isinstance(value, str):
            raise WorkspaceError("Standalone dependency must be a file path", file=source)
        selected = (owner / value).resolve()
        if selected.is_relative_to(base):
            dependencies.add(selected)
        if not selected.is_relative_to(base) or not selected.is_file():
            raise WorkspaceError("Standalone dependency must be a local file", file=source,
                                 details={"reference": value})
        if selected == environment or (private_root is not None and selected.is_relative_to(private_root)):
            raise WorkspaceError("Adapter configuration cannot be a Dashboard dependency", file=source)
        relative = selected.relative_to(base).as_posix()
        if any(part.startswith(".") for part in Path(relative).parts) or relative.startswith("auth/"):
            raise WorkspaceError("Private files cannot be standalone dependencies", file=source)
        content = selected.read_bytes()
        if relative in files and files[relative] != content:
            raise WorkspaceError("Standalone dependency path collision", file=source)
        files[relative] = content
        return relative

    def code(value: object, owner: Path, suffix: str) -> str:
        if isinstance(value, str):
            return local(value, owner)
        if not isinstance(value, dict) or set(value) != {"inline"} or not isinstance(value["inline"], str):
            raise WorkspaceError("Code must be a file path or {inline: <text>}", file=source)
        content = value["inline"].encode("utf-8")
        # Keep imports relative to the declaring file, as for external code.
        relative = (owner.relative_to(base) / f"inline_{hashlib.sha256(content).hexdigest()}.{suffix}").as_posix()
        if relative in files and files[relative] != content:
            raise WorkspaceError("Inline dependency path collision", file=source)
        files[relative] = content
        return relative

    for collection in (
        "sources", "dataset_transforms", "interactive_transforms", "parameter_domains", "server_actions"
    ):
        entries = []
        declared = document.get(collection, [])
        if not isinstance(declared, list):
            raise WorkspaceError(f"{collection} must be a list", file=source)
        for entry in declared:
            owner = base
            if isinstance(entry, str):
                relative = local(entry, base)
                owner = (base / relative).parent
                entry = read_yaml(base / relative)
                files.pop(relative)
            if not isinstance(entry, dict):
                raise WorkspaceError(f"Invalid {collection} entry", file=source)
            entry = dict(entry)
            bound_path = None
            if "data" in entry:
                alias = entry.pop("data")
                if collection != "sources" or not isinstance(alias, str) or alias not in bindings:
                    raise WorkspaceError("Source data requires a matching --data name=path", file=source)
                if "path" in entry or "adapter" in entry:
                    raise WorkspaceError("Source data cannot be combined with path or adapter", file=source)
                selected = bindings[alias]
                dependencies.update((selected, Path(str(selected) + "-wal")))
                kind = local_data_kind(selected)
                expected = "file" if kind == "csv" else "sql"
                if entry.get("type") != expected:
                    raise WorkspaceError(f"Input {alias} requires Source type {expected}", file=source)
                used_bindings.add(alias)
                bound_path = f"bound_data/{alias}.{'csv' if kind == 'csv' else 'sqlite'}"
                if bound_path not in files:
                    files[bound_path] = snapshot_local_data(selected)
                if kind == "csv":
                    entry["path"] = bound_path
                else:
                    adapter_name = f"local_data_{alias}"
                    entry["adapter"] = adapter_name
                    data_adapters[adapter_name] = bound_path
            if "code" in entry:
                suffix = "sql" if collection == "parameter_domains" or entry.get("type") == "sql" else (
                    "js" if entry.get("runtime") == "browser-js" else "py"
                )
                entry["code"] = code(entry["code"], owner, suffix)
            if bound_path is None and "path" in entry and not entry.get("adapter") and not str(entry["path"]).startswith("asset:"):
                entry["path"] = local(entry["path"], owner)
            if "code_dependencies" in entry:
                if not isinstance(entry["code_dependencies"], list):
                    raise WorkspaceError(
                        f"{collection}[{len(entries)}].code_dependencies must be a list",
                        file=source,
                    )
                entry["code_dependencies"] = [local(value, owner) for value in entry["code_dependencies"]]
            entries.append(entry)
        document[collection] = entries

    if unused := set(bindings) - used_bindings:
        raise WorkspaceError("Unused --data bindings", details={"names": sorted(unused)})

    if not isinstance(document.get("canvas", {}), dict):
        raise WorkspaceError("canvas must be an object", file=source)
    canvas = dict(document.get("canvas", {}))
    for key, suffix in (("scripts", "js"), ("styles", "css")):
        if key in canvas:
            if not isinstance(canvas[key], list):
                raise WorkspaceError(f"canvas.{key} must be a list", file=source)
            canvas[key] = [code(value, base, suffix) for value in canvas[key]]
    if canvas.get("template"):
        canvas["template"] = local(canvas["template"], base)
    document["canvas"] = canvas
    # An adjacent Presentation remains optional, just as in a folder Dashboard.
    presentation_path = base / "presentation.yaml"
    if presentation_path.is_file():
        presentation = read_yaml(presentation_path)
        assets = presentation.get("assets", {})
        if not isinstance(assets, dict):
            raise WorkspaceError("assets must be an object", file=presentation_path)
        for key, paths in assets.items():
            if not isinstance(paths, list):
                raise WorkspaceError(f"assets.{key} must be a list", file=presentation_path)
            for value in paths:
                local(value, base)
        presentation_canvas = presentation.get("canvas", {})
        if not isinstance(presentation_canvas, dict):
            raise WorkspaceError("canvas must be an object", file=presentation_path)
        template = presentation_canvas.get("template")
        if template:
            local(template, base)
        local("presentation.yaml", base)
    files["dashboard.yaml"] = yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode()

    # Identity includes the source location and explicit environment, never secrets.
    identity_parts = [str(source), str(environment)]
    if bindings:
        identity_parts.append({k: str(v) for k, v in bindings.items()})
    identity = json.dumps(identity_parts, sort_keys=True)
    digest = hashlib.sha256(identity.encode())
    for name, content in sorted(files.items()):
        digest.update(name.encode())
        digest.update(content)
    from dataviz.state_paths import standalone_state_home
    state_home = standalone_state_home()
    state_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = state_home / "standalone" / digest.hexdigest()
    source_identity = hashlib.sha256(str(source).encode()).hexdigest()
    legacy_journal = base / ".dataviz" / "actions" / source_identity / "receipts.sqlite"
    journal = legacy_journal if legacy_journal.exists() else state_home / "actions" / source_identity / "receipts.sqlite"
    for name, content in files.items():
        destination = root / "dashboards" / "main" / name
        if not destination.exists() or destination.read_bytes() != content:
            atomic_write_bytes(destination, content)
    atomic_write_text(root / "workspace.yaml", yaml.safe_dump({
        "schema": WORKSPACE_SCHEMA, "id": "standalone", "title": document.get("title", "Dashboard"),
    }))
    atomic_write_text(root / ".dataviz" / "standalone.json", json.dumps({
        "source": str(source), "auth": str(environment) if environment else None,
        "data_adapters": data_adapters,
        "action_journal": str(journal),
        "dependencies": sorted(str(item) for item in dependencies),
    }))
    return root, document.get("id")
