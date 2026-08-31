from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _safe_child(path: Path, parent: Path) -> bool:
    try:
        resolved = path.resolve()
        root = parent.resolve()
    except OSError:
        return False
    return resolved != root and root in resolved.parents and not path.is_symlink()


def _remove_empty_ancestors(path: Path, root: Path) -> None:
    """Remove empty cache namespace directories without ever removing the root."""
    current = path
    while _safe_child(current, root):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _cache_entry_directories(cache_root: Path) -> list[Path]:
    if not cache_root.exists():
        return []
    return sorted(
        {
            metadata.parent
            for metadata in cache_root.rglob("result.json")
            if metadata.is_file() and _safe_child(metadata.parent, cache_root)
        }
    )


def _candidate_rows(
    entries: Iterable[Path],
    *,
    root: Path,
    keep: int | None,
    max_age_seconds: float | None,
    now: float,
    protected_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    protected_names = protected_names or set()
    ordered: list[tuple[Path, float, bool]] = []
    for path in entries:
        if not _safe_child(path, root):
            continue
        try:
            ordered.append((path, path.stat().st_mtime, path.name in protected_names))
        except OSError:
            continue
    ordered.sort(key=lambda item: item[1], reverse=True)

    candidates: list[dict[str, Any]] = []
    for index, (path, modified_at, protected) in enumerate(ordered):
        if protected:
            continue
        reasons: list[str] = []
        if keep is not None and index >= keep:
            reasons.append("count")
        if max_age_seconds is not None and now - modified_at > max_age_seconds:
            reasons.append("age")
        if not reasons:
            continue
        candidates.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "bytes": _directory_size(path),
                "modified_at": datetime.fromtimestamp(
                    modified_at, tz=timezone.utc
                ).isoformat(),
                "reasons": reasons,
            }
        )
    return candidates


def cleanup_workspace_storage(
    workspace_root: Path,
    *,
    max_runs: int | None,
    run_max_age_seconds: float | None,
    max_cache_entries: int | None,
    cache_max_age_seconds: float | None,
    max_results: int | None = None,
    result_max_age_seconds: float | None = None,
    include_runs: bool = True,
    include_cache: bool = True,
    include_results: bool = True,
    apply: bool = False,
    protected_run_ids: set[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Plan or apply bounded cleanup strictly inside one Workspace's state dir."""
    workspace_root = workspace_root.resolve()
    state_root = workspace_root / ".dataviz"
    runs_root = state_root / "runs"
    cache_root = state_root / "cache"
    results_root = state_root / "results"
    parameter_options_root = state_root / "parameter-options"
    current = time.time() if now is None else now

    run_entries = (
        [path for path in runs_root.iterdir() if path.is_dir()]
        if include_runs and runs_root.exists()
        else []
    )
    runs = _candidate_rows(
        run_entries,
        root=runs_root,
        keep=max_runs,
        max_age_seconds=run_max_age_seconds,
        now=current,
        protected_names=protected_run_ids,
    )
    cache = _candidate_rows(
        _cache_entry_directories(cache_root) if include_cache else [],
        root=cache_root,
        keep=max_cache_entries,
        max_age_seconds=cache_max_age_seconds,
        now=current,
    )
    parameter_options_entries = (
        [
            path
            for path in parameter_options_root.glob("options_*")
            if path.is_dir()
        ]
        if include_cache and parameter_options_root.exists()
        else []
    )
    parameter_options = _candidate_rows(
        parameter_options_entries,
        root=parameter_options_root,
        keep=max_cache_entries,
        max_age_seconds=cache_max_age_seconds,
        now=current,
    )
    result_entries = (
        [path for path in results_root.glob("result_*") if path.is_dir()]
        if include_results and results_root.exists()
        else []
    )
    result_leases = results_root / ".leases"
    protected_results = (
        {path.name.split("-", 1)[0] for path in result_leases.iterdir() if path.is_file()}
        if result_leases.exists()
        else set()
    )
    results = _candidate_rows(
        result_entries,
        root=results_root,
        keep=max_results,
        max_age_seconds=result_max_age_seconds,
        now=current,
        protected_names=protected_results,
    )

    errors: list[dict[str, str]] = []
    deleted: list[str] = []
    if apply:
        for item in [*runs, *cache, *parameter_options, *results]:
            path = Path(item["path"])
            if path.parent == runs_root:
                parent = runs_root
            elif path.parent == results_root:
                parent = results_root
            elif path.parent == parameter_options_root:
                parent = parameter_options_root
            else:
                parent = cache_root
            if not _safe_child(path, parent):
                errors.append({"path": str(path), "message": "unsafe cleanup path"})
                continue
            try:
                shutil.rmtree(path)
                deleted.append(str(path))
                if parent == cache_root:
                    _remove_empty_ancestors(path.parent, cache_root)
            except OSError as exc:
                errors.append({"path": str(path), "message": str(exc)})

    candidates = [*runs, *cache, *parameter_options, *results]
    return {
        "mode": "apply" if apply else "dry-run",
        "workspace": str(workspace_root),
        "runs": runs,
        "cache": cache,
        "parameter_options": parameter_options,
        "results": results,
        "candidate_count": len(candidates),
        "candidate_bytes": sum(item["bytes"] for item in candidates),
        "deleted_count": len(deleted),
        "deleted": deleted,
        "errors": errors,
    }
