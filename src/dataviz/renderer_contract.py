from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dataviz.components import component_runtime_assets


RENDERER_CONTRACT_SCHEMA = "dataviz/renderer-contract/v1"


def load_renderer_contract(path: Path | None, renderer_id: str) -> dict[str, Any]:
    if path is None:
        return {
            "schema": RENDERER_CONTRACT_SCHEMA,
            "renderer": renderer_id,
            "cases": [
                {"type": renderer_id, "rows": [{"category": "A", "value": 1}]},
                {"type": renderer_id, "rows": []},
            ],
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != RENDERER_CONTRACT_SCHEMA:
        raise ValueError(f"Renderer contract must use {RENDERER_CONTRACT_SCHEMA}")
    if value.get("renderer") != renderer_id:
        raise ValueError(
            f"Renderer contract targets {value.get('renderer')!r}, expected {renderer_id!r}"
        )
    if not isinstance(value.get("cases"), list) or not value["cases"]:
        raise ValueError("Renderer contract requires at least one case")
    return value


def run_renderer_contract(
    script: Path,
    renderer_id: str,
    *,
    contract: Path | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Execute a custom Renderer lifecycle against a detached DOM in Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional dev install
        raise RuntimeError(
            "Renderer contract testing requires the dev extra: uv sync --extra dev"
        ) from exc

    definition = load_renderer_contract(contract, renderer_id)
    assets = component_runtime_assets(["renderer.custom"])
    component_source = "\n".join(item["source"] for item in assets["scripts"])
    renderer_source = script.read_text(encoding="utf-8")
    escaped_component_source = component_source.replace("</", "<\\/")
    escaped_renderer_source = renderer_source.replace("</", "<\\/")
    cases = json.dumps(definition["cases"], ensure_ascii=False).replace("</", "<\\/")
    document = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><style>{assets['style']}</style></head><body>
<script>
window.datavizRuntime = {{
  renderers: new Map(),
  registerRenderer(id, lifecycle) {{
    if (!id || typeof lifecycle?.mount !== 'function') throw new Error('Renderer requires id and mount()');
    if (this.renderers.has(id)) throw new Error(`Duplicate Renderer: ${{id}}`);
    this.renderers.set(id, lifecycle);
  }},
}};
</script>
<script>{escaped_component_source}</script>
<script>{escaped_renderer_source}</script>
<script>
(async () => {{
  try {{
    window.datavizComponents.installRendererContracts(window.datavizRuntime);
    window.datavizRendererContractResult = await window.datavizRuntime.testRenderer(
      {json.dumps(renderer_id)}, {cases}
    );
  }} catch (error) {{
    window.datavizRendererContractResult = {{
      renderer: {json.dumps(renderer_id)}, valid: false,
      failures: [{{phase: 'bootstrap', message: error?.message || String(error), stack: error?.stack || null}}],
    }};
  }}
}})();
</script></body></html>"""
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.set_content(document, wait_until="domcontentloaded")
        page.wait_for_function(
            "window.datavizRendererContractResult !== undefined",
            timeout=int(timeout_seconds * 1000),
        )
        result = page.evaluate("window.datavizRendererContractResult")
        browser.close()
    return {
        "schema": "dataviz/renderer-contract-result/v1",
        **result,
        "script": str(script.resolve()),
        "contract": str(contract.resolve()) if contract else "builtin",
        "console_errors": console_errors,
    }
