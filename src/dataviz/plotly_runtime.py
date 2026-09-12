from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib.resources import files


PLOTLY_JS_VERSION = "4.1.0"
PLOTLY_JS_RESOURCE = f"vendor/plotly/plotly-{PLOTLY_JS_VERSION}.min.js"
PLOTLY_JS_SHA256 = "03e18091beef5647aaf9e15f526981f325d760bb6b784fe0672a1e20585272cf"


@lru_cache(maxsize=1)
def get_plotlyjs() -> str:
    payload = files("dataviz").joinpath(PLOTLY_JS_RESOURCE).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PLOTLY_JS_SHA256:
        raise RuntimeError(
            f"Bundled Plotly.js {PLOTLY_JS_VERSION} integrity mismatch: {actual}"
        )
    return payload.decode("utf-8")
