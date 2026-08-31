from __future__ import annotations

from pathlib import Path
from typing import Any

from dataviz.errors import ValidationFailure
from dataviz.templates import RUNTIME_PROTOCOL_SCHEMA


PACKAGE_ROOT = Path(__file__).resolve().parent
WEB_COMPONENT_ASSET = PACKAGE_ROOT / "server" / "static" / "runtime-web-component-adapter.js"


def frontend_adapter_catalog() -> dict[str, dict[str, Any]]:
    return {
        "vanilla": {
            "schema": "dataviz/frontend-adapter/v1",
            "id": "vanilla",
            "status": "production",
            "protocol": RUNTIME_PROTOCOL_SCHEMA,
            "purpose": "Default Canvas, Selection, Transform and Renderer Runtime.",
            "dependency": "canvas-runtime.js",
        },
        "web-component": {
            "schema": "dataviz/frontend-adapter/v1",
            "id": "web-component",
            "status": "reference",
            "protocol": RUNTIME_PROTOCOL_SCHEMA,
            "purpose": (
                "Framework-independent reference client and <dataviz-output> element "
                f"that consume only the public {RUNTIME_PROTOCOL_SCHEMA} manifest."
            ),
            "dependency": "none",
            "server_url": "/runtime/web-component-adapter.js",
            "public_api": [
                "DatavizRuntimeV3Client",
                "<dataviz-output output=\"source:data/main\" mode=\"table\">",
                "<dataviz-output view=\"detail\" mode=\"count\">",
            ],
        },
    }


def frontend_adapter_source(name: str) -> str:
    normalized = name.strip().lower()
    if normalized != "web-component":
        raise ValidationFailure(
            f"Frontend Adapter has no exportable source: {name}",
            details={"available": ["web-component"]},
        )
    return WEB_COMPONENT_ASSET.read_text(encoding="utf-8")
