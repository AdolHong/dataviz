(function installDeclarativeViewAdapter(global) {
  'use strict';
  const install = event => {
    const runtime = event?.detail || global.datavizRuntime;
    const components = global.datavizComponents;
    const controller = components?.viewDeclarative;
    const services = global.datavizRuntimeServices;
    if (!runtime || !controller || !services || runtime.viewAdapter) return;

    const states = new Map();
    let perspectiveSerial = 0;
    let disposed = false;
    const perspectiveOperationTimeoutMs = Math.max(
      100,
      Number(global.__datavizRendererOperationTimeoutMs || 15_000),
    );
    const node = id => document.querySelector(
      `.dv-view[data-view-id="${CSS.escape(id)}"]`
    );
    const bindingContext = (root, key, descriptor, generation) => {
      const binding = descriptor?.controlBinding;
      if (!binding) return null;
      return {
        ...binding,
        emit:(action, data = null) => global.dataviz.controlActions.dispatch({
          view_id:key,
          control:binding.control,
          generation:generation ?? root?._datavizRenderGeneration ?? 0,
          action,
          data,
        }),
      };
    };
    const context = (root, body, key, descriptor = null, generation = null) => ({
      root,
      body,
      key,
      viewId:key,
      runtime,
      charts:chartService,
      tables:tableService,
      controlBinding:bindingContext(root, key, descriptor, generation),
    });
    const setRendererSignal = (root, status, {active = null} = {}) => {
      if (!root) return;
      const signal = root.querySelector('[data-view-renderer-signal]');
      if (!signal) return;
      const normalized = String(status || 'not_run');
      signal.dataset.status = normalized;
      signal.hidden = ![
        'queued', 'loading', 'stale', 'error', 'cancelled', 'unavailable',
      ].includes(normalized);
      signal.setAttribute('aria-hidden', String(signal.hidden));
      if (active === true) root.dataset.rendererSignalActive = 'true';
      else if (active === false) delete root.dataset.rendererSignalActive;
    };
    const applyStatus = (root, status, label = status) => {
      if (!root) return;
      root.dataset.viewStatus = status;
      components.state?.apply(root, status, {label});
      const statusNode = root.querySelector('[data-view-status-label]');
      if (statusNode) statusNode.textContent = label;
      if (root.dataset.rendererSignalActive === 'true') {
        if (['ready', 'empty'].includes(status)) {
          setRendererSignal(root, status, {active:false});
        } else if (['error', 'cancelled', 'unavailable'].includes(status)) {
          setRendererSignal(root, status, {active:false});
        } else {
          setRendererSignal(root, status);
        }
      }
    };
    const releaseWheelAtBoundary = (
      host,
      enabled = () => true,
      ignoreNestedScroll = false,
    ) => {
      if (!host) return;
      host.__datavizWheelBoundaryEnabled = enabled;
      host.__datavizWheelBoundaryIgnoreNestedScroll = ignoreNestedScroll;
      if (host.__datavizWheelBoundary) return;
      host.__datavizWheelBoundary = true;
      host.addEventListener('wheel', wheelEvent => {
        if (
          wheelEvent.defaultPrevented
          || !host.__datavizWheelBoundaryEnabled?.()
          || wheelEvent.ctrlKey
          || !wheelEvent.deltaY
          || Math.abs(wheelEvent.deltaX) > Math.abs(wheelEvent.deltaY)
        ) return;
        const path = wheelEvent.composedPath();
        const hostIndex = path.indexOf(host);
        const candidates = path.slice(0, hostIndex + 1).filter(item => {
          if (!(item instanceof Element)) return false;
          const style = getComputedStyle(item);
          return /(auto|scroll|overlay)/.test(style.overflowY)
            && item.scrollHeight > item.clientHeight + 1;
        });
        const direction = Math.sign(wheelEvent.deltaY);
        const canConsume = !host.__datavizWheelBoundaryIgnoreNestedScroll
          && candidates.some(item => direction > 0
            ? item.scrollTop + item.clientHeight < item.scrollHeight - 1
            : item.scrollTop > 1);
        if (canConsume) return;
        const page = document.scrollingElement || document.documentElement;
        const pageCanConsume = page
          && page.scrollHeight > global.innerHeight + 1
          && (direction > 0
            ? page.scrollTop + global.innerHeight < page.scrollHeight - 1
            : page.scrollTop > 1);
        if (!pageCanConsume) return;
        const multiplier = wheelEvent.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? 16
          : wheelEvent.deltaMode === WheelEvent.DOM_DELTA_PAGE ? global.innerHeight : 1;
        wheelEvent.preventDefault();
        wheelEvent.stopImmediatePropagation();
        page.scrollTop += wheelEvent.deltaY * multiplier;
      }, {capture:true, passive:false});
    };
    const chartTheme = root => {
      const scope = root?.closest?.('.dv-canvas') || document.documentElement;
      const style = getComputedStyle(scope);
      const token = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
      const accent = token('--dv-accent', '#3949ab');
      return {
        ink:token('--dv-ink', '#202536'),
        muted:token('--dv-muted', '#667085'),
        line:token('--dv-line', '#d9e0ec'),
        grid:token('--dv-chart-grid', '#e8edf5'),
        panel:token('--dv-panel', '#ffffff'),
        accent,
        font:token('--dv-font-sans', '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'),
        palette:[
          accent,
          ...Array.from({length:7}, (_, index) => token(
            `--dv-chart-${index + 2}`,
            ['#26a69a', '#f2a93b', '#e76f51', '#7e57c2', '#2f80ed', '#4caf50', '#e65b7a'][index],
          )),
        ],
      };
    };
    const plotlyAxisTheme = (axis, theme) => {
      const source = axis || {};
      const title = typeof source.title === 'object' && source.title !== null
        ? {...source.title, font:{color:theme.muted, ...(source.title.font || {})}}
        : source.title;
      return {
        gridcolor:theme.grid,
        zerolinecolor:theme.line,
        linecolor:theme.line,
        tickcolor:theme.line,
        automargin:true,
        ...source,
        tickfont:{color:theme.muted, ...(source.tickfont || {})},
        ...(title === undefined ? {} : {title}),
      };
    };
    const plotlyTheme = (root, layout = {}) => {
      const theme = chartTheme(root);
      const hoverlabel = layout.hoverlabel || {};
      const legend = layout.legend || {};
      return {
        paper_bgcolor:'transparent',
        plot_bgcolor:'transparent',
        colorway:theme.palette,
        ...layout,
        font:{family:theme.font, color:theme.ink, ...(layout.font || {})},
        hoverlabel:{
          bgcolor:theme.panel,
          bordercolor:theme.line,
          ...hoverlabel,
          font:{family:theme.font, color:theme.ink, ...(hoverlabel.font || {})},
        },
        legend:{
          ...legend,
          font:{family:theme.font, color:theme.muted, ...(legend.font || {})},
        },
        xaxis:plotlyAxisTheme(layout.xaxis, theme),
        yaxis:plotlyAxisTheme(layout.yaxis, theme),
      };
    };
    const plotlyConfig = (config = {}) => ({
      // A Dashboard is a scrolling document first.  Plotly must not consume a
      // wheel gesture unless the author explicitly opts into chart zooming.
      responsive:true,
      displaylogo:false,
      showSendToCloud:false,
      scrollZoom:false,
      ...config,
    });
    const plotlyRestoreSelectionIcon = {
      width:24,
      height:24,
      path:'M20 12a8 8 0 1 1-2.34-5.66L20 8V2l-2.2 2.2A10 10 0 1 0 22 12h-2z',
    };
    const managedPlotlyDescriptor = (descriptor, renderContext) => {
      const sourceConfig = descriptor.config || {};
      const restoreButton = {
        name:'Restore default selection',
        icon:plotlyRestoreSelectionIcon,
        click:() => requestAnimationFrame(() => {
          runtime.metrics.renderers.interactions += 1;
          renderContext.controlBinding?.emit('reset');
        }),
      };
      const defaultModeBar = renderContext.controlBinding
        ? [['select2d', 'lasso2d', restoreButton]]
        : undefined;
      const hasExplicitModeBar = Object.prototype.hasOwnProperty.call(
        sourceConfig, 'modeBarButtons'
      );
      return {
        ...descriptor,
        config:{
          ...sourceConfig,
          displayModeBar:sourceConfig.displayModeBar
            ?? Boolean(renderContext.controlBinding),
          ...(hasExplicitModeBar || !defaultModeBar ? {} : {
            modeBarButtons:defaultModeBar,
          }),
        },
      };
    };
    const chartService = Object.freeze({
      plotly:Object.freeze({
        async mount(host, specification = {}, root = host?.closest?.('.dv-view')) {
          if (!global.Plotly) throw new Error('Plotly.js is not loaded');
          const config = plotlyConfig(specification.config || {});
          releaseWheelAtBoundary(
            host,
            () => host?._context?.scrollZoom !== true,
            true,
          );
          await global.Plotly.newPlot(
            host,
            specification.data || [],
            plotlyTheme(root, specification.layout || {}),
            config,
          );
          const state = {node:host, specification, observer:null};
          state.observer = new ResizeObserver(() => {
            runtime.metrics.renderers.resizes += 1;
            global.Plotly?.Plots?.resize?.(host);
          });
          state.observer.observe(host);
          return state;
        },
        async update(state, specification = {}, root = state?.node?.closest?.('.dv-view')) {
          if (!state?.node) throw new Error('Plotly chart state is missing its host');
          await global.Plotly.react(
            state.node,
            specification.data || [],
            plotlyTheme(root, specification.layout || {}),
            plotlyConfig(specification.config || {}),
          );
          state.specification = specification;
          return state;
        },
        resize(state) {
          if (!state?.node) return;
          runtime.metrics.renderers.resizes += 1;
          global.Plotly?.Plots?.resize?.(state.node);
        },
        dispose(state) {
          state?.observer?.disconnect?.();
          if (state?.node) global.Plotly?.purge?.(state.node);
        },
      }),
    });
    global.dataviz.charts = chartService;
    const formatTableValue = (value, rule) => {
      if (value == null) return '';
      if (!rule) return String(value);
      if (rule === 'number') return new Intl.NumberFormat().format(Number(value));
      if (rule === 'percent') return new Intl.NumberFormat(undefined, {
        style:'percent', maximumFractionDigits:2,
      }).format(Number(value));
      if (rule === 'date') return new Intl.DateTimeFormat(undefined, {
        dateStyle:'medium',
      }).format(new Date(value));
      if (rule === 'datetime') return new Intl.DateTimeFormat(undefined, {
        dateStyle:'medium', timeStyle:'short',
      }).format(new Date(value));
      if (rule === 'currency') return new Intl.NumberFormat(undefined, {
        style:'currency', currency:'CNY',
      }).format(Number(value));
      if (typeof rule === 'object') {
        if (rule.type === 'date' || rule.type === 'datetime') {
          return new Intl.DateTimeFormat(rule.locale, rule.options || {}).format(new Date(value));
        }
        return new Intl.NumberFormat(rule.locale, rule.options || rule).format(Number(value));
      }
      return String(value);
    };
    let managedTableFeatures = null;
    const tanstackCore = () => {
      const core = global.datavizTanStackTable;
      if (!core?.constructTable || !core?.tableFeatures) {
        throw new Error('TanStack Table Core is not loaded');
      }
      const expected = String(global.dataviz.runtime_versions?.tanstack_table || '');
      if (expected && expected !== String(core.version || '')) {
        throw new Error(
          `TanStack Table Runtime version mismatch: expected ${expected}, loaded ${core.version}`
        );
      }
      return core;
    };
    const defaultTableFeatures = () => {
      if (managedTableFeatures) return managedTableFeatures;
      const core = tanstackCore();
      managedTableFeatures = core.tableFeatures({
        coreReactivityFeature:core.storeReactivityBindings(),
        columnFilteringFeature:core.columnFilteringFeature,
        globalFilteringFeature:core.globalFilteringFeature,
        filteredRowModel:core.createFilteredRowModel(),
        filterFns:core.filterFns,
        rowSortingFeature:core.rowSortingFeature,
        sortedRowModel:core.createSortedRowModel(),
        sortFns:core.sortFns,
        rowExpandingFeature:core.rowExpandingFeature,
        expandedRowModel:core.createExpandedRowModel(),
        rowPaginationFeature:core.rowPaginationFeature,
        paginatedRowModel:core.createPaginatedRowModel(),
        columnOrderingFeature:core.columnOrderingFeature,
        columnPinningFeature:core.columnPinningFeature,
        columnSizingFeature:core.columnSizingFeature,
        columnVisibilityFeature:core.columnVisibilityFeature,
      });
      return managedTableFeatures;
    };
    const appendTableRenderable = (host, value) => {
      if (value == null || value === false) return;
      if (value instanceof Node) {
        host.append(value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(item => appendTableRenderable(host, item));
        return;
      }
      host.append(document.createTextNode(String(value)));
    };
    const tableColumnNames = specification => {
      const rows = specification.rows || specification.data || [];
      const columns = specification.columns || [];
      if (columns.length && columns.every(column => typeof column === 'string')) return columns;
      return Object.keys(rows[0] || {});
    };
    const inferTableAlign = (rows, column, configured) => {
      if (configured) return configured;
      const value = rows.find(row => row?.[column] != null)?.[column];
      return typeof value === 'number' ? 'right' : 'left';
    };
    const normalizeInitialSorting = value => {
      const values = Array.isArray(value) ? value : value ? [value] : [];
      return values.map(item => {
        if (typeof item === 'string') {
          return {id:item.startsWith('-') ? item.slice(1) : item, desc:item.startsWith('-')};
        }
        return {id:String(item.id || item.column || ''), desc:Boolean(item.desc)};
      }).filter(item => item.id);
    };
    const normalizeColumnPinning = options => {
      const configured = options.pinned_columns || options.pinning || {};
      if (Array.isArray(configured)) return {start:configured, end:[]};
      return {
        start:[...(configured.start || configured.left || [])],
        end:[...(configured.end || configured.right || [])],
      };
    };
    const tableColumnDefinitions = (specification, rows, options) => {
      if (Array.isArray(specification.columnDefs)) return specification.columnDefs;
      if (
        Array.isArray(specification.columns)
        && specification.columns.length
        && specification.columns.every(column => typeof column === 'object')
      ) return specification.columns;
      return tableColumnNames(specification).map(column => {
        const configuredWidth = Number(options.widths?.[column]);
        return {
          id:column,
          accessorFn:row => row?.[column],
          header:options.labels?.[column] || column,
          cell:cell => formatTableValue(cell.getValue(), options.formats?.[column]),
          enableSorting:options.sortable !== false,
          ...(Number.isFinite(configuredWidth) && configuredWidth > 0
            ? {size:configuredWidth}
            : {}),
          meta:{
            datavizColumn:column,
            datavizAlign:inferTableAlign(rows, column, options.align?.[column]),
            datavizWrap:Boolean(options.wrap || options.wrap_columns?.includes?.(column)),
          },
        };
      });
    };
    const tablePreparation = specification => {
      const rows = specification.rows || specification.data || [];
      const options = specification.options || {};
      const displayLimit = Number(specification.limit) > 0
        ? Number(specification.limit)
        : 100;
      const configuredPageSize = Number(options.page_size);
      const pageSize = Number.isFinite(configuredPageSize) && configuredPageSize > 0
        ? Math.floor(configuredPageSize)
        : displayLimit;
      const columns = tableColumnDefinitions(specification, rows, options);
      const columnNames = columns.map(column => String(
        column.id || column.accessorKey || column.meta?.datavizColumn || ''
      )).filter(Boolean);
      const hidden = new Set(options.hidden_columns || []);
      const columnVisibility = Object.fromEntries(columnNames.map(column => [
        column,
        !hidden.has(column),
      ]));
      const configuredOrder = options.column_order || [];
      return {
        rows,
        options,
        columns,
        pageSize,
        paginationEnabled:Number.isFinite(configuredPageSize) && configuredPageSize > 0,
        initialState:{
          sorting:normalizeInitialSorting(options.initial_sort),
          globalFilter:String(options.initial_search || ''),
          pagination:{pageIndex:0, pageSize},
          columnVisibility,
          columnOrder:configuredOrder.length ? [...configuredOrder] : columnNames,
          columnPinning:normalizeColumnPinning(options),
        },
        configurationKey:JSON.stringify({
          columns:columnNames,
          hidden:[...hidden],
          order:configuredOrder,
          pinning:normalizeColumnPinning(options),
          pageSize,
          sortable:options.sortable !== false,
        }),
      };
    };
    const applyTableCellPresentation = (node, column, options) => {
      const meta = column.columnDef.meta || {};
      const columnName = meta.datavizColumn || column.id;
      node.dataset.column = columnName;
      node.dataset.align = meta.datavizAlign || options.align?.[columnName] || 'left';
      if (meta.datavizWrap) node.dataset.wrap = 'true';
      const pinned = column.getIsPinned?.();
      if (column.columnDef.size != null || pinned) {
        node.style.width = `${column.getSize()}px`;
        node.style.minWidth = `${column.getSize()}px`;
        if (pinned) node.style.maxWidth = `${column.getSize()}px`;
      }
      if (!pinned) return;
      node.dataset.pinned = pinned;
      const offset = pinned === 'start'
        ? column.getStart?.('start')
        : column.getAfter?.('end');
      node.style[pinned === 'start' ? 'left' : 'right'] = `${Number(offset || 0)}px`;
    };
    const tableMeta = (state, filteredCount, visibleCount) => {
      const meta = document.createElement('div');
      meta.className = 'dv-table-meta';
      const strong = document.createElement('strong');
      strong.textContent = String(filteredCount);
      const label = document.createElement('span');
      const total = state.preparation.rows.length;
      label.textContent = `${filteredCount === total ? 'rows' : `of ${total} rows`}${
        visibleCount < filteredCount ? ` · showing ${visibleCount}` : ''
      }`;
      meta.append(strong, label);
      return meta;
    };
    const renderTanStackTable = state => {
      if (state.disposed) return;
      const {host, table, preparation} = state;
      const {options} = preparation;
      const activeSearch = document.activeElement?.classList?.contains('dv-table-search');
      const searchSelection = activeSearch
        ? [document.activeElement.selectionStart, document.activeElement.selectionEnd]
        : null;
      const fragment = document.createDocumentFragment();
      const filteredRows = table.getPrePaginatedRowModel().rows;
      const renderedRows = table.getRowModel().rows;
      if (options.searchable === true || options.show_count === true) {
        const toolbar = document.createElement('div');
        toolbar.className = 'dv-table-toolbar';
        if (options.searchable === true) {
          const search = document.createElement('label');
          search.className = 'dv-table-search-field';
          const searchIcon = document.createElement('span');
          searchIcon.className = 'dv-table-search-icon';
          searchIcon.setAttribute('aria-hidden', 'true');
          const input = document.createElement('input');
          input.className = 'dv-table-search';
          input.type = 'search';
          input.placeholder = options.search_placeholder || 'Search rows';
          input.setAttribute('aria-label', options.search_label || 'Search table rows');
          input.value = String(table.store.state.globalFilter || '');
          let composing = false;
          input.addEventListener('compositionstart', () => { composing = true; });
          input.addEventListener('compositionend', event => {
            composing = false;
            table.setGlobalFilter(event.currentTarget.value);
          });
          input.addEventListener('input', event => {
            if (composing || event.isComposing) return;
            table.setGlobalFilter(event.currentTarget.value);
          });
          search.append(searchIcon, input);
          toolbar.append(search);
        }
        if (options.show_count === true) {
          toolbar.append(tableMeta(state, filteredRows.length, renderedRows.length));
        }
        fragment.append(toolbar);
      }
      if (!preparation.rows.length || !filteredRows.length) {
        const empty = document.createElement('div');
        empty.className = 'dv-table-empty';
        empty.textContent = !preparation.rows.length
          ? options.empty_text || 'No rows match the current selections.'
          : options.no_results_text || 'No rows match this search.';
        fragment.append(empty);
        host.replaceChildren(fragment);
        if (activeSearch) {
          const search = host.querySelector('.dv-table-search');
          search?.focus({preventScroll:true});
          if (searchSelection) search?.setSelectionRange?.(...searchSelection);
        }
        return;
      }
      const wrap = document.createElement('div');
      wrap.className = 'dv-table-wrap';
      wrap.dataset.tanstackTableVersion = tanstackCore().version;
      const tableNode = document.createElement('table');
      tableNode.className = `dv-table${options.striped === false ? '' : ' dv-table--striped'}${
        options.compact ? ' dv-table--compact' : ''
      }${options.wrap ? ' dv-table--wrap' : ''}`;
      if (options.layout === 'fixed') tableNode.style.tableLayout = 'fixed';
      const thead = tableNode.createTHead();
      table.getHeaderGroups().forEach(headerGroup => {
        const row = thead.insertRow();
        headerGroup.headers.forEach(header => {
          if (header.rowSpan === 0) return;
          const cell = document.createElement('th');
          cell.scope = header.subHeaders?.length ? 'colgroup' : 'col';
          cell.colSpan = header.colSpan;
          if (header.rowSpan > 1) cell.rowSpan = header.rowSpan;
          applyTableCellPresentation(cell, header.column, options);
          const sorted = header.column.getIsSorted?.();
          const canSort = !header.isPlaceholder && header.column.getCanSort?.();
          if (canSort) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'dv-table-sort';
            button.dataset.sorted = sorted || 'none';
            const label = document.createElement('span');
            appendTableRenderable(label, tanstackCore().FlexRender({header}));
            const indicator = document.createElement('span');
            indicator.className = 'dv-table-sort-indicator';
            indicator.setAttribute('aria-hidden', 'true');
            indicator.textContent = sorted === 'asc' ? '↑' : sorted === 'desc' ? '↓' : '↕';
            button.append(label, indicator);
            button.addEventListener('click', header.column.getToggleSortingHandler());
            cell.setAttribute(
              'aria-sort',
              sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none',
            );
            cell.append(button);
          } else if (!header.isPlaceholder) {
            appendTableRenderable(cell, tanstackCore().FlexRender({header}));
          }
          row.append(cell);
        });
      });
      const tbody = tableNode.createTBody();
      const binding = state.renderContext?.controlBinding;
      const selected = new Set(
        (binding?.state?.values || []).map(value => JSON.stringify(value))
      );
      renderedRows.forEach(row => {
        const rowNode = tbody.insertRow();
        rowNode.dataset.rowIndex = String(row.index);
        if (binding) {
          const value = global.dataviz.controlActions.value(binding, row.original);
          const active = selected.has(JSON.stringify(value));
          rowNode.classList.toggle('is-selected', active);
          rowNode.setAttribute('aria-selected', String(active));
          rowNode.tabIndex = 0;
          const select = () => {
            runtime.metrics.renderers.interactions += 1;
            binding.emit('select', row.original);
          };
          rowNode.addEventListener('click', select);
          rowNode.addEventListener('keydown', event => {
            if (!['Enter', ' '].includes(event.key)) return;
            event.preventDefault();
            select();
          });
        }
        row.getVisibleCells().forEach(cell => {
          const cellNode = rowNode.insertCell();
          applyTableCellPresentation(cellNode, cell.column, options);
          const rendered = tanstackCore().FlexRender({cell});
          appendTableRenderable(
            cellNode,
            rendered == null ? cell.renderValue?.() : rendered,
          );
        });
      });
      const hasFooter = table.getFooterGroups().some(group => group.headers.some(
        header => header.column.columnDef.footer != null
      ));
      if (hasFooter) {
        const tfoot = tableNode.createTFoot();
        table.getFooterGroups().forEach(footerGroup => {
          const row = tfoot.insertRow();
          footerGroup.headers.forEach(header => {
            const cell = row.insertCell();
            cell.colSpan = header.colSpan;
            applyTableCellPresentation(cell, header.column, options);
            appendTableRenderable(cell, tanstackCore().FlexRender({footer:header}));
          });
        });
      }
      wrap.append(tableNode);
      releaseWheelAtBoundary(wrap);
      fragment.append(wrap);
      if (preparation.paginationEnabled && table.getPageCount() > 1) {
        const pagination = document.createElement('nav');
        pagination.className = 'dv-table-pagination';
        pagination.setAttribute('aria-label', options.pagination_label || 'Table pages');
        const previous = document.createElement('button');
        previous.type = 'button';
        previous.className = 'dv-table-page-button';
        previous.textContent = '‹';
        previous.setAttribute('aria-label', 'Previous page');
        previous.disabled = !table.getCanPreviousPage();
        previous.addEventListener('click', () => table.previousPage());
        const status = document.createElement('span');
        const pageIndex = table.store.state.pagination?.pageIndex || 0;
        status.className = 'dv-table-page-status';
        status.textContent = `${pageIndex + 1} / ${table.getPageCount()}`;
        const next = document.createElement('button');
        next.type = 'button';
        next.className = 'dv-table-page-button';
        next.textContent = '›';
        next.setAttribute('aria-label', 'Next page');
        next.disabled = !table.getCanNextPage();
        next.addEventListener('click', () => table.nextPage());
        pagination.append(previous, status, next);
        fragment.append(pagination);
      }
      host.replaceChildren(fragment);
      if (activeSearch) {
        const search = host.querySelector('.dv-table-search');
        search?.focus({preventScroll:true});
        if (searchSelection) search?.setSelectionRange?.(...searchSelection);
      }
    };
    const mountTanStackTable = (host, specification = {}, renderContext = null) => {
      const core = tanstackCore();
      const preparation = tablePreparation(specification);
      const table = core.constructTable({
        features:defaultTableFeatures(),
        data:preparation.rows,
        columns:preparation.columns,
        initialState:preparation.initialState,
        enableSorting:preparation.options.sortable !== false,
        sortDescFirst:Boolean(preparation.options.sort_desc_first),
        globalFilterFn:preparation.options.global_filter_fn || 'auto',
        getSubRows:specification.getSubRows,
      });
      const state = {
        host,
        table,
        preparation,
        specification,
        renderContext,
        subscription:null,
        disposed:false,
      };
      state.subscription = table.store.subscribe(() => renderTanStackTable(state));
      renderTanStackTable(state);
      return state;
    };
    const updateTanStackTable = (state, specification = {}, renderContext = null) => {
      if (!state?.table || state.disposed) {
        throw new Error('TanStack Table state is missing its instance');
      }
      const preparation = tablePreparation(specification);
      const configurationChanged = (
        preparation.configurationKey !== state.preparation.configurationKey
      );
      state.specification = specification;
      state.renderContext = renderContext || state.renderContext;
      state.preparation = preparation;
      state.table.setOptions(previous => ({
        ...previous,
        data:preparation.rows,
        columns:preparation.columns,
        enableSorting:preparation.options.sortable !== false,
        sortDescFirst:Boolean(preparation.options.sort_desc_first),
        globalFilterFn:preparation.options.global_filter_fn || 'auto',
        getSubRows:specification.getSubRows,
      }));
      if (configurationChanged) {
        state.table.setColumnVisibility(preparation.initialState.columnVisibility);
        state.table.setColumnOrder(preparation.initialState.columnOrder);
        state.table.setColumnPinning(preparation.initialState.columnPinning);
        state.table.setPageSize(preparation.pageSize);
      }
      const pageCount = Math.max(1, state.table.getPageCount());
      const pageIndex = state.table.store.state.pagination?.pageIndex || 0;
      if (pageIndex >= pageCount) state.table.setPageIndex(pageCount - 1);
      renderTanStackTable(state);
      return state;
    };
    const disposeTanStackTable = state => {
      if (!state || state.disposed) return;
      state.disposed = true;
      state.subscription?.unsubscribe?.();
      state.subscription = null;
      state.host?.replaceChildren();
    };
    const tableService = Object.freeze({
      tanstack:Object.freeze({
        version:'9.2.4',
        get core() { return tanstackCore(); },
        createFeatures:features => tanstackCore().tableFeatures({
          ...defaultTableFeatures(),
          ...(features || {}),
        }),
        mount:mountTanStackTable,
        update:updateTanStackTable,
        resize:state => renderTanStackTable(state),
        dispose:disposeTanStackTable,
      }),
    });
    global.dataviz.tables = tableService;
    const awaitPerspectiveOperation = async (state, stage, operation) => {
      state.stage = stage;
      let timeout;
      try {
        return await Promise.race([
          Promise.resolve(operation),
          new Promise((_, reject) => {
            timeout = setTimeout(() => {
              const error = new Error(
                `Perspective ${stage} did not settle within ${perspectiveOperationTimeoutMs}ms`
              );
              error.code = 'renderer_lifecycle_timeout';
              reject(error);
            }, perspectiveOperationTimeoutMs);
          }),
        ]);
      } finally {
        clearTimeout(timeout);
      }
    };
    const flushPerspective = async state => {
      if (typeof state.viewer?.flush === 'function') {
        await awaitPerspectiveOperation(state, 'flush', state.viewer.flush());
      } else if (typeof state.viewer?.resize === 'function') {
        await awaitPerspectiveOperation(state, 'resize', state.viewer.resize());
      }
      runtime.metrics.perspective.flushed += 1;
    };
    const disposePerspective = state => {
      if (!state) return;
      tableService.tanstack.dispose(state.fallbackTable);
      state.fallbackTable = null;
      if (state.disposed) return;
      state.disposed = true;
      state.observer?.disconnect();
      state.pending = Promise.resolve(state.pending).catch(() => {}).then(async () => {
        const viewer = state.viewer;
        const table = state.table;
        const worker = state.worker;
        state.viewer = null;
        state.table = null;
        state.worker = null;
        try {
          if (typeof viewer?.delete === 'function') {
            await awaitPerspectiveOperation(state, 'viewer dispose', viewer.delete());
          }
        } finally {
          try {
            if (typeof table?.delete === 'function') {
              await awaitPerspectiveOperation(state, 'table dispose', table.delete());
            }
          } finally {
            worker?.terminate?.();
            if (state.countedCreated) runtime.metrics.perspective.disposed += 1;
          }
        }
      }).catch(error => {
        state.worker?.terminate?.();
        state.worker = null;
        console.warn('[dataviz:perspective:dispose]', error);
      });
    };
    const createPerspective = (renderContext, descriptor) => {
      const {key, root, body} = renderContext;
      const rows = descriptor.rows || [];
      const columns = descriptor.columns || Object.keys(rows[0] || {});
      root?.classList.add('dv-view--perspective');
      const loading = document.createElement('div');
      loading.className = 'dv-perspective-loading';
      loading.innerHTML = '<span></span><strong>Preparing analysis table</strong><small>sort · filter · pivot · chart</small>';
      body.replaceChildren(loading);
      const state = {
        worker:null,
        table:null,
        viewer:null,
        observer:null,
        fallbackTable:null,
        latestRows:rows,
        latestDescriptor:descriptor,
        mode:'loading',
        stage:'bootstrap',
        disposed:false,
        countedCreated:false,
        pending:Promise.resolve(),
      };
      state.pending = (async () => {
        if (!global.datavizPerspectiveReady) {
          throw new Error('Perspective is not loaded; add perspective to canvas.client_libraries');
        }
        if (!state.latestRows.length) {
          state.fallbackTable = tableService.tanstack.mount(
            body,
            {...descriptor, rows:[], columns},
            renderContext,
          );
          state.mode = 'empty';
          applyStatus(root, 'empty', 'empty');
          return;
        }
        const perspectiveRuntime = await awaitPerspectiveOperation(
          state,
          'runtime load',
          global.datavizPerspectiveReady,
        );
        if (state.disposed) return;
        const expectedMajor = String(global.dataviz.runtime_versions?.perspective || '').split('.')[0];
        const actualMajor = String(perspectiveRuntime.version || '').split('.')[0];
        if (expectedMajor && actualMajor && expectedMajor !== actualMajor) {
          throw new Error(
            `Perspective Runtime version mismatch: expected ${expectedMajor}.x, loaded ${perspectiveRuntime.version}`
          );
        }
        if (typeof perspectiveRuntime.perspective?.worker !== 'function') {
          throw new Error('Perspective Client does not expose perspective.worker()');
        }
        const worker = await awaitPerspectiveOperation(
          state,
          'worker create',
          perspectiveRuntime.perspective.worker(),
        );
        if (state.disposed) {
          worker?.terminate?.();
          return;
        }
        if (typeof worker?.table !== 'function') {
          worker?.terminate?.();
          throw new Error('Perspective Worker does not expose table()');
        }
        state.worker = worker;
        const tableName = `dataviz_${String(key).replace(/[^A-Za-z0-9_]/g, '_')}_${++perspectiveSerial}`;
        const table = await awaitPerspectiveOperation(
          state,
          'table create',
          worker.table(state.latestRows, {name:tableName}),
        );
        if (state.disposed) {
          try {
            await awaitPerspectiveOperation(state, 'table dispose', table.delete?.());
          } finally {
            worker?.terminate?.();
          }
          return;
        }
        const viewer = document.createElement('perspective-viewer');
        if (
          typeof viewer.load !== 'function'
          || typeof viewer.restore !== 'function'
          || typeof viewer.flush !== 'function'
          || typeof viewer.delete !== 'function'
        ) {
          await table.delete?.();
          throw new Error(
            'Perspective Viewer API is incompatible; load(), restore(), flush() and delete() are required'
          );
        }
        viewer.className = 'dv-perspective';
        viewer.setAttribute('theme', descriptor.theme || 'Pro Light');
        releaseWheelAtBoundary(viewer);
        body.replaceChildren(viewer);
        state.table = table;
        state.viewer = viewer;
        await awaitPerspectiveOperation(state, 'viewer load', viewer.load(worker));
        await awaitPerspectiveOperation(state, 'viewer restore', viewer.restore({
          plugin:'Datagrid',
          columns,
          settings:false,
          ...(descriptor.config || descriptor.perspective || {}),
          table:tableName,
        }));
        await flushPerspective(state);
        if (state.latestRows !== rows) {
          await awaitPerspectiveOperation(
            state,
            'table update',
            table.replace(state.latestRows),
          );
          await flushPerspective(state);
        }
        state.observer = new ResizeObserver(() => {
          runtime.metrics.renderers.resizes += 1;
          viewer.resize?.();
        });
        state.observer.observe(body);
        state.mode = 'perspective';
        state.stage = 'ready';
        state.countedCreated = true;
        runtime.metrics.perspective.created += 1;
        applyStatus(root, 'ready', 'perspective');
      })().catch(error => {
        if (state.disposed) return;
        state.mode = 'fallback';
        state.stage = 'fallback';
        runtime.metrics.perspective.failed += 1;
        root?.classList.remove('dv-view--perspective');
        state.fallbackTable = tableService.tanstack.mount(
          body,
          {...descriptor, rows:state.latestRows, columns},
          renderContext,
        );
        applyStatus(root, 'ready', 'table fallback');
        const viewer = state.viewer;
        const table = state.table;
        const worker = state.worker;
        state.viewer = null;
        state.table = null;
        state.worker = null;
        let viewerDelete;
        try { viewerDelete = viewer?.delete?.(); } catch (_error) { viewerDelete = null; }
        Promise.resolve(viewerDelete).catch(() => {}).finally(() => {
          let tableDelete;
          try { tableDelete = table?.delete?.(); } catch (_error) { tableDelete = null; }
          Promise.resolve(tableDelete).catch(() => {}).finally(() => worker?.terminate?.());
        });
        console.warn(`[dataviz:${key}] Perspective unavailable; using basic table`, error);
      });
      return state;
    };
    const updatePerspective = (renderContext, descriptor, state) => {
      state.latestRows = descriptor.rows || [];
      state.latestDescriptor = descriptor;
      if (state.mode === 'empty' && state.latestRows.length) {
        disposePerspective(state);
        return createPerspective(renderContext, descriptor);
      }
      // Perspective's table.replace([]) / viewer.flush() path can wait for an
      // internal render timeout while leaving the previous pivot visible. An
      // explicit empty Selection is already a terminal result, so publish that
      // state synchronously and release the old viewer in the background. A
      // later non-empty update follows the existing Empty -> create lifecycle.
      if (!state.latestRows.length && ['loading', 'perspective'].includes(state.mode)) {
        const columns = descriptor.columns || [];
        state.mode = 'empty';
        renderContext.root?.classList.remove('dv-view--perspective');
        disposePerspective(state);
        state.fallbackTable = tableService.tanstack.mount(
          renderContext.body,
          {...descriptor, rows:[], columns},
          renderContext,
        );
        applyStatus(renderContext.root, 'empty', 'empty');
        runtime.metrics.perspective.updated += 1;
        return state;
      }
      if (state.mode === 'empty' || state.mode === 'fallback') {
        const columns = descriptor.columns || Object.keys(state.latestRows[0] || {});
        state.fallbackTable = state.fallbackTable
          ? tableService.tanstack.update(
            state.fallbackTable,
            {...descriptor, rows:state.latestRows, columns},
            renderContext,
          )
          : tableService.tanstack.mount(
            renderContext.body,
            {...descriptor, rows:state.latestRows, columns},
            renderContext,
          );
        applyStatus(
          renderContext.root,
          state.latestRows.length ? 'ready' : 'empty',
          state.mode === 'empty' ? 'empty' : 'table fallback',
        );
        return state;
      }
      state.pending = Promise.resolve(state.pending).then(async () => {
        if (state.disposed || !state.table) return;
        await awaitPerspectiveOperation(
          state,
          'table update',
          state.table.replace(state.latestRows),
        );
        await flushPerspective(state);
        runtime.metrics.perspective.updated += 1;
        applyStatus(renderContext.root, state.latestRows.length ? 'ready' : 'empty', 'perspective');
      }).catch(error => {
        if (state.disposed) return;
        runtime.metrics.perspective.failed += 1;
        applyStatus(renderContext.root, 'error', 'perspective error');
        console.error(`[dataviz:${renderContext.key}] Perspective update failed`, error);
      });
      return state;
    };
    const clearRoot = (root, key) => {
      const body = root?.querySelector('.dv-view-body');
      if (!root || !body) return {root, body};
      root.classList.remove('dv-view--table', 'dv-view--perspective');
      body.replaceChildren();
      return {root, body};
    };
    const disposeRenderer = (root, key) => {
      const mounted = states.get(key);
      if (!mounted) return;
      states.delete(key);
      runtime.metrics.renderers.disposes += 1;
      try {
        Promise.resolve(
          mounted.renderer.dispose?.(context(root, mounted.body, key), mounted.state)
        ).catch(error => console.error(`[dataviz:${key}] Renderer dispose failed`, error));
      } catch (error) {
        console.error(`[dataviz:${key}] Renderer dispose failed`, error);
      }
    };
    const terminal = (root, key, {status, title, message, modifier = status}) => {
      if (!root) return;
      disposeRenderer(root, key);
      const {body} = clearRoot(root, key);
      if (body) {
        const placeholder = document.createElement('div');
        placeholder.className = `dv-view-placeholder dv-view-placeholder--${modifier}`;
        const heading = document.createElement('strong');
        heading.textContent = title;
        const detail = document.createElement('span');
        detail.textContent = message || '';
        placeholder.append(heading, detail);
        body.append(placeholder);
      }
      applyStatus(root, status, status);
    };
    const waiting = (root, key, label = 'Waiting for data') => {
      if (!root) return;
      disposeRenderer(root, key);
      const {body} = clearRoot(root, key);
      if (body) {
        const placeholder = document.createElement('div');
        placeholder.className = 'dv-view-placeholder dv-view-placeholder--live';
        placeholder.innerHTML = '<span></span><strong>Waiting for this data branch</strong>';
        placeholder.title = label;
        body.append(placeholder);
      }
      applyStatus(root, 'loading', 'loading');
    };
    const empty = (root, key, message = 'No data matches the current state') => {
      runtime.metrics.renderers.empty += 1;
      terminal(root, key, {status:'empty', title:'No data', message});
    };
    const unavailable = (root, key, message) => terminal(root, key, {
      status:'unavailable', title:'Interactive computation unavailable', message,
    });
    const cancelled = (root, key, message) => terminal(root, key, {
      status:'cancelled', title:'Computation cancelled', message,
    });
    const clear = id => {
      const root = node(id);
      disposeRenderer(root, id);
      return clearRoot(root, id);
    };
    const rendererError = (key, type, phase, error) => ({
      code:'renderer_lifecycle_error',
      view_id:key,
      renderer:type,
      phase,
      message:error?.message || String(error),
      stack:error?.stack || null,
    });
    const showError = (root, key, type, phase, error) => {
      runtime.metrics.renderers.failed += 1;
      const detail = rendererError(key, type, phase, error);
      runtime.rendererErrors.set(key, detail);
      const mounted = states.get(key);
      if (mounted) disposeRenderer(mounted.root, key);
      const {body} = clearRoot(root, key);
      if (body) {
        const errorNode = document.createElement('div');
        errorNode.className = 'dv-view-error';
        errorNode.setAttribute('role', 'alert');
        errorNode.innerHTML = `<strong>${services.escape(detail.renderer)} · ${
          services.escape(detail.phase)
        }</strong><pre>${services.escape(detail.stack || detail.message)}</pre>`;
        body.append(errorNode);
      }
      if (root) root.dataset.rendererError = `${type}:${phase}`;
      applyStatus(root, 'error', 'renderer error');
      console.error(`[dataviz:${key}:${type}:${phase}]`, detail);
    };
    const renderInto = (root, key, producer) => {
      const previousStatus = root?.dataset.viewStatus || null;
      setRendererSignal(root, 'loading', {active:true});
      applyStatus(root, 'loading', 'rendering');
      if (root) {
        delete root.dataset.rendererError;
        root._datavizRenderGeneration = (root._datavizRenderGeneration || 0) + 1;
      }
      const generation = root?._datavizRenderGeneration || 0;
      let descriptor;
      try {
        descriptor = producer();
        if (descriptor == null) {
          empty(root, key);
          return null;
        }
        if (descriptor.empty === true) {
          empty(root, key, descriptor.emptyMessage);
          return descriptor;
        }
      } catch (error) {
        showError(root, key, 'descriptor', 'produce', error);
        return null;
      }
      const type = descriptor.type || 'text';
      const renderer = runtime.renderers.get(type);
      if (!renderer) {
        showError(root, key, type, 'lookup', new Error(`Unknown Renderer: ${type}`));
        return null;
      }
      const previous = root?._datavizRendererPending || Promise.resolve();
      const pending = Promise.resolve(previous).catch(() => {}).then(async () => {
        if (root?._datavizRenderGeneration !== generation) return;
        const started = performance.now();
        let phase = 'validate';
        try {
          await renderer.validate?.(descriptor);
          if (root?._datavizRenderGeneration !== generation) return;
          const mounted = states.get(key);
          if (mounted && mounted.type === type && mounted.root === root && renderer.update) {
            phase = 'update';
            mounted.state = await renderer.update(
              context(root, mounted.body, key, descriptor, generation),
              descriptor,
              mounted.state,
            ) ?? mounted.state;
            runtime.metrics.renderers.updates += 1;
          } else {
            if (mounted) disposeRenderer(mounted.root, key);
            const {body} = clearRoot(root, key);
            if (!body) throw new Error(`Unknown view: ${key}`);
            phase = 'mount';
            const state = await renderer.mount(
              context(root, body, key, descriptor, generation),
              descriptor,
            );
            if (root?._datavizRenderGeneration !== generation) {
              await renderer.dispose?.(context(root, body, key, descriptor, generation), state);
              return;
            }
            states.set(key, {type, renderer, state, root, body});
            runtime.metrics.renderers.mounts += 1;
            if (previousStatus === 'empty') runtime.metrics.renderers.restores += 1;
          }
          runtime.rendererErrors.delete(key);
          if (type !== 'perspective') applyStatus(root, 'ready', type);
        } catch (error) {
          if (root?._datavizRenderGeneration === generation) {
            showError(root, key, type, phase, error);
          }
        } finally {
          runtime.metrics.renderers.totalMs += performance.now() - started;
        }
      });
      if (root) root._datavizRendererPending = pending;
      return descriptor;
    };
    const syncPlotlyInteractions = (state, descriptor) => {
      const chartNode = state.node;
      if (state.controlActionFrame != null) {
        cancelAnimationFrame(state.controlActionFrame);
        state.controlActionFrame = null;
      }
      if (state.controlClickHandler) {
        chartNode.removeListener?.('plotly_click', state.controlClickHandler);
        state.controlClickHandler = null;
      }
      if (state.controlSelectedHandler) {
        chartNode.removeListener?.('plotly_selected', state.controlSelectedHandler);
        state.controlSelectedHandler = null;
      }
      if (state.controlDoubleClickHandler) {
        chartNode.removeListener?.('plotly_doubleclick', state.controlDoubleClickHandler);
        state.controlDoubleClickHandler = null;
      }
      if (!descriptor.controlBinding) return;
      state.controlClickHandler = event => {
        const datum = event?.points?.[0]?.customdata;
        if (datum === undefined) return;
        if (state.controlActionFrame != null) {
          cancelAnimationFrame(state.controlActionFrame);
          state.controlActionFrame = null;
        }
        runtime.metrics.renderers.interactions += 1;
        state.renderContext.controlBinding?.emit('select', {
          __datavizControlValue:datum,
        });
      };
      state.controlSelectedHandler = event => {
        const keyed = new Map((event?.points || []).map(point => ({
          __datavizControlValue:point.customdata,
        })).filter(item => item.__datavizControlValue !== undefined).map(item => [
          JSON.stringify(item.__datavizControlValue), item,
        ]));
        const data = [...keyed.values()];
        // Plotly can emit an empty selection after a point click or a
        // zero-area drag.  Clearing here races with plotly_click and makes a
        // successful click appear to have been ignored.  Explicit empty and
        // default restoration remain available through their own controls.
        if (!data.length) return;
        if (state.controlActionFrame != null) {
          cancelAnimationFrame(state.controlActionFrame);
        }
        runtime.metrics.renderers.interactions += 1;
        state.controlActionFrame = requestAnimationFrame(() => {
          state.controlActionFrame = null;
          state.renderContext.controlBinding?.emit('select_many', data);
        });
      };
      state.controlDoubleClickHandler = () => {
        if (state.controlActionFrame != null) {
          cancelAnimationFrame(state.controlActionFrame);
        }
        runtime.metrics.renderers.interactions += 1;
        state.controlActionFrame = requestAnimationFrame(() => {
          state.controlActionFrame = null;
          state.renderContext.controlBinding?.emit('reset');
        });
      };
      chartNode.on('plotly_click', state.controlClickHandler);
      chartNode.on('plotly_selected', state.controlSelectedHandler);
      chartNode.on('plotly_doubleclick', state.controlDoubleClickHandler);
    };

    runtime.registerRenderer('table', {
      validate:descriptor => {
        if (!Array.isArray(descriptor.rows || [])) throw new Error('Table renderer expects rows[]');
      },
      mount(renderContext, descriptor) {
        renderContext.root?.classList.add('dv-view--table');
        return tableService.tanstack.mount(
          renderContext.body,
          descriptor,
          renderContext,
        );
      },
      update(renderContext, descriptor, state) {
        return tableService.tanstack.update(state, descriptor, renderContext);
      },
      dispose(renderContext, state) {
        tableService.tanstack.dispose(state);
        renderContext.root?.classList.remove('dv-view--table');
      },
    });
    runtime.registerRenderer('plotly', {
      async mount(renderContext, descriptor) {
        const chartNode = document.createElement('div');
        chartNode.className = 'dv-chart dv-plotly';
        renderContext.body.append(chartNode);
        const specification = managedPlotlyDescriptor(descriptor, renderContext);
        const chart = await chartService.plotly.mount(
          chartNode, specification, renderContext.root
        );
        const state = {
          ...chart,
          descriptor,
          renderContext,
          controlClickHandler:null,
          controlSelectedHandler:null,
          controlDoubleClickHandler:null,
          controlActionFrame:null,
        };
        syncPlotlyInteractions(state, descriptor);
        return state;
      },
      async update(renderContext, descriptor, state) {
        state.descriptor = descriptor;
        state.renderContext = renderContext;
        await chartService.plotly.update(
          state, managedPlotlyDescriptor(descriptor, renderContext), renderContext.root
        );
        syncPlotlyInteractions(state, descriptor);
        return state;
      },
      dispose(_renderContext, state) {
        if (state.controlActionFrame != null) cancelAnimationFrame(state.controlActionFrame);
        chartService.plotly.dispose(state);
      },
    });
    runtime.registerRenderer('perspective', {
      mount: createPerspective,
      update: updatePerspective,
      dispose(renderContext, state) {
        disposePerspective(state);
        renderContext.root?.classList.remove('dv-view--perspective');
      },
    });
    runtime.registerRenderer('html', {
      mount(renderContext, descriptor) {
        renderContext.body.innerHTML = descriptor.html || '';
        return {};
      },
      update(renderContext, descriptor, state) {
        renderContext.body.innerHTML = descriptor.html || '';
        return state;
      },
      dispose() {},
    });
    runtime.registerRenderer('text', {
      mount(renderContext, descriptor) {
        const textNode = document.createElement('div');
        textNode.className = 'dv-prose';
        textNode.textContent = descriptor?.text ?? '';
        renderContext.body.append(textNode);
        return {node:textNode};
      },
      update(_renderContext, descriptor, state) {
        state.node.textContent = descriptor?.text ?? '';
        return state;
      },
      dispose() {},
    });

    const adapter = {
      protocol:'dataviz/runtime/v5',
      lifecycle:Object.freeze({
        hooks:Object.freeze(['validate', 'mount', 'update', 'dispose']),
        phases:Object.freeze([
          'mount', 'update', 'empty', 'restore',
          'interaction', 'resize', 'dispose', 'export',
        ]),
      }),
      states,
      node,
      setStatus:applyStatus,
      renderInto,
      render:(id, producer) => renderInto(node(id), id, producer),
      waiting,
      empty,
      unavailable,
      cancelled,
      clearRoot,
      disposeRenderer,
      releaseWheelAtBoundary,
      createPerspective,
      dispose() {
        if (disposed) return;
        disposed = true;
        states.forEach((mounted, key) => disposeRenderer(mounted.root, key));
      },
    };
    runtime.viewAdapter = adapter;
    global.dataviz.renderView = adapter.render;
    controller.registerViews(runtime);
    components.adapters = components.adapters || new Map();
    components.adapters.set('view.declarative', adapter);

    document.querySelectorAll('.dv-plotly[data-spec]').forEach(chartNode => {
      if (!global.Plotly) {
        chartNode.innerHTML = '<div class="dv-runtime-error">Plotly.js could not be loaded.</div>';
        return;
      }
      const rootNode = chartNode.closest('.dv-view');
      const body = chartNode.closest('.dv-view-body');
      const key = rootNode?.dataset.viewId;
      if (!rootNode || !body || !key) return;
      const spec = services.decodeSpec(chartNode);
      const renderContext = context(rootNode, body, key, spec);
      const pending = chartService.plotly.mount(
        chartNode, managedPlotlyDescriptor(spec, renderContext), rootNode
      ).then(chart => {
        const state = {
          ...chart,
          descriptor:spec,
          renderContext,
          controlClickHandler:null,
          controlSelectedHandler:null,
          controlDoubleClickHandler:null,
          controlActionFrame:null,
        };
        syncPlotlyInteractions(state, spec);
        states.set(key, {
          type:'plotly', renderer:runtime.renderers.get('plotly'), state, root:rootNode, body,
        });
        runtime.metrics.renderers.mounts += 1;
        return state;
      }).catch(error => showError(rootNode, key, 'plotly', 'mount', error));
      rootNode._datavizRendererPending = pending;
    });
    document.querySelectorAll('.dv-perspective-bootstrap').forEach((bootstrap, index) => {
      try {
        const payload = JSON.parse(new TextDecoder().decode(Uint8Array.from(
          atob(bootstrap.dataset.perspectivePayload),
          value => value.charCodeAt(0),
        )));
        const body = bootstrap.closest('.dv-view-body');
        const rootNode = bootstrap.closest('.dv-view');
        if (!body) return;
        const key = rootNode?.dataset.viewId || `artifact:${index}`;
        const renderContext = context(rootNode, body, key);
        const state = createPerspective(renderContext, {type:'perspective', ...payload});
        states.set(key, {
          type:'perspective',
          renderer:runtime.renderers.get('perspective'),
          state,
          root:rootNode,
          body,
        });
        runtime.metrics.renderers.mounts += 1;
        if (rootNode) rootNode._datavizRendererPending = state.pending;
      } catch (error) {
        bootstrap.textContent = `Interactive table failed: ${error.message}`;
      }
    });
  };
  install();
  global.addEventListener('dataviz:runtime-ready', install, {once:true});
})(window);
