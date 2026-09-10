"""Explicit server-side mutations, separate from the read/Transform DAG.

This module owns the definition and Python invocation context. Scheduling,
receipts and refresh publication belong to the server execution layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dataviz.identifiers import StableId, STABLE_ID_PATTERN

if TYPE_CHECKING:
    from dataviz.auth.resolver import AdapterResolver


class ServerActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_: Literal["dataviz/server-action/v1"] = Field(alias="schema")
    kind: Literal["server_action"] = "server_action"
    id: StableId
    description: str = ""
    code: str = Field(min_length=1)
    entrypoint: str = "execute"
    code_dependencies: list[str] = Field(default_factory=list)
    resources: dict[StableId, StableId] = Field(default_factory=dict)
    invalidates: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)

    @field_validator("entrypoint")
    @classmethod
    def valid_entrypoint(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError("entrypoint must be a Python identifier")
        return value

    @field_validator("invalidates")
    @classmethod
    def valid_effects(cls, values: list[str]) -> list[str]:
        for value in values:
            kind, separator, name = value.partition(":")
            if separator != ":" or kind not in {"source", "view"} or not re.fullmatch(
                STABLE_ID_PATTERN, name
            ):
                raise ValueError("invalidates entries must be source:<id> or view:<id>")
        if len(values) != len(set(values)):
            raise ValueError("invalidates entries must be unique")
        return values


def json_object(value: Any, *, label: str, max_bytes: int = 1_048_576) -> dict[str, Any]:
    """Copy only genuine JSON, rejecting lossy keys, NaN and oversized messages."""
    def check(item: Any) -> None:
        if item is None or type(item) in {str, bool, int, float}:
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError(f"{label} must contain only JSON values and string keys")

    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    try:
        check(value)
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > max_bytes:
            raise ValueError(f"{label} exceeds {max_bytes} bytes")
        return json.loads(encoded)
    except (RecursionError, OverflowError, UnicodeError) as error:
        raise ValueError(f"{label} is not a supported JSON object") from error


@dataclass
class ActionResources:
    """Server-owned binding resolution; no path/Adapter override from payload."""

    resolver: AdapterResolver
    aliases: dict[str, str]
    dashboard_bindings: dict[str, str]

    def _adapter(self, alias: str) -> str:
        if alias not in self.aliases:
            raise ValueError(f"Undeclared Action resource: {alias}")
        return self.aliases[alias]

    def config(self, alias: str) -> dict[str, object]:
        """Trusted Python only. Never return this credential-bearing dict to UI."""
        return self.resolver.runtime_config(self._adapter(alias), self.dashboard_bindings)

    def path(self, alias: str, relative_path: str) -> Path:
        return self.resolver.resolve_path(
            self._adapter(alias), relative_path, self.dashboard_bindings
        )


class ResourceAccess(Protocol):
    def config(self, alias: str) -> dict[str, object]: ...

    def path(self, alias: str, relative_path: str) -> Path: ...


@dataclass
class ActionContext:
    request_id: str
    payload: dict[str, Any]
    resources: ResourceAccess
    allowed_invalidations: frozenset[str]
    _invalidations: list[str] = field(default_factory=list, init=False, repr=False)

    def invalidate(self, reference: str) -> None:
        if reference not in self.allowed_invalidations:
            raise ValueError(f"Undeclared Action invalidation: {reference}")
        if reference not in self._invalidations:
            self._invalidations.append(reference)

    @property
    def invalidations(self) -> tuple[str, ...]:
        return tuple(self._invalidations)
