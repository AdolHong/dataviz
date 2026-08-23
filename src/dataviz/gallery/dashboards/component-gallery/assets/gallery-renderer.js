window.datavizRuntime.registerRenderer('gallery.spark', {
  validate(descriptor) {
    if (!Array.isArray(descriptor.rows)) throw new Error('gallery.spark expects rows[]');
  },
  mount(context, descriptor) {
    const root = document.createElement('div');
    root.className = 'gallery-spark';
    context.body.append(root);
    this.update(context, descriptor, {root});
    return {root};
  },
  update(_context, descriptor, state) {
    const rows = descriptor.rows.slice(0, 12);
    const max = Math.max(1, ...rows.map(row => Number(row.revenue || 0)));
    state.root.innerHTML = `<strong>Lifecycle extension</strong><div>${rows.map(row =>
      `<i title="${row.store_id} · ${row.month}" style="height:${Math.max(8, Number(row.revenue || 0) / max * 100)}%"></i>`
    ).join('')}</div><small>validate → mount → update → dispose</small>`;
    return state;
  },
  dispose(_context, state) { state.root?.remove(); },
});

const style = document.createElement('style');
style.textContent = `.gallery-spark{display:grid;align-content:center;gap:16px;height:100%;padding:24px}.gallery-spark>strong{font-size:24px}.gallery-spark>div{display:flex;align-items:end;gap:5px;height:130px;border-bottom:1px solid currentColor}.gallery-spark i{flex:1;min-width:4px;background:var(--dv-accent);opacity:.82}.gallery-spark small{font:10px "DM Mono",monospace;letter-spacing:.08em;text-transform:uppercase}`;
document.head.append(style);

const stories = window.datavizComponentStories || [];
if (stories.length) {
  const index = document.createElement('details');
  index.className = 'gallery-story-index';
  index.dataset.runtimePopover = '';
  index.dataset.overlayFloating = 'false';
  const groups = Map.groupBy
    ? Map.groupBy(stories, story => story.component.split('.')[0])
    : stories.reduce((result, story) => {
        const key = story.component.split('.')[0];
        if (!result.has(key)) result.set(key, []);
        result.get(key).push(story);
        return result;
      }, new Map());
  index.innerHTML = `<summary><span>STORIES</span><strong>${stories.length} runtime specimens</strong><i>⌃</i></summary><div class="gallery-story-index__panel">${[...groups].map(([category, values]) =>
    `<section><strong>${category}</strong>${values.map(story => `<button type="button" data-story-id="${story.id}">${story.title}</button>`).join('')}</section>`
  ).join('')}</div>`;
  document.body.append(index);
  stories.forEach(story => {
    const target = document.querySelector(story.gallery?.target || '');
    if (!target) return;
    target.dataset.componentStory = story.id;
    target.id ||= `story-${story.id.replace(/[^A-Za-z0-9_-]/g, '-')}`;
  });
  index.addEventListener('click', event => {
    const button = event.target.closest('[data-story-id]');
    if (!button) return;
    const story = stories.find(item => item.id === button.dataset.storyId);
    const target = story ? document.querySelector(story.gallery?.target || '') : null;
    if (!target) return;
    target.scrollIntoView({behavior:'smooth', block:'center'});
    target.animate(
      [{outlineColor:'transparent'}, {outlineColor:'var(--dv-accent)'}, {outlineColor:'transparent'}],
      {duration:1200, easing:'ease-out'},
    );
    index.open = false;
  });
  window.datavizComponents?.hydrate(index);
}

const storyStyle = document.createElement('style');
storyStyle.textContent = `.gallery-story-index{position:fixed;z-index:900;right:18px;bottom:18px;width:min(360px,calc(100vw - 36px));font:11px "DM Mono",monospace}.gallery-story-index>summary{display:flex;align-items:center;gap:10px;padding:11px 13px;color:#fff;background:var(--dv-ink);border:1px solid var(--dv-ink);list-style:none;cursor:pointer;box-shadow:0 10px 30px #17211d24}.gallery-story-index>summary span{color:var(--dv-green);font-size:9px;letter-spacing:.12em}.gallery-story-index>summary strong{flex:1}.gallery-story-index>summary i{font-style:normal}.gallery-story-index__panel{display:grid;gap:12px;max-height:min(520px,70vh);padding:14px;background:var(--dv-panel);border:1px solid var(--dv-ink);box-shadow:0 18px 50px #17211d30;overflow:auto}.gallery-story-index__panel section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.gallery-story-index__panel section>strong{grid-column:1/-1;color:var(--dv-accent);font-size:9px;letter-spacing:.1em;text-transform:uppercase}.gallery-story-index__panel button{padding:7px 8px;color:var(--dv-ink);background:var(--dv-paper);border:1px solid var(--dv-line);text-align:left;cursor:pointer}.gallery-story-index__panel button:hover{border-color:var(--dv-ink);background:var(--dv-green)}`;
document.head.append(storyStyle);
