"""Runnable, isolated writeback recipe exposed through CLI documentation."""

from dataviz.protocols import DASHBOARD_SCHEMA

SETUP = '''import sqlite3
with sqlite3.connect("annotations.sqlite") as db:
    db.execute("CREATE TABLE IF NOT EXISTS annotations (id TEXT PRIMARY KEY, label TEXT, revision INTEGER NOT NULL)")
    db.execute("INSERT OR IGNORE INTO annotations VALUES ('apple', NULL, 0)")
'''

ACTION = '''from sqlalchemy import create_engine, text
def execute(context):
    payload = context.payload
    if payload.get("label") not in (None, "sensitive", "negative"):
        raise ValueError("Unknown label")
    if not isinstance(payload.get("id"), str) or type(payload.get("revision")) is not int:
        raise ValueError("id and expected revision are required")
    engine = create_engine(context.resources.config("store")["url"])
    try:
        with engine.begin() as db:
            result = db.execute(text("UPDATE annotations SET label=:label, revision=revision+1 WHERE id=:id AND revision=:revision"), payload)
            if result.rowcount != 1:
                raise ValueError("Record changed or missing; reload before saving")
    finally:
        engine.dispose()
    context.invalidate("source:annotations")
    return {"saved": True, "id": payload["id"], "label": payload["label"], "revision": payload["revision"] + 1}
'''

RENDERER = '''window.datavizRuntime.registerRenderer('annotation.editor', {
  mount(context, descriptor) {
    const root = document.createElement('div');
    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Manual label');
    for (const [value, label] of [['', 'Unlabelled'], ['sensitive', 'Sensitive'], ['negative', 'Negative']]) {
      select.add(new Option(label, value));
    }
    const save = document.createElement('button');
    save.type = 'button'; save.textContent = 'Save';
    const retry = document.createElement('button');
    retry.type = 'button'; retry.textContent = 'Retry page sync'; retry.hidden = true;
    const message = document.createElement('p'); message.setAttribute('role', 'status');
    const state = {root, select, save, retry, message, context, row:descriptor.rows[0], busy:false, requestId:null};
    const show = receipt => {
      if (receipt.status !== 'succeeded') return;
      message.textContent = 'Saved; syncing page…';
    };
    const run = async refreshOnly => {
      if (state.busy) return;
      state.busy = true; save.disabled = true; retry.disabled = true;
      message.textContent = refreshOnly ? 'Saved; syncing page…' : 'Saving…';
      if (!refreshOnly) state.requestId = crypto.randomUUID();
      try {
        const receipt = refreshOnly
          ? await state.context.actions.refresh('save_label', state.requestId, {onProgress:show})
          : await state.context.actions.invoke('save_label', {
              id:state.row.id, revision:state.row.revision, label:select.value || null,
            }, {requestId:state.requestId, onProgress:show});
        const synced = receipt.refresh?.status === 'ready' && receipt.client_refresh?.status !== 'failed';
        message.textContent = synced ? 'Saved; page synced' : 'Saved; page not synced. Reload or retry sync.';
        retry.hidden = receipt.refresh?.status !== 'failed' && receipt.client_refresh?.status !== 'failed';
        state.recoveryRequired = !synced;
      } catch (error) {
        const saved = error.receipt?.status === 'succeeded';
        message.textContent = saved ? 'Saved; page sync failed' : 'Save not confirmed. Check receipt and data before another write. Request: ' + state.requestId;
        retry.hidden = !saved;
        state.recoveryRequired = true;
      } finally {
        state.busy = false; retry.disabled = false;
        save.disabled = !state.context.actions.available || !state.row || state.recoveryRequired;
      }
    };
    save.onclick = () => run(false);
    retry.onclick = () => run(true);
    select.value = state.row?.label || '';
    save.disabled = !context.actions.available || !state.row;
    root.append(select, save, retry, message); context.body.append(root);
    return state;
  },
  update(context, descriptor, state) {
    state.context = context;
    state.row = descriptor.rows[0];
    state.select.value = state.row?.label || '';
    state.save.disabled = state.busy || state.recoveryRequired || !state.row || !context.actions.available;
    return state;
  },
  dispose(context, state) { state.save.onclick = null; state.retry.onclick = null; state.root.remove(); }
});'''


def annotation_recipe():
    return {
        "purpose": "checkbox 保存 SQLite / 人工标注 / 保存后局部刷新：独立示例，不自动写入真实业务库。",
        "steps": [
            "在新建的临时目录保存 setup.py、connections.yaml、annotation.yaml；只对示例库执行 python setup.py。",
            "dataviz validate annotation.yaml --auth connections.yaml --strict",
            "dataviz serve annotation.yaml --auth connections.yaml；浏览器点击 Run 后再保存。",
            "切换标签、保存、重开页面验证持久化；并发旧 revision 必须拒绝，不能覆盖新判断。",
            "只读报告不可保存；未知结果保留 request ID，通过 actions status 核对，不自动重写。",
        ],
        "setup.py": SETUP,
        "connections.yaml": {"adapters": {"annotations_db": {
            "type": "sqlalchemy", "url": "sqlite:///annotations.sqlite",
        }}},
        "annotation.yaml": {
            "schema": DASHBOARD_SCHEMA, "id": "annotation-demo", "title": "Annotation example",
            "sources": [{"id": "annotations", "type": "sql", "adapter": "annotations_db",
                         "code": {"inline": "select id, label, revision from annotations order by id"},
                         "outputs": {"main": {"kind": "table"}}}],
            "server_actions": [{"id": "save_label", "code": {"inline": ACTION},
                                "resources": {"store": "annotations_db"},
                                "invalidates": ["source:annotations"]}],
            "canvas": {"scripts": [{"inline": RENDERER}]},
            "views": [{"id": "editor", "template": "custom", "renderer": "annotation.editor",
                       "input": "source:annotations/main"}],
        },
    }
