import pytest

pytestmark = pytest.mark.e2e


def test_replaced_selects_release_overlay_records(control_page):
    page = control_page('control.select', '<main id="mount"></main>')
    result = page.evaluate('''async () => {
      const mount = document.querySelector('#mount'), api = window.datavizComponents;
      const baseline = api.overlay.records.size;
      for (let i = 0; i < 40; i++) {
        mount.innerHTML = '<div class="dv-control" data-control-component="select">'
          + '<select data-control-input><option value="a">A</option></select>'
          + '<div data-control-mount></div></div>';
        api.controls.hydrate(mount);
        const records = [...api.overlay.records].filter(record => mount.contains(record.owner));
        if (records.length !== 1) throw new Error('Expected actual select overlay');
        records[0].api.open();
        // A control moved synchronously into another tray is not destroyed.
        const control = mount.firstElementChild;
        control.remove();
        mount.append(control);
        await new Promise(resolve => queueMicrotask(resolve));
        if (!api.overlay.records.has(records[0])) throw new Error('Reparented overlay was destroyed');
        mount.replaceChildren();
        await new Promise(resolve => queueMicrotask(resolve));
      }
      return {baseline, current:api.overlay.records.size,
        open:document.querySelectorAll(':popover-open').length};
    }''')
    assert result['current'] == result['baseline']
    assert result['open'] == 0


def test_overlay_destroy_allows_clean_reregistration(control_page):
    page = control_page('control.select', '<details id="owner"><summary>Open</summary><div>Content</div></details>')
    result = page.evaluate('''() => {
      const api = window.datavizComponents.overlay, owner = document.querySelector('#owner');
      const first = api.registerDetails(owner);
      first.api.open();
      first.api.destroy();
      const closed = !owner.open;
      const second = api.registerDetails(owner);
      owner.querySelector('summary').click();
      return {closed, fresh:second !== first, open:owner.open, registered:api.records.has(second)};
    }''')
    assert result == {'closed': True, 'fresh': True, 'open': True, 'registered': True}
