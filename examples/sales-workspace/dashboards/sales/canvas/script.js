document.querySelectorAll('.dv-widget').forEach((node, index) => {
  node.animate(
    [{opacity: 0, transform: 'translateY(12px)'}, {opacity: 1, transform: 'translateY(0)'}],
    {duration: 420, delay: index * 90, fill: 'both', easing: 'cubic-bezier(.2,.7,.2,1)'}
  );
});

const selectedOrders = (state, viewId) => {
  const selections = state.getViewSelections(viewId);
  return state.data.source('orders')
    .where('region', 'in', selections.region || [])
    .where('revenue', '>=', Number(selections.min_revenue || 0));
};

const totalsBy = (frame, group, value) => frame
  .groupBy(group)
  .aggregate({[value]: {field: value, op: 'sum'}})
  .sort(group)
  .rows();

function revenueView(state) {
  const selections = state.getViewSelections('revenue');
  const actual = totalsBy(selectedOrders(state, 'revenue'), 'date', 'revenue');
  const forecast = totalsBy(
    state.data.source('forecast')
      .where('region', 'in', selections.region || [])
      .where('forecast_revenue', '>=', Number(selections.min_revenue || 0)),
    'date',
    'forecast_revenue',
  );
  return {
    type: 'plotly',
    data: [
      {x: actual.map(row => row.date), y: actual.map(row => row.revenue), name: 'Actual', mode: 'lines+markers'},
      {x: forecast.map(row => row.date), y: forecast.map(row => row.forecast_revenue), name: 'Forecast', mode: 'lines', line: {dash: 'dot'}},
    ],
    layout: {
      margin: {l: 42, r: 18, t: 22, b: 38}, paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: {family: 'DM Mono', color: '#17211d'}, legend: {orientation: 'h', y: 1.08},
      xaxis: {showgrid: false}, yaxis: {gridcolor: '#ded9cc'},
    },
  };
}

function targetView(state) {
  const selections = state.getViewSelections('target');
  const actual = new Map(totalsBy(selectedOrders(state, 'target'), 'region', 'revenue').map(row => [row.region, row.revenue]));
  const rows = state.data.source('targets').where('region', 'in', selections.region || []).rows();
  const values = rows.map(row => Math.round(((actual.get(row.region) || 0) / Number(row.target)) * 1000) / 10);
  return {
    type: 'echarts',
    options: {
      grid: {left: 48, right: 18, top: 18, bottom: 34}, tooltip: {trigger: 'axis', formatter: '{b}: {c}%'},
      xAxis: {type: 'value', max: 120, axisLabel: {formatter: '{value}%'}},
      yAxis: {type: 'category', data: rows.map(row => row.region)},
      series: [{type: 'bar', data: values, itemStyle: {color: '#e2592a'}, barWidth: 18}],
    },
  };
}

function distributionView(state) {
  const rows = totalsBy(selectedOrders(state, 'distribution'), 'region', 'orders').sort((a, b) => a.orders - b.orders);
  return {
    type: 'echarts',
    options: {
      grid: {left: 62, right: 30, top: 18, bottom: 28}, tooltip: {trigger: 'axis'},
      xAxis: {type: 'value', splitLine: {lineStyle: {color: '#ded9cc'}}},
      yAxis: {type: 'category', data: rows.map(row => row.region), axisTick: {show: false}},
      series: [{type: 'bar', data: rows.map(row => row.orders), itemStyle: {color: '#263d33'}, barWidth: 20, label: {show: true, position: 'right'}}],
    },
  };
}

function detailView(state) {
  const selections = state.getViewSelections('detail');
  const rows = state.data.source('orders')
    .where('region', 'in', selections.region || [])
    .where('orders', '>=', Number(selections.min_orders || 0))
    .derive({avg_order_value: row => Math.round((Number(row.revenue) / Number(row.orders)) * 100) / 100})
    .rows()
    .sort((a, b) => String(b.date).localeCompare(String(a.date)) || String(a.region).localeCompare(String(b.region)));
  return {type: 'table', rows, columns: ['date', 'region', 'revenue', 'orders', 'avg_order_value'], limit: 100};
}

window.datavizClient = {
  render(state) {
    if (!state.portable) return;
    state.renderView('revenue', () => revenueView(state));
    state.renderView('target', () => targetView(state));
    state.renderView('distribution', () => distributionView(state));
    state.renderView('detail', () => detailView(state));
    const regionLabel = document.querySelector('#active-regions');
    if (regionLabel) regionLabel.textContent = (state.getViewSelections('revenue').region || []).join(' / ') || 'All';
  },
};
