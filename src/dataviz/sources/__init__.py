from dataviz.sources.file import FileSourceRunner
from dataviz.sources.sql import SqlSourceRunner

SOURCE_RUNNERS = {
    "file": FileSourceRunner(),
    "sql": SqlSourceRunner(),
}

__all__ = ["SOURCE_RUNNERS"]
