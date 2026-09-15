from __future__ import annotations


import re

import shutil


from pathlib import Path


import pytest


import yaml

from playwright.sync_api import (
    Page,
    expect,
)


from e2e.support.runtime import (
    _running_server,
    _copy_workspace,
    _open_single_fixture_dashboard,
    _open_dashboard,
    ROOT,
    MINIMAL,
)

@pytest.mark.e2e
def test_multi_page_example_renders_both_analysis_paths(page: Page, tmp_path: Path):
    root = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples/multi-page-workspace", root,
                    ignore=shutil.ignore_patterns(".dataviz", "__pycache__"))
    with _running_server(root) as url:
        page.set_viewport_size({"width": 1440, "height": 1050})
        _open_single_fixture_dashboard(page, url, root)
        frame = page.frame_locator("#canvas-frame")
        for page_id in ("annual", "history"):
            tab = page.locator(f'#page-navigation-list button[data-page-id="{page_id}"]')
            tab.click()
            expect(tab).to_have_attribute("aria-current", "page")
            expect(tab).to_have_css("border-top-width", "0px")
            expect(tab).to_have_css("background-color", "rgb(238, 240, 248)")
            expect(frame.locator("h1")).to_have_count(0)
            if page_id == "annual":
                page.screenshot(path=str(tmp_path / "before-run.png"), full_page=True)
            page.locator("#run-button").click()
            expect(frame.locator('[data-view-id="details"]')).to_contain_text("水果", timeout=30_000)
            expect(frame.locator('[data-view-id="trend"] .js-plotly-plot')).to_be_visible()
            expect(page.locator("#run-button strong")).to_have_text("Run", timeout=30_000)
            expect(frame.locator(".dv-report-header h1")).to_be_hidden()
            for width, height in ((1440, 1050), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                if width == 390:
                    expect(page.locator("body")).to_have_class(re.compile("sidebar-collapsed"))
                    expect(page.locator("#dashboard-sidebar")).not_to_be_in_viewport()
                image = tmp_path / f"{page_id}-{width}.png"
                page.screenshot(path=str(image), full_page=True)
                print(f"Example screenshot: {image}")
            page.set_viewport_size({"width": 1440, "height": 1050})


@pytest.mark.e2e
def test_sidebar_search_and_recursive_folder_expansion(page: Page, tmp_path: Path):
    workspace = _copy_workspace(MINIMAL, tmp_path / 'search-navigation')
    config = workspace / 'workspace.yaml'
    definition = yaml.safe_load(config.read_text())
    definition['folders'] = [{'path': name} for name in ['分析', '分析/季度', 'Archive', 'Archive/Old']]
    config.write_text(yaml.safe_dump(definition, allow_unicode=True))
    (workspace / 'dashboards/sales-overview').rename(workspace / 'dashboards/分析##季度##sales-overview')
    with _running_server(workspace) as base_url:
        page.goto(base_url, wait_until='domcontentloaded')
        folder = page.locator('.nav-folder__toggle', has_text='分析')
        nested = page.locator('.nav-folder__toggle', has_text='季度')
        archive = page.locator('.nav-folder__toggle', has_text='Archive')
        dashboard = page.locator('.nav-button[data-id="sales-overview"]')
        expect(folder).to_have_attribute('aria-expanded', 'false')
        expect(nested).not_to_be_visible()
        search = page.get_by_role('searchbox', name='Search dashboards and folders')
        search.fill('SALES-OVERVIEW')
        expect(dashboard).to_be_visible()
        expect(folder).to_have_attribute('aria-expanded', 'true')
        expect(archive).to_have_count(0)
        search.fill('季度')
        expect(dashboard).to_be_visible()
        search.fill('qwer-no-match')
        expect(page.locator('#nav-search-empty')).to_be_visible()
        expect(search).to_be_focused()
        page.get_by_role('button', name='Clear navigation search').click()
        expect(folder).to_have_attribute('aria-expanded', 'false')
        expect(dashboard).not_to_be_visible()
        folder.click(button='right')
        page.get_by_role('menuitem', name='Expand all subfolders', exact=True).click()
        expect(dashboard).to_be_visible()
        expect(nested).to_have_attribute('aria-expanded', 'true')
        expect(archive).to_have_attribute('aria-expanded', 'false')
        page.reload(wait_until='domcontentloaded')
        expect(dashboard).to_be_visible()
        # Blank navigation space is the root, not the last selected folder.
        page.locator('#dashboard-nav').click(button='right', position={'x': 4, 'y': 350})
        page.get_by_role('menuitem', name='Expand all subfolders', exact=True).click()
        expect(archive).to_have_attribute('aria-expanded', 'true')
        folder.click(button='right')
        page.get_by_role('menuitem', name='Collapse all subfolders', exact=True).click()
        expect(folder).to_have_attribute('aria-expanded', 'false')
        expect(nested).to_have_attribute('aria-expanded', 'false')
        expect(archive).to_have_attribute('aria-expanded', 'true')
        page.locator('#dashboard-nav').click(button='right', position={'x': 4, 'y': 350})
        page.get_by_role('menuitem', name='Collapse all subfolders', exact=True).click()
        expect(archive).to_have_attribute('aria-expanded', 'false')
        search.fill('sales')
        expect(dashboard).to_be_visible()
        for width in [1440, 390]:
            page.set_viewport_size({'width': width, 'height': 900})
            if page.locator('body').evaluate("el => el.classList.contains('sidebar-collapsed')"):
                page.locator('#sidebar-toggle').click()
            expect(search).to_be_visible()
            page.wait_for_function("() => document.querySelector('.rail').getBoundingClientRect().left >= 0")
            bounds = page.locator('.nav-search').bounding_box()
            assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
            page.screenshot(path=str(ROOT / '.test-evidence' / f'nav-search-{width}.png'))
        page.set_viewport_size({'width': 1440, 'height': 900})
        # Searching disables both custom row dragging and native folder dragging.
        search.fill('a')  # sales-overview and Archive both match.
        expect(dashboard).to_be_visible()
        expect(archive).to_be_visible()
        expect(archive).to_have_attribute('draggable', 'false')
        moves = []
        page.on('request', lambda request: moves.append(request.url)
                if request.method == 'PATCH' and '/api/navigation/' in request.url else None)
        source = dashboard.bounding_box()
        target = archive.bounding_box()
        assert source and target
        page.mouse.move(source['x'] + source['width'] / 2, source['y'] + source['height'] / 2)
        page.mouse.down()
        page.mouse.move(target['x'] + target['width'] / 2, target['y'] + target['height'] / 2, steps=8)
        expect(page.locator('.nav-drag-preview')).to_have_count(0)
        expect(page.locator('#nav-root-drop')).to_have_attribute('aria-hidden', 'true')
        page.mouse.up()
        expect(archive.locator('xpath=..').locator('.nav-button')).to_have_count(0)
        assert moves == []
        page.get_by_role('button', name='Clear navigation search').click()
        expect(archive).to_have_attribute('aria-expanded', 'false')
        page.reload(wait_until='domcontentloaded')
        expect(archive).to_have_attribute('aria-expanded', 'false')
        expect(archive).to_have_attribute('draggable', 'true')
        folder.focus()
        page.keyboard.press('Enter')
        nested.focus()
        page.keyboard.press('Enter')
        expect(dashboard).to_be_visible()


@pytest.mark.e2e
def test_sidebar_dashboard_can_be_dragged_and_renamed_from_context_menu(
    page: Page, tmp_path: Path
):
    page.set_default_timeout(5_000)
    workspace = _copy_workspace(MINIMAL, tmp_path / "navigation-editor")
    workspace_path = workspace / "workspace.yaml"
    definition = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    definition["folders"] = [{"path": "Archive", "order": 10}]
    workspace_path.write_text(
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with _running_server(workspace) as base_url:
        _open_dashboard(page, base_url, "sales-overview")
        dashboard = page.locator('.nav-button[data-id="sales-overview"]')
        folder = page.locator('.nav-folder__toggle', has_text="Archive")
        expect(dashboard).to_have_attribute("draggable", "false")
        expect(dashboard.locator(".nav-button__drag-handle")).to_have_count(0)

        source_box = dashboard.bounding_box()
        target_box = folder.bounding_box()
        assert source_box is not None and target_box is not None
        page.mouse.move(
            source_box["x"] + source_box["width"] / 2,
            source_box["y"] + source_box["height"] / 2,
        )
        page.mouse.down()
        page.mouse.move(
            target_box["x"] + target_box["width"] / 2,
            target_box["y"] + target_box["height"] / 2,
            steps=12,
        )
        expect(page.locator("body")).to_have_attribute("data-nav-dragging", "dashboard")
        preview = page.locator(".nav-drag-preview")
        expect(preview).to_be_visible()
        expect(dashboard).to_have_class(re.compile(r"\bis-dragging\b"))
        expect(folder.locator("xpath=..")).to_have_class(re.compile(r"\bis-drop-target\b"))
        preview_box = preview.bounding_box()
        assert preview_box is not None
        assert preview_box["y"] < source_box["y"] - 5
        page.mouse.up()
        expect(page.locator(".nav-drag-preview")).to_have_count(0)
        moved = workspace / "dashboards" / "Archive##sales-overview"
        expect(page.locator('.nav-folder .nav-button[data-id="sales-overview"]')).to_be_visible()
        assert (moved / "dashboard.yaml").is_file()

        dashboard = page.locator('.nav-button[data-id="sales-overview"]')
        dashboard.click(button="right")
        context_menu = page.locator("#nav-context-menu")
        expect(context_menu.get_by_role("menuitem", name="Rename")).to_be_visible()
        context_menu.get_by_role("menuitem", name="Rename").click()
        dialog = page.locator("#nav-dialog")
        expect(dialog.get_by_role("heading", name="Rename Dashboard")).to_be_visible()
        dialog.locator('input[name="title"]').fill("Sales review")
        dialog.get_by_role("button", name="Save name").click()

        renamed = workspace / "dashboards" / "Archive##Sales review"
        expect(page.locator('.nav-button[data-id="sales-overview"] strong')).to_have_text(
            "Sales review"
        )
        assert (renamed / "dashboard.yaml").is_file()
        assert not moved.exists()
        assert "/dashboards/sales-overview" in page.url

        dashboard = page.locator('.nav-button[data-id="sales-overview"]')
        source_box = dashboard.bounding_box()
        assert source_box is not None
        source_x = source_box["x"] + source_box["width"] / 2
        source_y = source_box["y"] + source_box["height"] / 2
        page.mouse.move(source_x, source_y)
        page.mouse.down()
        page.mouse.move(source_x + 10, source_y + 10, steps=4)
        root_drop = page.locator("#nav-root-drop")
        expect(root_drop).to_be_visible()
        root_box = root_drop.bounding_box()
        assert root_box is not None
        page.mouse.move(
            root_box["x"] + root_box["width"] / 2,
            root_box["y"] + root_box["height"] / 2,
            steps=12,
        )
        expect(root_drop).to_have_class(re.compile(r"\bis-drop-target\b"))
        page.mouse.up()
        expect(
            page.locator('#dashboard-nav > .nav-tree > .nav-level > .nav-button[data-id="sales-overview"]')
        ).to_be_visible()
        assert (workspace / "dashboards" / "Sales review" / "dashboard.yaml").is_file()
