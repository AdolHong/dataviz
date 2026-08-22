from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DatavizError(Exception):
    """Base error with a stable machine-readable representation."""

    code = "dataviz_error"

    def __init__(self, message: str, *, file: Path | str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.file = str(file) if file else None
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.code,
            "message": self.message,
            "file": self.file,
            "details": self.details,
        }


class WorkspaceError(DatavizError):
    code = "workspace_error"


class ValidationFailure(DatavizError):
    code = "validation_error"


class ExecutionFailure(DatavizError):
    code = "execution_error"


class SourceFailure(ExecutionFailure):
    code = "source_error"


class WidgetFailure(ExecutionFailure):
    code = "widget_error"


@dataclass(slots=True)
class Diagnostic:
    level: str
    message: str
    file: str | None = None
    field: str | None = None
    code: str = "validation"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "file": self.file,
            "field": self.field,
        }

