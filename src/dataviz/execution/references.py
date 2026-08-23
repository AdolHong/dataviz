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


def parse_output_reference(value: str) -> OutputReference:
    raw = value.strip()
    if not raw:
        raise ValidationFailure("Output reference cannot be empty")
    node, separator, output = raw.partition("/")
    if ":" not in node:
        raise ValidationFailure(
            f"Output reference must include source:, dataset:, or interactive:: {value}"
        )
    kind, _, local_id = node.partition(":")
    if kind not in {"source", "dataset", "interactive"} or not local_id:
        raise ValidationFailure(f"Invalid output reference: {value}")
    if not separator or not output or "/" in output:
        raise ValidationFailure(
            "Output reference must include one explicit output name, for example "
            f"source:{local_id}/main: {value}"
        )
    return OutputReference(node_id=node, output=output)
