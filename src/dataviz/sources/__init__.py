from dataviz.sources.base import SourceRunner
from dataviz.sources.file import FileSourceRunner
from dataviz.sources.sql import SqlSourceRunner

SOURCE_RUNNERS: dict[str, SourceRunner] = {
    "file": FileSourceRunner(),
    "sql": SqlSourceRunner(),
}

__all__ = ["SOURCE_RUNNERS"]
