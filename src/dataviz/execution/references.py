from __future__ import annotations

from dataclasses import dataclass

from dataviz.errors import ValidationFailure


@dataclass(frozen=True, slots=True)
class OutputReference:
    node_id: str
    output: str = "main"

    @property
    def canonical(self) -> str:
        return f"{self.node_id}/{self.output}"


def parse_output_reference(value: str, *, default_kind: str = "source") -> OutputReference:
    raw = value.strip()
    if not raw:
        raise ValidationFailure("Output reference cannot be empty")
    node, separator, output = raw.partition("/")
    if ":" not in node:
        node = f"{default_kind}:{node}"
    kind, _, local_id = node.partition(":")
    if kind not in {"source", "transform", "browser"} or not local_id:
        raise ValidationFailure(f"Invalid output reference: {value}")
    return OutputReference(node_id=node, output=output if separator and output else "main")
