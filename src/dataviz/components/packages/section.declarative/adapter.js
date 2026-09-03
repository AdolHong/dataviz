(function installDeclarativeSectionAdapter(global) {
  'use strict';
  const install = event => {
    const runtime = event?.detail || global.datavizRuntime;
    const components = global.datavizComponents;
    const controller = components?.sectionDeclarative;
    const view = runtime?.viewAdapter;
    if (!runtime || !controller || !view || runtime.sectionAdapter) return;

    const states = new Map();
    let disposed = false;
    const mountedCount = () => document.querySelectorAll(
      '.dv-repeat-card[data-repeat-mounted="true"]'
    ).length;
    const observer = typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver(entries => {
          entries.forEach(entry => {
            const card = entry.target;
            if (entry.isIntersecting) card.__datavizRepeatMount?.();
            else card.__datavizRepeatUnmount?.();
          });
        }, {rootMargin:'520px 0px'});
    const mountCard = card => {
      if (card.dataset.repeatMounted === 'true' || !card.__datavizRepeatRender) return;
      card.dataset.repeatMounted = 'true';
      card.__datavizRepeatRender();
      runtime.metrics.repeat.mounted = mountedCount();
      runtime.metrics.repeat.maxMounted = Math.max(
        runtime.metrics.repeat.maxMounted,
        runtime.metrics.repeat.mounted,
      );
    };
    const unmountCard = card => {
      if (
        card.dataset.repeatMounted !== 'true'
        || card.__datavizRepeatSpec?.recycle_offscreen === false
      ) return;
      view.disposeRenderer(card, card.dataset.viewId);
      view.clearRoot(card, card.dataset.viewId);
      card.dataset.repeatMounted = 'false';
      card.dataset.viewStatus = 'loading';
      const placeholder = document.createElement('div');
      placeholder.className = 'dv-view-placeholder dv-repeat-placeholder';
      placeholder.innerHTML = '<span></span><small>Recycled · scroll nearby to render</small>';
      card.querySelector('.dv-view-body')?.append(placeholder);
      runtime.metrics.repeat.disposed += 1;
      runtime.metrics.repeat.mounted = mountedCount();
    };
    const disposeCard = card => {
      observer?.unobserve(card);
      if (card.dataset.repeatDisposed === 'true') return;
      card.dataset.repeatDisposed = 'true';
      if (card.dataset.repeatMounted === 'true') {
        view.disposeRenderer(card, card.dataset.viewId);
        view.clearRoot(card, card.dataset.viewId);
        runtime.metrics.repeat.disposed += 1;
      }
      card.remove();
      runtime.metrics.repeat.mounted = mountedCount();
    };
    const ensureToolbar = state => {
      if (state.toolbar?.isConnected) return;
      const toolbar = document.createElement('div');
      toolbar.className = 'dv-repeat-toolbar';
      toolbar.innerHTML = `<label class="dv-repeat-search"><span>Search groups</span><input type="search" placeholder="${
        components.viewDeclarative.escape(state.spec.search_placeholder || 'Search groups…')
      }"></label><small data-repeat-summary aria-live="polite"></small><button type="button" data-repeat-more>Load more</button>`;
      const input = toolbar.querySelector('input');
      input.hidden = state.spec.searchable === false;
      input.closest('label').hidden = state.spec.searchable === false;
      let scheduled = 0;
      input.addEventListener('input', () => {
        cancelAnimationFrame(scheduled);
        scheduled = requestAnimationFrame(() => {
          state.query = input.value.trim().toLocaleLowerCase();
          state.visibleLimit = Number(state.spec.page_size || 40);
          runtime.metrics.repeat.searches += 1;
          reconcile(state);
        });
      });
      toolbar.querySelector('[data-repeat-more]').addEventListener('click', () => {
        state.visibleLimit += Number(state.spec.page_size || 40);
        reconcile(state);
      });
      state.toolbar = toolbar;
      state.host.prepend(toolbar);
    };
    const reconcile = state => {
      const started = performance.now();
      const {host, spec} = state;
      ensureToolbar(state);
      const filtered = state.query
        ? state.instances.filter(instance => (
            instance.searchText.toLocaleLowerCase().includes(state.query)
          ))
        : state.instances;
      const visible = filtered.slice(0, state.visibleLimit);
      const current = new Map(Array.from(
        host.querySelectorAll(':scope > .dv-repeat-card')
      ).map(card => [card.dataset.repeatKey, card]));
      const keep = new Set(visible.map(instance => instance.key));
      current.forEach((card, key) => {
        if (!keep.has(key)) disposeCard(card);
      });
      let empty = host.querySelector(':scope > .dv-repeat-empty');
      if (!visible.length) {
        if (!empty) {
          empty = document.createElement('div');
          empty.className = 'dv-repeat-empty';
          host.append(empty);
        }
        const heading = state.query
          ? 'No matching groups'
          : spec.template === 'selection-gallery' ? 'Nothing selected' : 'No groups available';
        empty.innerHTML = `<strong>${heading}</strong><span>${components.viewDeclarative.escape(
          spec.empty_text || 'No data matches the current selections.'
        )}</span>`;
      } else empty?.remove();
      visible.forEach((instance, index) => {
        let card = current.get(instance.key);
        if (!card) {
          card = document.createElement('article');
          card.className = 'dv-view dv-view--client dv-repeat-card';
          card.dataset.viewId = instance.id;
          card.dataset.repeatKey = instance.key;
          card.dataset.viewStatus = 'loading';
          card.dataset.repeatMounted = 'false';
          card.innerHTML = '<header class="dv-view-header"><div class="dv-view-heading"><span class="dv-view-title" role="heading" aria-level="3"></span><p class="dv-view-description"></p></div><div class="dv-view-actions"><small data-view-status-label>queued</small></div></header><div class="dv-view-body"><div class="dv-view-placeholder">Waiting to enter the viewport</div></div>';
        }
        delete card.dataset.repeatDisposed;
        card.__datavizRepeatSpec = spec;
        card.style.setProperty('--dv-repeat-index', index);
        card.querySelector('.dv-view-title').textContent = instance.title;
        const description = card.querySelector('.dv-view-description');
        description.textContent = instance.description || '';
        const descriptionField = `views.${instance.sourceViewId}.description`;
        if (global.dataviz.content_bindings?.[descriptionField]) {
          description.dataset.dvContentField = descriptionField;
        } else delete description.dataset.dvContentField;
        const changed = card.dataset.repeatSignature !== instance.signature;
        card.__datavizRepeatRender = () => view.renderInto(card, instance.id, instance.render);
        card.__datavizRepeatMount = () => mountCard(card);
        card.__datavizRepeatUnmount = () => unmountCard(card);
        host.append(card);
        if (changed) {
          card.dataset.repeatSignature = instance.signature;
          if (card.dataset.repeatMounted === 'true') card.__datavizRepeatRender();
          else if (spec.render === 'eager' || !observer) mountCard(card);
          else {
            view.clearRoot(card, instance.id);
            const placeholder = document.createElement('div');
            placeholder.className = 'dv-view-placeholder dv-repeat-placeholder';
            placeholder.innerHTML = '<span></span><small>Queued for lazy rendering</small>';
            card.querySelector('.dv-view-body').append(placeholder);
          }
        }
        if (spec.render === 'lazy' && observer) observer.observe(card);
      });
      const remaining = Math.max(0, filtered.length - visible.length);
      const more = state.toolbar.querySelector('[data-repeat-more]');
      more.hidden = remaining === 0;
      more.textContent = `Load ${Math.min(remaining, Number(spec.page_size || 40))} more`;
      state.toolbar.querySelector('[data-repeat-summary]').textContent = state.query
        ? `${visible.length} shown · ${filtered.length} matched · ${state.instances.length} total`
        : `${visible.length} shown · ${state.instances.length} groups`;
      host.dataset.repeatCount = String(state.instances.length);
      host.dataset.repeatFilteredCount = String(filtered.length);
      host.dataset.repeatRenderedCards = String(visible.length);
      host.dataset.repeatReconcileMs = (performance.now() - started).toFixed(2);
      runtime.metrics.repeat.cards = document.querySelectorAll('.dv-repeat-card').length;
      updateSection(host.closest('.dv-section'));
    };
    const renderRepeated = (spec, instances) => {
      const host = document.querySelector(
        `.dv-repeat[data-repeat-section="${CSS.escape(spec.section)}"]`
      );
      if (!host) return;
      let state = states.get(spec.section);
      if (!state) {
        state = {
          host,
          spec,
          instances:[],
          query:'',
          visibleLimit:Number(spec.page_size || 40),
          toolbar:null,
        };
        states.set(spec.section, state);
      }
      state.spec = spec;
      state.instances = instances;
      reconcile(state);
    };
    const statusPriority = ['error', 'unavailable', 'cancelled', 'loading', 'stale', 'empty', 'ready'];
    const updateSection = section => {
      if (!section) return;
      const statuses = Array.from(section.querySelectorAll('.dv-view')).map(item => (
        item.dataset.viewStatus || 'loading'
      ));
      const status = statuses.length
        ? statusPriority.find(candidate => statuses.includes(candidate)) || 'ready'
        : 'empty';
      section.dataset.sectionStatus = status;
      components.state?.apply(section, status, {label:status});
    };
    const sectionObserver = new MutationObserver(records => {
      new Set(records.map(record => record.target.closest?.('.dv-section')).filter(Boolean))
        .forEach(updateSection);
    });
    const sectionsRoot = document.querySelector('.dv-sections');
    if (sectionsRoot) {
      sectionObserver.observe(sectionsRoot, {
        subtree:true,
        childList:true,
        attributes:true,
        attributeFilter:['data-view-status'],
      });
      document.querySelectorAll('.dv-section').forEach(updateSection);
    }

    const adapter = {
      protocol:'dataviz/runtime/v15',
      states,
      renderRepeated,
      updateSection,
      disposeCard,
      dispose() {
        if (disposed) return;
        disposed = true;
        observer?.disconnect();
        sectionObserver.disconnect();
        states.forEach(state => {
          state.host?.querySelectorAll(':scope > .dv-repeat-card').forEach(disposeCard);
        });
        states.clear();
      },
    };
    runtime.sectionAdapter = adapter;
    global.dataviz.renderRepeatedSection = renderRepeated;
    controller.registerRepeatedViews(runtime);
    components.adapters = components.adapters || new Map();
    components.adapters.set('section.declarative', adapter);
  };
  install();
  global.addEventListener('dataviz:runtime-ready', install, {once:true});
})(window);
