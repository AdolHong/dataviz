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

const galleryStates = [
  {id:'ready', label:'Ready', note:'Current, interactive and complete.'},
  {id:'loading', label:'Loading', note:'Work is active; previous context remains visible.'},
  {id:'stale', label:'Stale', note:'Inputs changed; this result needs recomputing.'},
  {id:'empty', label:'Empty', note:'Valid execution with no matching result.'},
  {id:'error', label:'Error', note:'Failure is contained inside this component.'},
  {id:'cancelled', label:'Cancelled', note:'Superseded or explicitly stopped work.'},
  {id:'unavailable', label:'Unavailable', note:'A dependency or capability is not available.'},
];

const galleryEscape = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

function galleryStateCopy(state, family) {
  const copy = {
    control: {
      ready:'Choose regions', loading:'Loading choices…', stale:'Choices changed upstream',
      empty:'No choices available', error:'Choices could not be loaded',
      cancelled:'Choice lookup cancelled', unavailable:'Control dependency missing',
    },
    compute: {
      ready:'Simulation ready', loading:'Running 100,000 trials…', stale:'Draft seed differs from result',
      empty:'No named output produced', error:'Model failed: invalid covariance matrix',
      cancelled:'Superseded by a newer run', unavailable:'Python runtime is not bundled',
    },
    view: {
      ready:'12,480', loading:'Refreshing this branch…', stale:'12,480',
      empty:'No rows match the current selections', error:'Renderer failed inside this View',
      cancelled:'Rendering cancelled', unavailable:'Required output is unavailable',
    },
    section: {
      ready:'All child Views are current', loading:'Two child Views are still loading',
      stale:'One child View needs recomputing', empty:'Every child View is empty',
      error:'One child View failed; siblings remain usable', cancelled:'Section work was cancelled',
      unavailable:'This section has no reachable outputs',
    },
  };
  return copy[family][state];
}

function galleryControlMarkup(state, index) {
  const disabled = state === 'unavailable' ? ' disabled' : '';
  const options = state === 'empty'
    ? ''
    : '<option value="east" selected>East</option><option value="south">South</option><option value="north">North</option>';
  return `<div class="dv-control gallery-state-control" data-control-component="select" data-gallery-state-lock="true" data-clearable="true">
    <select id="gallery-control-state-${index}" multiple data-control-input data-selection-input="gallery-state-${index}"${disabled}>${options}</select>
    <div data-control-mount></div>
  </div>`;
}

function galleryComputeMarkup(state, index) {
  const disabled = state === 'unavailable' ? ' disabled' : '';
  return `<label class="dv-compute-control gallery-state-compute">
    <span>Random seed</span>
    <input type="number" value="${state === 'empty' ? '' : 42}" aria-label="Random seed ${index}"${disabled}>
    <small>${galleryEscape(galleryStateCopy(state, 'compute'))}</small>
  </label>`;
}

function galleryViewMarkup(state, index) {
  const isMetric = ['ready', 'stale'].includes(state);
  return `<article class="dv-view gallery-state-view" data-view-id="gallery-state-view-${index}" data-view-status="${state}">
    <header class="dv-view-header"><div class="dv-view-heading"><strong class="dv-view-title">Revenue</strong><p class="dv-view-description">Scoped renderer boundary</p></div><small data-view-status-label>${state}</small></header>
    <div class="dv-view-body">${isMetric
      ? `<div class="dv-metric"><strong>${galleryEscape(galleryStateCopy(state, 'view'))}</strong><span>selected revenue</span></div>`
      : `<div class="dv-view-placeholder">${galleryEscape(galleryStateCopy(state, 'view'))}</div>`}</div>
  </article>`;
}

function gallerySectionMarkup(state, index) {
  const childStates = state === 'ready' ? ['ready', 'ready']
    : state === 'loading' ? ['ready', 'loading']
      : state === 'stale' ? ['ready', 'stale']
        : state === 'error' ? ['ready', 'error'] : [state, state];
  return `<section class="dv-section gallery-state-section" data-section-id="gallery-state-section-${index}">
    <header class="dv-section__header"><div><p class="dv-section__eyebrow">STATE AGGREGATE</p><h2>Quarter pulse</h2></div></header>
    <div class="dv-section__body">${childStates.map((child, childIndex) => `<div class="gallery-mini-view" data-component-status="${child}"><i></i><span>${childIndex ? 'Orders' : 'Revenue'}</span><strong>${child}</strong></div>`).join('')}</div>
    <p class="gallery-state-section__note">${galleryEscape(galleryStateCopy(state, 'section'))}</p>
  </section>`;
}

function galleryStateMatrix(family, title, description, render) {
  const section = document.createElement('section');
  section.id = `story-${family}-state-matrix`;
  section.className = `gallery-contract gallery-contract--${family}`;
  section.innerHTML = `<header class="gallery-contract__header"><div><p>7-STATE CONTRACT / ${family.toUpperCase()}</p><h2>${galleryEscape(title)}</h2></div><span>${galleryEscape(description)}</span></header>
    <div class="gallery-state-matrix">${galleryStates.map((state, index) => `<article class="gallery-state-card" data-gallery-status="${state.id}">
      <header><span>${String(index + 1).padStart(2, '0')}</span><strong>${state.label}</strong><i data-component-state-label>${state.id}</i></header>
      <div class="gallery-state-card__specimen">${render(state.id, index)}</div>
      <p>${galleryEscape(state.note)}</p>
    </article>`).join('')}</div>`;
  return section;
}

function galleryScaleControl(count) {
  const section = document.createElement('article');
  section.id = `story-control-scale-${count}`;
  section.className = 'gallery-scale-card';
  const searchMode = count >= 100 ? 'always' : 'auto';
  const virtualMode = count >= 1000 ? 'always' : 'auto';
  section.innerHTML = `<header><div><p>${String(count).padStart(4, '0')} / REAL OPTIONS</p><h3>${count.toLocaleString()} choices</h3></div><span>${count >= 1000 ? 'SEARCH + VIRTUAL' : count >= 100 ? 'SEARCH' : 'COMPACT'}</span></header>
    <div class="dv-control gallery-scale-control" data-control-component="select" data-search-mode="${searchMode}" data-virtual-mode="${virtualMode}" data-search-placeholder="Search all ${count.toLocaleString()} options…" data-viewport-height="228" data-clearable="true">
      <select id="gallery-control-scale-${count}" multiple data-control-input data-selection-input="gallery-scale-${count}"></select>
      <div data-control-mount></div>
    </div>
    <footer><span data-gallery-scale-metrics>Native ${count.toLocaleString()} · enhanced pending</span><i>${count >= 1000 ? 'bounded row DOM' : 'full option contract'}</i></footer>`;
  const select = section.querySelector('select');
  const fragment = document.createDocumentFragment();
  for (let index = 1; index <= count; index += 1) {
    const option = document.createElement('option');
    const value = String(index).padStart(4, '0');
    option.value = value;
    option.textContent = `Store ${value}`;
    option.dataset.group = `Portfolio ${String.fromCharCode(65 + Math.floor((index - 1) / Math.max(1, Math.ceil(count / 4))))}`;
    fragment.append(option);
  }
  select.append(fragment);
  return section;
}

function galleryThemeMatrix() {
  const definitions = [
    ['business', 'Business', 'Modern indigo default'],
    ['plain', 'Plain', 'Minimal neutral analysis'],
    ['editorial', 'Editorial', 'Warm narrative report'],
    ['terminal', 'Terminal', 'Dark technical monitoring'],
  ];
  const section = document.createElement('section');
  section.className = 'gallery-contract gallery-contract--themes';
  section.innerHTML = `<header class="gallery-contract__header"><div><p>THEME CONTRACT / PRESENTATION.SHELL</p><h2>One semantic surface, four voices</h2></div><span>Every preset maps the same stable tokens into Canvas, controls, charts and tables.</span></header>
    <div class="gallery-theme-grid">${definitions.map(([id, title, note]) => `<article class="gallery-theme-card dv-theme--${id}" data-theme-preview="${id}">
      <header><span>${title}</span><small>${note}</small></header>
      <strong>¥1,594,000</strong><p>Selected revenue</p>
      <div><i></i><i></i><i></i><i></i></div>
      <footer><span>Ready</span><button type="button">Inspect</button></footer>
    </article>`).join('')}</div>`;
  return section;
}

function buildGalleryContractLab() {
  const shell = document.querySelector('.dv-default-shell') || document.querySelector('.dv-canvas');
  if (!shell || document.querySelector('.gallery-contract-lab')) return;
  const lab = document.createElement('section');
  lab.className = 'gallery-contract-lab';
  lab.innerHTML = `<header class="gallery-contract-lab__hero"><div><p>COMPONENT CONTRACT LAB / RUNTIME V2</p><h1>Every state.<br>Every scale.</h1></div><aside><strong>4 × 7</strong><span>semantic state specimens</span><strong>1,110</strong><span>real control options</span></aside></header>`;
  lab.append(
    galleryThemeMatrix(),
    galleryStateMatrix('control', 'Control lifecycle', 'Canonical native controls remain the source of truth.', galleryControlMarkup),
    galleryStateMatrix('compute', 'Compute lifecycle', 'Draft, committed and derived-result states stay explicit.', galleryComputeMarkup),
    galleryStateMatrix('view', 'View lifecycle', 'Loading and failure are isolated to one renderer host.', galleryViewMarkup),
    galleryStateMatrix('section', 'Section lifecycle', 'A Section reports the aggregate state of its child Views.', gallerySectionMarkup),
  );
  const scale = document.createElement('section');
  scale.className = 'gallery-contract gallery-contract--scale';
  scale.innerHTML = '<header class="gallery-contract__header"><div><p>SCALE CONTRACT / CONTROL.SELECT</p><h2>One API, three real workloads</h2></div><span>No mock counts: every native option exists in this page.</span></header>';
  const grid = document.createElement('div');
  grid.className = 'gallery-scale-grid';
  [10, 100, 1000].forEach(count => grid.append(galleryScaleControl(count)));
  scale.append(grid);
  lab.append(scale);
  shell.append(lab);
  window.datavizComponents?.hydrate(lab);
  galleryStates.forEach(state => {
    lab.querySelectorAll(`[data-gallery-status="${state.id}"]`).forEach(card => {
      window.datavizComponents?.state?.apply(card, state.id, {label:state.label});
      const subject = card.querySelector('.dv-control, .dv-compute-control, .dv-view, .dv-section');
      if (subject) window.datavizComponents?.state?.apply(subject, state.id, {label:state.label});
    });
  });
  [10, 100, 1000].forEach(count => {
    const host = lab.querySelector(`#story-control-scale-${count}`);
    const metrics = host?.querySelector('.dv-control')?._datavizControl?.metrics?.();
    const output = host?.querySelector('[data-gallery-scale-metrics]');
    if (metrics && output) output.textContent = `Native ${metrics.total.toLocaleString()} · ${metrics.virtual ? `${metrics.rendered} rendered` : 'full rows'}`;
  });
}

buildGalleryContractLab();

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
storyStyle.textContent = `
.gallery-contract-lab{display:grid;gap:clamp(42px,6vw,84px);margin-top:clamp(64px,8vw,120px);padding-top:clamp(36px,5vw,72px);border-top:1px solid var(--dv-line)}
.gallery-contract-lab__hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:40px;align-items:end;padding:clamp(24px,4vw,56px);color:#fff;background:var(--dv-header-bg);border-radius:var(--dv-radius);box-shadow:0 12px 34px rgba(26,35,126,.18)}
.gallery-contract-lab__hero p,.gallery-contract__header p,.gallery-scale-card header p{margin:0;color:var(--dv-green);font:600 10px "DM Mono",monospace;letter-spacing:.16em;text-transform:uppercase}
.gallery-contract-lab__hero h1{margin:12px 0 0;font:720 clamp(46px,7vw,92px)/.9 var(--dv-font-sans);letter-spacing:-.055em}
.gallery-contract-lab__hero aside{display:grid;grid-template-columns:auto auto;gap:7px 12px;align-items:baseline;padding:18px;border-left:1px solid #ffffff3b}
.gallery-contract-lab__hero aside strong{color:#b7ebd0;font:720 26px var(--dv-font-sans)}.gallery-contract-lab__hero aside span{font:9px var(--dv-font-mono);letter-spacing:.08em;text-transform:uppercase}
.gallery-contract{scroll-margin-top:24px}.gallery-contract__header{display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,38%);gap:24px;align-items:end;margin-bottom:18px;padding-bottom:14px;border-bottom:2px solid var(--dv-ink)}
.gallery-contract__header h2{margin:5px 0 0;color:var(--dv-accent-strong);font:720 clamp(30px,3.4vw,48px)/1 var(--dv-font-sans);letter-spacing:-.035em}.gallery-contract__header>span{color:var(--dv-muted);font-size:13px;line-height:1.45}
.gallery-theme-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.gallery-theme-card{display:grid;gap:12px;min-width:0;padding:18px;color:var(--dv-ink);background:var(--dv-panel);border:1px solid var(--dv-line);border-radius:var(--dv-radius,12px);box-shadow:var(--dv-shadow)}.gallery-theme-card>header{display:grid;gap:3px;padding-bottom:11px;border-bottom:1px solid var(--dv-line)}.gallery-theme-card>header span{font-size:17px;font-weight:720}.gallery-theme-card>header small,.gallery-theme-card>p{color:var(--dv-muted);font:9px/1.45 var(--dv-font-mono);text-transform:uppercase}.gallery-theme-card>strong{color:var(--dv-accent-strong);font:720 31px/1 var(--dv-font-sans);letter-spacing:-.04em}.gallery-theme-card>p{margin:0}.gallery-theme-card>div{display:flex;align-items:end;gap:5px;height:48px;padding-top:8px;border-bottom:1px solid var(--dv-line)}.gallery-theme-card>div i{flex:1;background:var(--dv-accent);border-radius:3px 3px 0 0}.gallery-theme-card>div i:nth-child(1){height:38%}.gallery-theme-card>div i:nth-child(2){height:78%;background:var(--dv-chart-2,var(--dv-green))}.gallery-theme-card>div i:nth-child(3){height:52%;background:var(--dv-chart-3,var(--dv-accent))}.gallery-theme-card>div i:nth-child(4){height:92%;background:var(--dv-chart-4,var(--dv-green))}.gallery-theme-card>footer{display:flex;align-items:center;justify-content:space-between;gap:8px}.gallery-theme-card>footer span{color:var(--dv-green);font:700 9px var(--dv-font-mono);text-transform:uppercase}.gallery-theme-card>footer button{padding:6px 9px;color:var(--dv-accent-strong);background:var(--dv-soft);border:1px solid var(--dv-line);border-radius:5px;font-size:10px}
.gallery-state-matrix{display:grid;grid-template-columns:repeat(7,minmax(180px,1fr));gap:9px;overflow-x:auto;padding:0 2px 18px;scroll-snap-type:x proximity}
.gallery-state-card{display:flex;flex-direction:column;min-height:330px;background:color-mix(in srgb,var(--dv-panel) 96%,transparent);border:1px solid var(--dv-line);border-top:4px solid var(--dv-component-state,var(--dv-green));border-radius:var(--dv-radius);box-shadow:var(--dv-shadow);overflow:hidden;scroll-snap-align:start}
.gallery-state-card[data-gallery-status="loading"]{--dv-component-state:#3973ad}.gallery-state-card[data-gallery-status="empty"]{--dv-component-state:#87908b}.gallery-state-card[data-gallery-status="ready"]{--dv-component-state:var(--dv-green)}
.gallery-state-card>header{display:grid;grid-template-columns:auto 1fr;gap:3px 8px;align-items:center;padding:12px;border-bottom:1px solid var(--dv-line)}.gallery-state-card>header>span{grid-row:1/3;color:var(--dv-muted);font:9px var(--dv-font-mono)}.gallery-state-card>header>strong{font:700 17px var(--dv-font-sans)}.gallery-state-card>header>i{color:var(--dv-component-state);font:8px var(--dv-font-mono);font-style:normal;letter-spacing:.1em;text-transform:uppercase}
.gallery-state-card__specimen{flex:1;min-height:190px;padding:12px}.gallery-state-card>p{min-height:62px;margin:0;padding:11px 12px;color:#69716c;border-top:1px solid var(--dv-line);font:9px/1.5 "DM Mono",monospace}
.gallery-state-control .dv-choice-trigger{min-height:54px}.gallery-state-card[data-gallery-status="loading"] .gallery-state-card__specimen,.gallery-state-card[data-gallery-status="stale"] .gallery-state-card__specimen{opacity:.62}.gallery-state-card[data-gallery-status="unavailable"] .gallery-state-card__specimen{filter:grayscale(1);opacity:.52}
.gallery-state-compute input{font-size:18px!important}.gallery-state-compute small{line-height:1.5}.gallery-state-view{min-height:190px;box-shadow:none}.gallery-state-view .dv-view-header{padding:9px}.gallery-state-view .dv-view-title{font-size:14px}.gallery-state-view .dv-view-description{font-size:9px}.gallery-state-view .dv-view-body{padding:10px}.gallery-state-view .dv-metric{min-height:100px}.gallery-state-view .dv-metric strong{font-size:38px}.gallery-state-view .dv-view-placeholder{min-height:100px;font-size:8px;line-height:1.5}
.gallery-state-section{display:block}.gallery-state-section .dv-section__header{margin:0 0 8px}.gallery-state-section .dv-section__header h2{font-size:18px}.gallery-state-section .dv-section__body{display:grid;grid-template-columns:1fr 1fr;gap:6px}.gallery-mini-view{display:grid;gap:6px;min-height:76px;padding:9px;background:var(--dv-paper);border:1px solid var(--dv-line);font:8px "DM Mono",monospace;text-transform:uppercase}.gallery-mini-view i{width:18px;height:3px;background:var(--dv-component-state,var(--dv-green))}.gallery-mini-view strong{color:var(--dv-component-state,var(--dv-green))}.gallery-state-section__note{margin:8px 0 0;color:#68716c;font:9px/1.45 "DM Mono",monospace}
.gallery-scale-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.gallery-scale-card{display:grid;grid-template-rows:auto auto 1fr;gap:18px;min-width:0;padding:20px;background:var(--dv-panel);border:1px solid var(--dv-line);border-radius:var(--dv-radius);box-shadow:var(--dv-shadow)}.gallery-scale-card>header{display:flex;align-items:start;justify-content:space-between;gap:12px}.gallery-scale-card h3{margin:5px 0 0;font:700 28px var(--dv-font-sans)}.gallery-scale-card>header>span{padding:5px 7px;color:#fff;background:var(--dv-accent);border-radius:5px;font:8px var(--dv-font-mono);letter-spacing:.08em}.gallery-scale-card>footer{display:flex;justify-content:space-between;gap:10px;color:var(--dv-muted);font:8px var(--dv-font-mono);text-transform:uppercase}.gallery-scale-card>footer i{color:var(--dv-green);font-style:normal}.gallery-scale-control{min-width:0}
.gallery-story-index{position:fixed;z-index:900;right:18px;bottom:18px;width:min(360px,calc(100vw - 36px));font:11px var(--dv-font-mono)}.gallery-story-index>summary{display:flex;align-items:center;gap:10px;padding:11px 13px;color:#fff;background:var(--dv-accent-strong);border:1px solid var(--dv-accent-strong);border-radius:8px;list-style:none;cursor:pointer;box-shadow:var(--dv-shadow-float)}.gallery-story-index>summary span{color:#b7ebd0;font-size:9px;letter-spacing:.12em}.gallery-story-index>summary strong{flex:1}.gallery-story-index>summary i{font-style:normal}.gallery-story-index__panel{display:grid;gap:12px;max-height:min(520px,70vh);padding:14px;background:var(--dv-panel);border:1px solid var(--dv-line);border-radius:var(--dv-radius);box-shadow:var(--dv-shadow-float);overflow:auto}.gallery-story-index__panel section{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.gallery-story-index__panel section>strong{grid-column:1/-1;color:var(--dv-accent);font-size:9px;letter-spacing:.1em;text-transform:uppercase}.gallery-story-index__panel button{padding:7px 8px;color:var(--dv-ink);background:var(--dv-paper);border:1px solid var(--dv-line);border-radius:5px;text-align:left;cursor:pointer}.gallery-story-index__panel button:hover{color:var(--dv-accent-strong);border-color:var(--dv-accent);background:var(--dv-soft)}
@media(max-width:1180px){.gallery-theme-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:980px){.gallery-contract-lab__hero,.gallery-contract__header{grid-template-columns:1fr}.gallery-contract-lab__hero aside{border-top:1px solid #ffffff3b;border-left:0}.gallery-scale-grid{grid-template-columns:1fr}.gallery-state-matrix{grid-template-columns:repeat(7,minmax(230px,72vw))}}@media(max-width:620px){.gallery-theme-grid{grid-template-columns:1fr}}
`;
document.head.append(storyStyle);
