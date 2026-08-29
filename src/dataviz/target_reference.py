from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dataviz.errors import ValidationFailure


TARGET_REFERENCE_SCHEMA = "dataviz/target-reference/v1"

TargetKind = Literal[
    "dashboard",
    "source",
    "source_output",
    "dataset_output",
    "interactive_output",
    "view",
]


class TargetReferenceContract(BaseModel):
    """Machine-readable form stored by Catalog, Result, and Evidence contracts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    schema_: Literal["dataviz/target-reference/v1"] = Field(alias="schema")
    kind: TargetKind
    dashboard: str
    reference: str
    object: str | None = None
    output: str | None = None

_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_TARGET_PATTERN = re.compile(
    rf"^(?P<dashboard>{_IDENTIFIER})::(?:source:(?P<source>{_IDENTIFIER})|"
    rf"(?P<node>source|dataset|interactive):(?P<object>{_IDENTIFIER})/"
    rf"(?P<output>{_IDENTIFIER})|view:(?P<view>{_IDENTIFIER}))$"
)
_DASHBOARD_PATTERN = re.compile(rf"^{_IDENTIFIER}$")


@dataclass(frozen=True, slots=True)
class TargetReference:
    dashboard: str
    kind: TargetKind
    object_id: str | None = None
    output_name: str | None = None

    @property
    def local_reference(self) -> str | None:
        if self.kind == "dashboard":
            return None
        if self.kind == "source":
            return f"source:{self.object_id}"
        if self.kind == "view":
            return f"view:{self.object_id}"
        node = {
            "source_output": "source",
            "dataset_output": "dataset",
            "interactive_output": "interactive",
        }[self.kind]
        return f"{node}:{self.object_id}/{self.output_name}"

    @property
    def canonical(self) -> str:
        local = self.local_reference
        return self.dashboard if local is None else f"{self.dashboard}::{local}"

    def as_contract(self) -> dict[str, str]:
        payload = {
            "schema": TARGET_REFERENCE_SCHEMA,
            "kind": self.kind,
            "dashboard": self.dashboard,
            "reference": self.canonical,
        }
        if self.object_id is not None:
            payload["object"] = self.object_id
        if self.output_name is not None:
            payload["output"] = self.output_name
        return payload


def parse_target_reference(value: str) -> TargetReference:
    """Parse the only public target grammar; never guess aliases or object names."""

    raw = value.strip()
    if _DASHBOARD_PATTERN.fullmatch(raw):
        return TargetReference(dashboard=raw, kind="dashboard")
    match = _TARGET_PATTERN.fullmatch(raw)
    if match is None:
        raise ValidationFailure(
            f"Invalid Target Reference: {value}",
            details={
                "code": "target_reference_invalid",
                "schema": TARGET_REFERENCE_SCHEMA,
                "reference": value,
                "expected": [
                    "<dashboard-id>",
                    "<dashboard-id>::source:<source-id>",
                    "<dashboard-id>::source:<source-id>/<output-name>",
                    "<dashboard-id>::dataset:<transform-id>/<output-name>",
                    "<dashboard-id>::interactive:<transform-id>/<output-name>",
                    "<dashboard-id>::view:<view-id>",
                ],
            },
        )
    dashboard = match.group("dashboard")
    view = match.group("view")
    if view is not None:
        return TargetReference(dashboard=dashboard, kind="view", object_id=view)
    source = match.group("source")
    if source is not None:
        return TargetReference(dashboard=dashboard, kind="source", object_id=source)
    node = match.group("node")
    kind: TargetKind = {
        "source": "source_output",
        "dataset": "dataset_output",
        "interactive": "interactive_output",
    }[node]
    return TargetReference(
        dashboard=dashboard,
        kind=kind,
        object_id=match.group("object"),
        output_name=match.group("output"),
    )
