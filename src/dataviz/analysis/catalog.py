from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Iterator

from dataviz.analysis.contracts import (
    ANALYSIS_CATALOG_SCHEMA,
    ANALYSIS_ENTRY_SCHEMA,
    validate_analysis_entry,
)
from dataviz.analysis.usage import output_analysis_usage, read_usage_best_effort
from dataviz.errors import ValidationFailure
from dataviz.filesystem import atomic_write_text
from dataviz.workspace.loader import LoadedDashboard, LoadedWorkspace, load_workspace


CATALOG_POINTER_SCHEMA = "dataviz/analysis-catalog-pointer/v1"
CATALOG_BUILDER_VERSION = 4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _asset_path(definition_path: Path, value: str) -> Path:
    return (definition_path.parent / value).resolve()


def _dashboard_definition_paths(dashboard: LoadedDashboard) -> tuple[Path, ...]:
    paths: set[Path] = {dashboard.definition_path.resolve()}
    if dashboard.presentation_path is not None:
        paths.add(dashboard.presentation_path.resolve())
    for definition_path, definition in [
        *dashboard.sources.values(),
        *dashboard.dataset_transforms.values(),
        *dashboard.interactive_transforms.values(),
    ]:
        definition_path = definition_path.resolve()
        paths.add(definition_path)
        code = getattr(definition, "code", None)
        if code:
            paths.add(_asset_path(definition_path, code))
        for dependency in getattr(definition, "code_dependencies", ()):
            paths.add(_asset_path(definition_path, dependency))
    return tuple(sorted(paths, key=lambda value: value.as_posix()))


def _dashboard_fingerprint(workspace: LoadedWorkspace, dashboard: LoadedDashboard) -> str:
    digest = hashlib.sha256()
    for path in _dashboard_definition_paths(dashboard):
        relative = _relative(workspace.root, path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_hash_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _workspace_fingerprint(workspace: LoadedWorkspace) -> str:
    digest = hashlib.sha256()
    digest.update(_relative(workspace.root, workspace.definition_path).encode("utf-8"))
    digest.update(b"\0")
    digest.update(_hash_file(workspace.definition_path).encode("ascii"))
    return digest.hexdigest()


def _fingerprints(workspace: LoadedWorkspace) -> tuple[str, dict[str, str]]:
    return (
        _workspace_fingerprint(workspace),
        {
            dashboard_id: _dashboard_fingerprint(workspace, dashboard)
            for dashboard_id, dashboard in sorted(workspace.dashboards.items())
        },
    )


def _logical_reference(dashboard_id: str, local_reference: str) -> str:
    return f"{dashboard_id}::{local_reference}"


def _alias_digest(reference: str) -> str:
    encoded = base64.b32encode(hashlib.sha256(reference.encode("utf-8")).digest())
    return encoded.decode("ascii").rstrip("=")


def _assign_aliases(entries: list[dict[str, Any]]) -> None:
    prefix = {
        "source": "src",
        "base_output": "base",
        "derived_output": "drv",
        "view": "view",
    }
    unresolved = list(entries)
    length = 10
    while unresolved:
        groups: dict[str, list[dict[str, Any]]] = {}
        for entry in unresolved:
            candidate = f"{prefix[entry['kind']]}_{_alias_digest(entry['reference'])[:length]}"
            groups.setdefault(candidate, []).append(entry)
        next_unresolved: list[dict[str, Any]] = []
        for candidate, members in groups.items():
            if len(members) == 1:
                members[0]["alias"] = candidate
            else:
                next_unresolved.extend(members)
        if not next_unresolved:
            return
        length += 2
        if length > 52:
            raise RuntimeError("Unable to generate unique Analysis aliases")
        unresolved = next_unresolved


def _parameter_names(bindings: dict[str, dict[str, Any]]) -> set[str]:
    return {
        str(binding["parameter"])
        for binding in bindings.values()
        if isinstance(binding, dict) and binding.get("parameter")
    }


def _query_node_context(dashboard: LoadedDashboard, node_id: str) -> dict[str, Any]:
    contract = dashboard.dependency_contract
    closure = contract.query_closure([node_id])
    parameters: set[str] = set()
    upstream_outputs: set[str] = set()
    source_types: set[str] = set()
    adapters: set[str] = set()
    for dependency in closure:
        parameters.update(_parameter_names(contract.parameter_inputs.get(dependency, {})))
        upstream_outputs.update(contract.data_inputs.get(dependency, {}).values())
        if dependency.startswith("source:"):
            source_id = dependency.split(":", 1)[1]
            definition = dashboard.sources[source_id][1]
            source_types.add(definition.type)
            adapter = getattr(definition, "adapter", None)
            if adapter:
                adapters.add(str(adapter))
    return {
        "query_nodes": sorted(closure),
        "query_parameters": sorted(parameters),
        "upstream_outputs": sorted(upstream_outputs),
        "source_types": sorted(source_types),
        "adapters": sorted(adapters),
    }


def _interactive_context(dashboard: LoadedDashboard, transform_id: str) -> dict[str, Any]:
    contract = dashboard.dependency_contract
    interactive_nodes = contract.interactive_closure(transform_id)
    query_nodes: set[str] = set()
    query_parameters: set[str] = set()
    base_inputs: set[str] = set()
    upstream_outputs: set[str] = set()
    controls: set[str] = set()
    source_types: set[str] = set()
    adapters: set[str] = set()
    for identifier in interactive_nodes:
        query_parameters.update(
            _parameter_names(contract.interactive_parameter_inputs.get(identifier, {}))
        )
        controls.update(contract.interactive_selection_inputs.get(identifier, {}).values())
        controls.update(contract.interactive_compute_inputs.get(identifier, {}).values())
        for reference in contract.interactive_inputs.get(identifier, {}).values():
            upstream_outputs.add(reference)
            node_id = reference.split("/", 1)[0]
            if node_id.startswith(("source:", "dataset:")):
                base_inputs.add(reference)
                context = _query_node_context(dashboard, node_id)
                query_nodes.update(context["query_nodes"])
                query_parameters.update(context["query_parameters"])
                source_types.update(context["source_types"])
                adapters.update(context["adapters"])
    return {
        "interactive_nodes": list(interactive_nodes),
        "query_nodes": sorted(query_nodes),
        "query_parameters": sorted(query_parameters),
        "base_inputs": sorted(base_inputs),
        "upstream_outputs": sorted(upstream_outputs),
        "controls": sorted(controls),
        "source_types": sorted(source_types),
        "adapters": sorted(adapters),
    }


def _definition_and_code_paths(
    workspace: LoadedWorkspace,
    definition_path: Path,
    definition: Any,
) -> tuple[str, list[str]]:
    code_paths: list[str] = []
    code = getattr(definition, "code", None)
    if code:
        code_paths.append(_relative(workspace.root, _asset_path(definition_path, code)))
    for dependency in getattr(definition, "code_dependencies", ()):
        code_paths.append(
            _relative(workspace.root, _asset_path(definition_path, dependency))
        )
    return _relative(workspace.root, definition_path), sorted(set(code_paths))


def _output_contract(definition: Any) -> dict[str, Any]:
    return definition.model_dump(mode="json", by_alias=True, exclude_none=True)


def _implementation_assets(
    workspace: LoadedWorkspace,
    definition_path: str,
    code_paths: list[str],
) -> list[dict[str, str]]:
    return [
        {"path": relative, "sha256": _hash_file(workspace.root / relative)}
        for relative in [definition_path, *code_paths]
    ]


def _equivalence_hash(entry: dict[str, Any]) -> str:
    """Conservative identity for exact Catalog overview folding.

    Including the complete definition asset intentionally prefers missed folds
    over claiming two merely similar SQL/Transform definitions are equivalent.
    """

    payload = {
        "implementation_asset_hashes": sorted(
            asset["sha256"] for asset in entry.get("implementation_assets", [])
        ),
        "source_type": entry.get("source_type"),
        "runtime": entry.get("runtime"),
        "adapters": sorted(entry.get("adapters", [])),
        "query_bindings": entry.get("query_bindings", {}),
        "output": entry.get("output", {}),
    }
    if entry.get("source_type") == "file":
        # Business file contents deliberately do not enter the Catalog
        # fingerprint. Without a fresh content hash, folding would be unsafe.
        payload["untracked_file_reference"] = entry["reference"]
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _output_semantics(
    dashboard: LoadedDashboard,
    definition: Any,
    *,
    fallback_title: str,
    fallback_purpose: str,
) -> dict[str, Any]:
    semantics = getattr(definition, "semantics", None)
    if semantics is not None:
        return {
            "visibility": semantics.visibility,
            "title": semantics.title.strip(),
            "purpose": semantics.purpose.strip(),
            "grain": semantics.grain.strip(),
            "caveats": list(semantics.caveats),
            "assurance": semantics.assurance.model_dump(mode="json"),
            "time": semantics.time.model_dump(mode="json") if semantics.time else None,
            "measures": {
                name: value.model_dump(mode="json")
                for name, value in semantics.measures.items()
            },
            "relationships": [
                value.model_dump(mode="json") for value in semantics.relationships
            ],
            "semantic_source": "declared",
        }
    # Compatibility for pre-0.10 Dashboards: execution remains unchanged and
    # the Catalog keeps the entry discoverable, but reports exactly which
    # semantics are inferred so authors can migrate deliberately.
    return {
        "visibility": "internal",
        "title": fallback_title.strip(),
        "purpose": fallback_purpose.strip(),
        "grain": str(dashboard.definition.context.get("grain") or "").strip(),
        "caveats": [],
        "assurance": {"status": "draft", "owner": "", "evidence": []},
        "time": None,
        "measures": {},
        "relationships": [],
        "semantic_source": "legacy-inferred",
    }


def _entry_base(
    workspace: LoadedWorkspace,
    dashboard_id: str,
    dashboard: LoadedDashboard,
    *,
    kind: str,
    local_reference: str,
    title: str,
    purpose: str,
) -> dict[str, Any]:
    return {
        "schema": ANALYSIS_ENTRY_SCHEMA,
        "alias": "",
        "reference": _logical_reference(dashboard_id, local_reference),
        "dashboard": {
            "id": dashboard_id,
            "title": dashboard.title,
            "path": _relative(workspace.root, dashboard.root),
        },
        "kind": kind,
        "title": title,
        "purpose": purpose,
        "grain": dashboard.definition.context.get("grain") or None,
        "caveats": [],
        "visibility": "public",
    }


def _dashboard_entries(
    workspace: LoadedWorkspace,
    dashboard_id: str,
    dashboard: LoadedDashboard,
    definition_hash: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    contract = dashboard.dependency_contract

    for source_id, (path, source) in sorted(dashboard.sources.items()):
        node_id = f"source:{source_id}"
        definition_path, code_paths = _definition_and_code_paths(workspace, path, source)
        context = _query_node_context(dashboard, node_id)
        source_entry = _entry_base(
            workspace,
            dashboard_id,
            dashboard,
            kind="source",
            local_reference=node_id,
            title=source.name or source_id,
            purpose=source.description,
        )
        source_entry.update(
            stage="base",
            node_id=node_id,
            source_type=source.type,
            runtime="server",
            query_parameters=context["query_parameters"],
            controls=[],
            outputs=[
                _logical_reference(dashboard_id, reference)
                for reference in contract.query_outputs[node_id]
            ],
            upstream_outputs=[],
            downstream_views=sorted(
                {
                    view
                    for reference in contract.query_outputs[node_id]
                    for view in contract.output_view_consumers.get(reference, ())
                }
            ),
            adapters=context["adapters"],
            definition_path=definition_path,
            code_paths=code_paths,
            definition_hash=definition_hash,
        )
        entries.append(source_entry)

    query_nodes: list[tuple[str, Path, Any]] = [
        *(
            (f"source:{identifier}", path, definition)
            for identifier, (path, definition) in dashboard.sources.items()
        ),
        *(
            (f"dataset:{identifier}", path, definition)
            for identifier, (path, definition) in dashboard.dataset_transforms.items()
        ),
    ]
    for node_id, path, definition in sorted(query_nodes, key=lambda item: item[0]):
        definition_path, code_paths = _definition_and_code_paths(
            workspace, path, definition
        )
        context = _query_node_context(dashboard, node_id)
        for output_name, output in sorted(definition.outputs.items()):
            local_reference = f"{node_id}/{output_name}"
            fallback_title = output.description or (
                f"{getattr(definition, 'name', None) or node_id} / {output_name}"
            )
            semantics = _output_semantics(
                dashboard,
                output,
                fallback_title=fallback_title,
                fallback_purpose=output.description or getattr(definition, "description", ""),
            )
            entry = _entry_base(
                workspace,
                dashboard_id,
                dashboard,
                kind="base_output",
                local_reference=local_reference,
                title=semantics["title"],
                purpose=semantics["purpose"],
            )
            entry.update(semantics)
            entry.update(
                stage="base",
                node_id=node_id,
                output_name=output_name,
                source_type=(definition.type if node_id.startswith("source:") else "dataset-transform"),
                runtime="server",
                query_parameters=context["query_parameters"],
                controls=[],
                upstream_outputs=[
                    _logical_reference(dashboard_id, reference)
                    for reference in context["upstream_outputs"]
                ],
                downstream_views=list(contract.output_view_consumers.get(local_reference, ())),
                source_types=context["source_types"],
                adapters=context["adapters"],
                query_bindings=contract.parameter_inputs.get(node_id, {}),
                output=_output_contract(output),
                definition_path=definition_path,
                code_paths=code_paths,
                implementation_assets=_implementation_assets(
                    workspace, definition_path, code_paths
                ),
                definition_hash=definition_hash,
            )
            entry["equivalence_hash"] = _equivalence_hash(entry)
            entries.append(entry)

    for transform_id, (path, transform) in sorted(dashboard.interactive_transforms.items()):
        definition_path, code_paths = _definition_and_code_paths(
            workspace, path, transform
        )
        context = _interactive_context(dashboard, transform_id)
        for output_name, output in sorted(transform.outputs.items()):
            local_reference = f"interactive:{transform_id}/{output_name}"
            fallback_title = output.description or f"{transform.name or transform_id} / {output_name}"
            semantics = _output_semantics(
                dashboard,
                output,
                fallback_title=fallback_title,
                fallback_purpose=output.description or transform.description,
            )
            entry = _entry_base(
                workspace,
                dashboard_id,
                dashboard,
                kind="derived_output",
                local_reference=local_reference,
                title=semantics["title"],
                purpose=semantics["purpose"],
            )
            entry.update(semantics)
            entry.update(
                stage="derived",
                node_id=f"interactive:{transform_id}",
                output_name=output_name,
                source_type="interactive-transform",
                runtime=transform.runtime,
                query_parameters=context["query_parameters"],
                controls=context["controls"],
                base_inputs=[
                    _logical_reference(dashboard_id, reference)
                    for reference in context["base_inputs"]
                ],
                upstream_outputs=[
                    _logical_reference(dashboard_id, reference)
                    for reference in context["upstream_outputs"]
                ],
                downstream_views=list(contract.output_view_consumers.get(local_reference, ())),
                source_types=context["source_types"],
                adapters=context["adapters"],
                query_bindings=contract.interactive_parameter_inputs.get(
                    transform_id, {}
                ),
                output=_output_contract(output),
                definition_path=definition_path,
                code_paths=code_paths,
                implementation_assets=_implementation_assets(
                    workspace, definition_path, code_paths
                ),
                definition_hash=definition_hash,
            )
            entry["equivalence_hash"] = _equivalence_hash(entry)
            entries.append(entry)

    for view_id, view in sorted(dashboard.views.items()):
        entry = _entry_base(
            workspace,
            dashboard_id,
            dashboard,
            kind="view",
            local_reference=f"view:{view_id}",
            title=view.title or view_id,
            purpose=view.description,
        )
        input_references = {
            name: _logical_reference(dashboard_id, reference)
            for name, reference in view.input_refs.items()
        }
        query_parameters: set[str] = set()
        controls = set(contract.view_controls.get(view_id, ()))
        runtimes: set[str] = set()
        for reference in view.input_refs.values():
            node_id = reference.split("/", 1)[0]
            if node_id.startswith(("source:", "dataset:")):
                query_parameters.update(
                    _query_node_context(dashboard, node_id)["query_parameters"]
                )
            elif node_id.startswith("interactive:"):
                transform_id = node_id.split(":", 1)[1]
                context = _interactive_context(dashboard, transform_id)
                query_parameters.update(context["query_parameters"])
                controls.update(context["controls"])
                runtimes.add(contract.interactive_runtimes[transform_id])
        entry.update(
            stage="presentation",
            view_id=view_id,
            runtime=sorted(runtimes) or ["renderer"],
            query_parameters=sorted(query_parameters),
            controls=sorted(controls),
            inputs=input_references,
            presentation={
                key: value
                for key, value in view.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ).items()
                if key not in {"controls"}
            },
            definition_path=_relative(workspace.root, dashboard.definition_path),
            code_paths=[],
            definition_hash=definition_hash,
        )
        entries.append(entry)

    for entry in entries:
        if entry["kind"] not in {"base_output", "derived_output"}:
            continue
        missing = [
            field
            for field in ("title", "purpose", "grain")
            if not str(entry.get(field) or "").strip()
        ]
        entry["semantic_status"] = "complete" if not missing else "incomplete"
        entry["semantic_missing"] = missing
        entry["trust_status"] = entry.get("assurance", {}).get("status", "draft")

    _assign_aliases(entries)
    entries = [validate_analysis_entry(entry) for entry in entries]
    return entries


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _read_pointer(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if value.get("schema") == CATALOG_POINTER_SCHEMA else None


def _pointer_is_fresh(
    pointer: dict[str, Any] | None,
    workspace_hash: str,
    dashboard_hashes: dict[str, str],
    generations: Path,
) -> bool:
    if not pointer:
        return False
    return (
        pointer.get("builder_version") == CATALOG_BUILDER_VERSION
        and pointer.get("workspace_hash") == workspace_hash
        and pointer.get("dashboard_hashes") == dashboard_hashes
        and isinstance(pointer.get("generation"), str)
        and (generations / pointer["generation"]).is_file()
    )


def _read_generation(path: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [
            json.loads(row[0])
            for row in connection.execute("SELECT payload FROM entries ORDER BY reference")
        ]
    finally:
        connection.close()


def _write_generation(path: Path, entries: list[dict[str, Any]], generation: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE entries (
                alias TEXT PRIMARY KEY,
                reference TEXT NOT NULL UNIQUE,
                dashboard_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                stage TEXT NOT NULL,
                source_type TEXT,
                parameters TEXT NOT NULL,
                search_text TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX entries_dashboard ON entries(dashboard_id);
            CREATE INDEX entries_kind ON entries(kind);
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        for entry in entries:
            search_text = " ".join(
                str(value)
                for value in (
                    entry.get("alias"),
                    entry.get("reference"),
                    entry.get("title"),
                    entry.get("purpose"),
                    entry.get("dashboard", {}).get("id"),
                    entry.get("dashboard", {}).get("title"),
                    entry.get("source_type"),
                    entry.get("definition_path"),
                    " ".join(entry.get("query_parameters", ())),
                    " ".join(entry.get("controls", ())),
                    " ".join(entry.get("downstream_views", ())),
                    " ".join(
                        column.get("name", "")
                        for column in entry.get("output", {}).get("schema", ())
                    ),
                )
                if value
            ).casefold()
            connection.execute(
                "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry["alias"],
                    entry["reference"],
                    entry["dashboard"]["id"],
                    entry["kind"],
                    entry["stage"],
                    entry.get("source_type"),
                    _json(entry.get("query_parameters", [])),
                    search_text,
                    _json(entry),
                ),
            )
        connection.execute("INSERT INTO metadata VALUES ('schema', ?)", (ANALYSIS_CATALOG_SCHEMA,))
        connection.execute("INSERT INTO metadata VALUES ('generation', ?)", (generation,))
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"Analysis Catalog integrity check failed: {integrity}")
    finally:
        connection.close()


def _next_generation(pointer: dict[str, Any] | None, generations: Path) -> str:
    numbers: list[int] = []
    candidates = [str((pointer or {}).get("generation", ""))]
    candidates.extend(path.name for path in generations.glob("catalog-*.sqlite"))
    for current in candidates:
        try:
            numbers.append(int(current.removeprefix("catalog-").removesuffix(".sqlite")))
        except ValueError:
            continue
    number = max(numbers, default=0) + 1
    return f"catalog-{number:06d}.sqlite"


class AnalysisCatalog:
    def __init__(
        self,
        *,
        workspace: Path,
        generation: str,
        entries: list[dict[str, Any]],
        stale: bool = False,
        diagnostics: list[dict[str, Any]] | None = None,
    ):
        self.workspace = workspace
        self.generation = generation
        self.entries = entries
        self.stale = stale
        self.diagnostics = list(diagnostics or [])
        self._by_alias = {entry["alias"]: entry for entry in entries}
        self._by_reference = {entry["reference"]: entry for entry in entries}

    def resolve(self, reference: str) -> dict[str, Any]:
        raw = reference.strip().removeprefix("@")
        entry = self._by_alias.get(raw) or self._by_reference.get(raw)
        if entry is None:
            raise ValidationFailure(
                f"Unknown Analysis reference: {reference}",
                details={
                    "code": "analysis_reference_unknown",
                    "reference": reference,
                    "action": "Run dataviz analyze search WORKSPACE QUERY --format json",
                },
            )
        return entry

    def select(
        self,
        *,
        query: str = "",
        kind: str | None = None,
        dashboard: str | None = None,
        source_type: str | None = None,
        parameter: str | None = None,
        regex: bool = False,
        include_internal: bool = False,
        include_untrusted: bool = False,
    ) -> list[dict[str, Any]]:
        pattern = None
        terms: list[str] = []
        if query and regex:
            if len(query) > 1_000:
                raise ValidationFailure(
                    "Analysis search regular expression is too long",
                    details={"code": "analysis_search_regex_too_long", "limit": 1000},
                )
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as error:
                raise ValidationFailure(
                    f"Invalid Analysis search regular expression: {error}",
                    details={
                        "code": "analysis_search_regex_invalid",
                        "pattern": query,
                        "reason": str(error),
                    },
                ) from error
        else:
            terms = [term.casefold() for term in query.split() if term]
        selected = []
        for entry in self.entries:
            if not include_internal and entry.get("visibility", "public") != "public":
                continue
            if (
                not include_untrusted
                and entry.get("kind") in {"base_output", "derived_output"}
                and entry.get("assurance", {}).get("status", "draft")
                not in {"reviewed", "certified"}
            ):
                continue
            if kind and entry["kind"] != kind:
                continue
            if dashboard and entry["dashboard"]["id"] != dashboard:
                continue
            if source_type and source_type not in {
                entry.get("source_type"),
                *entry.get("source_types", ()),
            }:
                continue
            if parameter and parameter not in entry.get("query_parameters", ()):
                continue
            haystack = _json(entry).casefold()
            if pattern is not None and pattern.search(haystack) is None:
                continue
            if terms and not all(term in haystack for term in terms):
                continue
            selected.append(entry)
        return sorted(
            selected,
            key=lambda entry: (
                entry["dashboard"]["id"],
                entry["kind"],
                entry["reference"],
            ),
        )

    def overview(
        self,
        entries: list[dict[str, Any]],
        *,
        fold: bool = True,
        expand_occurrences: bool = False,
        top: int | None = None,
    ) -> list[dict[str, Any]]:
        """Attach usage and conservatively fold byte-identical implementations."""

        keys = [
            output_analysis_usage(entry["reference"])
            for entry in entries
            if entry.get("kind") in {"base_output", "derived_output"}
        ]
        usage = read_usage_best_effort(self.workspace, keys=keys)

        def occurrence(entry: dict[str, Any]) -> dict[str, Any]:
            result = dict(entry)
            item = usage.get(output_analysis_usage(entry["reference"]))
            result["usage"] = item or {"use_count": 0, "last_used_at": None}
            return result

        enriched = [occurrence(entry) for entry in entries]
        if not fold:
            grouped = enriched
        else:
            buckets: dict[str, list[dict[str, Any]]] = {}
            order: list[str] = []
            for entry in enriched:
                identity = (
                    entry.get("equivalence_hash")
                    if entry.get("kind") in {"base_output", "derived_output"}
                    else None
                ) or f"reference:{entry['reference']}"
                if identity not in buckets:
                    buckets[identity] = []
                    order.append(identity)
                buckets[identity].append(entry)
            grouped = []
            for identity in order:
                occurrences = buckets[identity]
                representative = dict(occurrences[0])
                representative["representative"] = {
                    "alias": representative["alias"],
                    "reference": representative["reference"],
                }
                representative["occurrence_count"] = len(occurrences)
                representative["usage"] = {
                    "use_count": sum(
                        int(item["usage"].get("use_count") or 0)
                        for item in occurrences
                    ),
                    "last_used_at": max(
                        (
                            str(item["usage"].get("last_used_at"))
                            for item in occurrences
                            if item["usage"].get("last_used_at")
                        ),
                        default=None,
                    ),
                }
                if expand_occurrences:
                    representative["references"] = [
                        {
                            "alias": item["alias"],
                            "reference": item["reference"],
                            "dashboard": item["dashboard"],
                            "usage": item["usage"],
                        }
                        for item in occurrences
                    ]
                grouped.append(representative)
        return grouped[:top] if top is not None else grouped


def _catalog_from_pointer(
    root: Path,
    pointer: dict[str, Any],
    *,
    stale: bool = False,
    diagnostics: list[dict[str, Any]] | None = None,
) -> AnalysisCatalog:
    generation = pointer["generation"]
    path = root / ".dataviz" / "catalog" / "generations" / generation
    return AnalysisCatalog(
        workspace=root,
        generation=generation,
        entries=_read_generation(path),
        stale=stale,
        diagnostics=diagnostics,
    )


def _fallback_catalog(
    root: Path,
    pointer: dict[str, Any] | None,
    generations: Path,
    error: Exception,
) -> AnalysisCatalog | None:
    if not pointer:
        return None
    generation = pointer.get("generation")
    if not isinstance(generation, str) or not (generations / generation).is_file():
        return None
    return _catalog_from_pointer(
        root,
        pointer,
        stale=True,
        diagnostics=[
            {
                "level": "warning",
                "code": "analysis_catalog_refresh_failed_using_previous",
                "message": "Catalog refresh failed; the previous immutable generation is still active.",
                "details": {
                    "generation": generation,
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            }
        ],
    )


def ensure_analysis_catalog(
    workspace_path: Path | str,
    *,
    refresh: bool = False,
    max_snapshot_retries: int = 3,
) -> AnalysisCatalog:
    root = Path(workspace_path).resolve()
    catalog_root = root / ".dataviz" / "catalog"
    generations = catalog_root / "generations"
    current_path = catalog_root / "CURRENT.json"
    lock_path = catalog_root / "catalog.lock"
    generations.mkdir(parents=True, exist_ok=True)

    pointer = _read_pointer(current_path)
    observed_generation = (pointer or {}).get("generation")
    try:
        loaded = load_workspace(root)
        workspace_hash, dashboard_hashes = _fingerprints(loaded)
    except Exception as error:
        fallback = _fallback_catalog(root, pointer, generations, error)
        if fallback is not None:
            return fallback
        raise
    if not refresh and _pointer_is_fresh(
        pointer, workspace_hash, dashboard_hashes, generations
    ):
        return _catalog_from_pointer(root, pointer)

    with _exclusive_lock(lock_path):
        try:
            for _attempt in range(max_snapshot_retries):
                loaded = load_workspace(root)
                workspace_hash, dashboard_hashes = _fingerprints(loaded)
                pointer = _read_pointer(current_path)
                # A concurrent writer may have completed while this process was
                # waiting. Even explicit refresh must not create a duplicate
                # generation for the exact same request.
                if (
                    pointer
                    and pointer.get("generation") != observed_generation
                    and _pointer_is_fresh(
                        pointer, workspace_hash, dashboard_hashes, generations
                    )
                ):
                    return _catalog_from_pointer(root, pointer)
                if not refresh and _pointer_is_fresh(
                    pointer, workspace_hash, dashboard_hashes, generations
                ):
                    return _catalog_from_pointer(root, pointer)

                previous_by_dashboard: dict[str, list[dict[str, Any]]] = {}
                if pointer and (generations / str(pointer.get("generation", ""))).is_file():
                    for entry in _read_generation(generations / pointer["generation"]):
                        previous_by_dashboard.setdefault(entry["dashboard"]["id"], []).append(entry)
                previous_hashes = (pointer or {}).get("dashboard_hashes", {})
                can_reuse_previous = (
                    (pointer or {}).get("builder_version") == CATALOG_BUILDER_VERSION
                )
                entries: list[dict[str, Any]] = []
                for dashboard_id, dashboard in sorted(loaded.dashboards.items()):
                    definition_hash = dashboard_hashes[dashboard_id]
                    if (
                        can_reuse_previous
                        and previous_hashes.get(dashboard_id) == definition_hash
                        and dashboard_id in previous_by_dashboard
                    ):
                        entries.extend(previous_by_dashboard[dashboard_id])
                    else:
                        entries.extend(
                            _dashboard_entries(
                                loaded, dashboard_id, dashboard, definition_hash
                            )
                        )
                # Reassign across the complete Workspace so even a deliberately
                # constructed truncated-hash collision cannot become ambiguous.
                _assign_aliases(entries)

                # A second complete load detects additions, removals and edits that
                # happened while the immutable generation was being assembled.
                stable = load_workspace(root)
                stable_workspace_hash, stable_dashboard_hashes = _fingerprints(stable)
                if (
                    stable_workspace_hash != workspace_hash
                    or stable_dashboard_hashes != dashboard_hashes
                ):
                    refresh = True
                    continue

                generation = _next_generation(pointer, generations)
                temporary = generations / f".{generation}.{os.getpid()}.tmp"
                final = generations / generation
                try:
                    _write_generation(temporary, entries, generation)
                    os.replace(temporary, final)
                finally:
                    temporary.unlink(missing_ok=True)
                next_pointer = {
                    "schema": CATALOG_POINTER_SCHEMA,
                    "generation": generation,
                    "built_at": _now(),
                    "builder_version": CATALOG_BUILDER_VERSION,
                    "workspace_hash": workspace_hash,
                    "dashboard_hashes": dashboard_hashes,
                    "entries": len(entries),
                }
                atomic_write_text(
                    current_path,
                    json.dumps(next_pointer, ensure_ascii=False, indent=2) + "\n",
                )
                return AnalysisCatalog(workspace=root, generation=generation, entries=entries)
        except Exception as error:
            current = _read_pointer(current_path) or pointer
            fallback = _fallback_catalog(root, current, generations, error)
            if fallback is not None:
                return fallback
            raise

    raise ValidationFailure(
        "Workspace definitions kept changing while the Analysis Catalog was built",
        details={
            "code": "analysis_catalog_snapshot_unstable",
            "attempts": max_snapshot_retries,
        },
    )


def refresh_analysis_catalog_async(workspace_path: Path | str) -> threading.Thread:
    """Refresh after a Server watcher batch without blocking Canvas publication."""

    root = Path(workspace_path).resolve()

    def refresh_catalog() -> None:
        try:
            ensure_analysis_catalog(root)
        except Exception:
            # The previous immutable generation remains usable. The next CLI
            # request retries freshness and receives structured diagnostics if
            # the Workspace is still invalid.
            return

    thread = threading.Thread(
        target=refresh_catalog,
        name=f"dataviz-analysis-catalog-{root.name}",
        daemon=True,
    )
    thread.start()
    return thread
