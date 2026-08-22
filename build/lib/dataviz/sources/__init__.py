from dataviz.sources.file import FileSourceAdapter
from dataviz.sources.python import PythonSourceAdapter
from dataviz.sources.sql import SqlSourceAdapter

SOURCE_ADAPTERS = {
    "file": FileSourceAdapter(),
    "python": PythonSourceAdapter(),
    "sql": SqlSourceAdapter(),
}

__all__ = ["SOURCE_ADAPTERS"]
