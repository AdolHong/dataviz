from __future__ import annotations

from functools import lru_cache
import hashlib
from importlib.resources import files


PLOTLY_JS_VERSION = "4.0.0"
PLOTLY_JS_RESOURCE = f"vendor/plotly/plotly-{PLOTLY_JS_VERSION}.min.js"
PLOTLY_JS_SHA256 = "14461f3b4c91c8bb590a99d6d03c3fd031ca40eec07ebab79a5e3eac107cd7ca"


@lru_cache(maxsize=1)
def get_plotlyjs() -> str:
    payload = files("dataviz").joinpath(PLOTLY_JS_RESOURCE).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PLOTLY_JS_SHA256:
        raise RuntimeError(
            f"Bundled Plotly.js {PLOTLY_JS_VERSION} integrity mismatch: {actual}"
        )
    return payload.decode("utf-8")
