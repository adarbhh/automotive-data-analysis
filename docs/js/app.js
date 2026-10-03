/* Dashboard logic. All numbers come from docs/data/*.js, written by the scripts in src/. */

const D = window.DASHBOARD;

// ---------- Helpers ----------

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const COLORS = {
  series: ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5'].map(css),
  light: css('--series-light'),
  negative: css('--negative'),
  reference: css('--reference'),
  text: css('--text-secondary'),
  muted: css('--text-muted'),
  grid: css('--grid'),
  axis: css('--axis'),
  surface: css('--surface'),
};

const fmtInt = n => Math.round(n).toLocaleString('en-US');
const fmtUsd = n => '$' + Math.round(n).toLocaleString('en-US');
const fmtPct = (n, digits = 1) => n.toFixed(digits) + '%';
const fmtCompact = n => n >= 1e9 ? (n / 1e9).toFixed(2) + 'B'
  : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M'
  : n >= 1e3 ? (n / 1e3).toFixed(0) + 'K' : String(n);
const titleCase = s => s.replace(/\b[a-z]/g, c => c.toUpperCase());
const brandName = s => ({ bmw: 'BMW', gmc: 'GMC', ram: 'Ram', rover: 'Land Rover', mini: 'MINI', kia: 'Kia' }[s] || titleCase(s));
const el = id => document.getElementById(id);

function renderTiles(containerId, tiles) {
  el(containerId).innerHTML = tiles.map(t => `
    <div class="tile">
      <div class="tile-value">${t.value}</div>
      <div class="tile-label">${t.label}</div>
      ${t.detail ? `<div class="tile-detail">${t.detail}</div>` : ''}
    </div>`).join('');
}

// columns: [{ key, label, num, format }]
function renderTable(tableId, columns, rows) {
  const head = columns.map(c => `<th class="${c.num ? 'num' : ''}">${c.label}</th>`).join('');
  const body = rows.map(row => '<tr>' + columns.map(c => {
    const value = c.format ? c.format(row[c.key], row) : row[c.key];
    return `<td class="${c.num ? 'num' : ''} ${c.muted ? 'muted' : ''}">${value}</td>`;
  }).join('') + '</tr>').join('');
  el(tableId).innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
}

// ---------- Chart defaults ----------

Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.color = COLORS.text;
Chart.defaults.maintainAspectRatio = false;
Chart.defaults.animation.duration = 300;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.legend.position = 'top';
Chart.defaults.plugins.legend.align = 'start';
Chart.defaults.plugins.legend.labels.boxWidth = 12;
Chart.defaults.plugins.legend.labels.boxHeight = 12;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.boxPadding = 4;
Chart.defaults.elements.bar.borderRadius = 4;
Chart.defaults.elements.line.borderWidth = 2;
Chart.defaults.elements.line.tension = 0;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 5;

const gridScale = (extra = {}) => ({
  grid: { color: COLORS.grid, drawTicks: false },
  border: { display: false },
  ticks: { padding: 8 },
  ...extra,
});
const plainScale = (extra = {}) => ({
  grid: { display: false },
  border: { color: COLORS.axis },
  ...extra,
});
const axisTitle = text => ({ display: true, text, color: COLORS.muted });

// Horizontal bar chart: one series, categories on the y axis
function hBarChart(canvasId, labels, values, { color = COLORS.series[0], xTitle, tickFormat = fmtInt, tooltipFormat = fmtInt, max } = {}) {
  return new Chart(el(canvasId), {
    type: 'bar',
    data: { labels, datasets: [{ data: values, backgroundColor: color, maxBarThickness: 22 }] },
    options: {
      indexAxis: 'y',
      scales: {
        x: gridScale({ max, title: xTitle ? axisTitle(xTitle) : undefined, ticks: { padding: 8, callback: tickFormat } }),
        y: plainScale(),
      },
      plugins: { tooltip: { callbacks: { label: ctx => ' ' + tooltipFormat(ctx.parsed.x) } } },
    },
  });
}

// Line chart with a crosshair-style tooltip (hover anywhere on the x axis)
function lineChart(canvasId, labels, datasets, { yTitle, xTitle, yFormat = fmtInt, legend = false, xTicks } = {}) {
  return new Chart(el(canvasId), {
    type: 'line',
    data: { labels, datasets },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: plainScale({ title: xTitle ? axisTitle(xTitle) : undefined, ticks: { maxTicksLimit: xTicks || 13, maxRotation: 0 } }),
        y: gridScale({ beginAtZero: true, title: yTitle ? axisTitle(yTitle) : undefined, ticks: { padding: 8, callback: yFormat } }),
      },
      plugins: {
        legend: { display: legend },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}: ${yFormat(ctx.parsed.y)}` } },
      },
    },
  });
}

const lineSeries = (label, data, color, extra = {}) =>
  ({ label, data, borderColor: color, backgroundColor: color, ...extra });

// ---------- Tabs ----------

const built = {};

function showTab(name) {
  document.querySelectorAll('.tab').forEach(tab => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active);
  });
  document.querySelectorAll('.panel').forEach(panel => {
    const active = panel.id === 'tab-' + name;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  });
  // Charts are built the first time their tab is opened (a hidden canvas has no size)
  if (!built[name]) {
    BUILDERS[name]();
    built[name] = true;
  }
  history.replaceState(null, '', '#' + name);
}

document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => showTab(tab.dataset.tab)));

// ---------- Overview ----------

function buildOverview() {
  const c = D.cleaning, p = D.pricing, r = D.recalls, v = D.vin, t = D.telematics;
  const effects = p.model.effects;
  const age = effects.find(e => e.group === 'Vehicle age');
  const odo = effects.find(e => e.group === 'Odometer');
  const vinDup = c.audit.find(a => a.step.includes('duplicate VIN'));
  const repost = c.audit.find(a => a.step.includes('reposted'));
  const maxConflict = Math.max(...v.audit.map(a => a.conflict_pct));
  const fire = r.topics[0];
  const parkOutside = r.severity_validation.find(s => s.group.startsWith('Park'));
  const allText = r.severity_validation.find(s => s.group.startsWith('All'));
  const recalled = r.join_listings[r.join_listings.length - 1];
  const drive = v.audit.find(a => a.field === 'Drive type');

  renderTiles('overview-tiles', [
    { value: fmtInt(c.raw_rows), label: 'Used-car listings analysed', detail: `${fmtInt(c.clean_rows)} after cleaning` },
    { value: fmtInt(r.total_recalls), label: 'Safety recalls', detail: `${r.first_year} to January 2026` },
    { value: fmtInt(v.sample_size), label: 'VINs decoded and validated', detail: `${fmtPct(100 - v.failure_rate)} decoded successfully` },
    { value: fmtInt(t.rows), label: 'Telematics readings', detail: `${fmtInt(t.trips)} trips, ${t.devices} vehicles` },
  ]);

  el('overview-findings').innerHTML = [
    `<strong>More than a third of the raw listings are repeat postings.</strong> ${fmtPct(vinDup.pct_of_original)} of the rows were the same vehicle (same VIN) posted again, and another ${fmtPct(repost.pct_of_original)} were the same ad reposted without a VIN. Without de-duplication every price statistic would be weighted towards sellers who repost.`,
    `<strong>Age is the strongest price driver.</strong> Each extra year lowers the asking price by about ${fmtPct(Math.abs(age.pct_effect))}, and every 10,000 miles by about ${fmtPct(Math.abs(odo.pct_effect))}, holding body type, fuel, drive and brand segment fixed (R&sup2; = ${p.model.r2.toFixed(2)}).`,
    `<strong>Recall counts mostly measure size.</strong> RV and truck makers appear among the top recall filers, but ranked by vehicles affected the list is led by the large passenger-car groups.`,
    `<strong>Fire-related recalls rank as the most severe.</strong> "${fire.name}" recalls have the highest severity score. The keyword proxy scored ${fmtPct(parkOutside.share_scored_high, 0)} of NHTSA "park outside" recalls as high severity, against ${fmtPct(allText.share_scored_high)} of all recalls.`,
    `<strong>${fmtPct(recalled.pct_of_listings)} of the listed cars have at least one recall on record</strong> for their model and model year, so a yes/no recall flag says little. The number of recalls is the more useful feature.`,
    `<strong>Sellers are accurate, but leave gaps.</strong> Across ${fmtInt(v.sample_size)} decoded VINs the seller and the VIN disagreed in at most ${fmtPct(maxConflict)} of cases for any field, while the decoder filled the drive type for ${drive.gaps_filled} listings where it was missing.`,
  ].map(text => `<li>${text}</li>`).join('');

  const stages = [
    ['Clean', 'Missing values, validity rules and de-duplication with a row-by-row audit.', '01_clean_listings.py'],
    ['Price', 'EDA, feature engineering and a log-price regression.', '02_eda_pricing.py'],
    ['Recalls', 'Trends, topic model on recall text, severity proxy and join to listings.', '03_recalls_analysis.py'],
    ['VIN', 'NHTSA API decoding, enrichment coverage and validation rules.', '04_vin_enrichment.py'],
    ['Telematics', 'Sampling checks, data quality report and driving features.', '05_telematics.py'],
  ];
  el('overview-stages').innerHTML = stages.map(([title, text, file], i) => `
    <div class="stage">
      <div class="stage-num">Stage ${i + 1}</div>
      <div class="stage-title">${title}</div>
      <div class="stage-text">${text}</div>
      <code>${file}</code>
    </div>`).join('');
}

// ---------- Pricing ----------

function buildPricing() {
  const c = D.cleaning, p = D.pricing;

  renderTiles('pricing-tiles', [
    { value: fmtInt(p.listings), label: 'Clean listings', detail: `${fmtPct(c.clean_rows / c.raw_rows * 100)} of ${fmtInt(c.raw_rows)} raw rows` },
    { value: fmtUsd(p.median_price), label: 'Median asking price' },
    { value: p.median_age + ' years', label: 'Median vehicle age', detail: `at listing (${p.reference_year})` },
    { value: fmtInt(p.median_odometer) + ' mi', label: 'Median odometer' },
  ]);

  // Cleaning funnel
  const steps = c.audit.filter(a => a.rows_removed > 0);
  new Chart(el('chart-funnel'), {
    type: 'bar',
    data: {
      labels: steps.map(a => a.step.replace(/ \(.*\)/, '').replace('missing or outside', 'outside').replace('Same vehicle listed again', 'Duplicate VIN').replace('Same ad reposted without a VIN', 'Reposted ad, no VIN')),
      datasets: [{ data: steps.map(a => a.rows_removed), backgroundColor: COLORS.series[0], maxBarThickness: 22 }],
    },
    options: {
      indexAxis: 'y',
      scales: { x: gridScale({ ticks: { padding: 8, callback: fmtCompact } }), y: plainScale() },
      plugins: { tooltip: { callbacks: {
        title: items => steps[items[0].dataIndex].step,
        label: ctx => ` ${fmtInt(ctx.parsed.x)} rows removed (${fmtPct(steps[ctx.dataIndex].pct_of_original)} of raw)`,
        afterLabel: ctx => ` ${fmtInt(steps[ctx.dataIndex].rows_remaining)} rows remaining`,
      } } },
    },
  });
  el('funnel-note').textContent =
    `${fmtInt(c.raw_rows)} raw rows, ${fmtInt(c.raw_rows - c.clean_rows)} removed, ${fmtInt(c.clean_rows)} kept. ` +
    'Each row is counted under the first rule it breaks, so the steps add up.';

  // Price histogram (log-spaced bins)
  const edges = p.histogram.edges;
  new Chart(el('chart-hist'), {
    type: 'bar',
    data: {
      labels: p.histogram.counts.map((_, i) => edges[i]),
      datasets: [{ data: p.histogram.counts, backgroundColor: COLORS.series[0], borderRadius: 2, categoryPercentage: 1, barPercentage: 0.92 }],
    },
    options: {
      scales: {
        x: plainScale({ title: axisTitle('Asking price (log scale)'), ticks: { maxRotation: 0, autoSkip: false,
          callback: function (value, index) { return index % 5 === 0 ? '$' + fmtCompact(edges[index]) : ''; } } }),
        y: gridScale({ ticks: { padding: 8, callback: fmtCompact } }),
      },
      plugins: { tooltip: { callbacks: {
        title: items => `${fmtUsd(edges[items[0].dataIndex])} to ${fmtUsd(edges[items[0].dataIndex + 1])}`,
        label: ctx => ` ${fmtInt(ctx.parsed.y)} listings`,
      } } },
    },
  });

  // Depreciation curve with a brand selector
  const ages = Array.from({ length: 26 }, (_, i) => i);
  const curve = name => {
    const d = p.depreciation[name];
    return ages.map(a => { const i = d.vehicle_age.indexOf(a); return i === -1 ? null : d.median_price[i]; });
  };
  const select = el('select-brand');
  select.innerHTML = Object.keys(p.depreciation).map(b => `<option value="${b}">${b === 'All brands' ? b : brandName(b)}</option>`).join('');

  const depChart = lineChart('chart-depreciation', ages,
    [lineSeries('All brands', curve('All brands'), COLORS.series[0])],
    { yTitle: 'Median asking price', xTitle: 'Vehicle age (years)', yFormat: fmtUsd, xTicks: 26 });

  select.addEventListener('change', () => {
    const brand = select.value;
    // The selected brand is always drawn in blue; "All brands" stays as a gray reference line
    depChart.data.datasets = brand === 'All brands'
      ? [lineSeries('All brands', curve('All brands'), COLORS.series[0])]
      : [lineSeries(brandName(brand), curve(brand), COLORS.series[0], { spanGaps: true }),
         lineSeries('All brands', curve('All brands'), COLORS.reference, { borderDash: [5, 4] })];
    depChart.options.plugins.legend.display = brand !== 'All brands';
    depChart.update();
  });

  // Brands: interquartile range bar + median dot
  const brands = p.brands;
  new Chart(el('chart-brands'), {
    data: {
      labels: brands.map(b => brandName(b.manufacturer)),
      datasets: [
        { type: 'line', label: 'Median', data: brands.map(b => b.median_price), showLine: false,
          backgroundColor: COLORS.series[0], borderColor: COLORS.series[0], pointStyle: 'circle',
          pointRadius: 5, pointHoverRadius: 7, pointBackgroundColor: COLORS.series[0], pointBorderColor: COLORS.surface, pointBorderWidth: 2 },
        { type: 'bar', label: 'Middle 50%', data: brands.map(b => [b.q25, b.q75]), backgroundColor: COLORS.light, pointStyle: 'rect',
          borderSkipped: false, barThickness: 10 },
      ],
    },
    options: {
      indexAxis: 'y',
      interaction: { mode: 'index', axis: 'y', intersect: false },
      scales: {
        x: gridScale({ position: 'top', beginAtZero: true, ticks: { padding: 8, callback: fmtUsd } }),
        y: plainScale({ ticks: { autoSkip: false } }),
      },
      plugins: {
        legend: { display: true, labels: { usePointStyle: true } },
        tooltip: { callbacks: {
          label: ctx => ctx.dataset.type === 'bar'
            ? ` Middle 50%: ${fmtUsd(ctx.raw[0])} to ${fmtUsd(ctx.raw[1])}`
            : ` Median: ${fmtUsd(ctx.parsed.x)}`,
          footer: items => `${fmtInt(brands[items[0].dataIndex].listings)} listings, median age ${brands[items[0].dataIndex].median_age} years`,
        } },
      },
    },
  });

  // Feature importance
  const imp = p.model.importance;
  hBarChart('chart-importance', imp.map(i => i.feature_group), imp.map(i => i.r2_drop),
    { tickFormat: v => v.toFixed(2), tooltipFormat: v => `R² drops by ${v.toFixed(3)}` });
  el('model-note').innerHTML =
    `Linear regression on log(price), trained on ${fmtInt(p.model.train_rows)} listings and tested on ${fmtInt(p.model.test_rows)}. ` +
    `R&sup2; = ${p.model.r2.toFixed(2)}; the typical prediction is off by ${fmtPct(p.model.median_pct_error, 0)} of the asking price. ` +
    'Condition, trim level and options are not in the data, which limits the fit.';

  // Effects by feature group (diverging: blue above baseline, red below)
  const effects = p.model.effects;
  const groups = ['Body type', 'Fuel type', 'Drive type', 'Transmission', 'Brand segment', 'Vehicle model'];
  const effectSelect = el('select-effect');
  effectSelect.innerHTML = groups.map(g => `<option>${g}</option>`).join('');

  const effectRows = group => effects
    .filter(e => e.group === group && !e.label.startsWith('unknown') && !e.label.startsWith('other'))
    .sort((a, b) => b.pct_effect - a.pct_effect);

  let rows = effectRows(groups[0]);
  const effectChart = new Chart(el('chart-effects'), {
    type: 'bar',
    data: { labels: [], datasets: [{ data: [], maxBarThickness: 20 }] },
    options: {
      indexAxis: 'y',
      scales: {
        x: gridScale({ ticks: { padding: 8, callback: v => (v > 0 ? '+' : '') + v + '%' } }),
        y: plainScale({ ticks: { autoSkip: false } }),
      },
      plugins: { tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.x > 0 ? '+' : ''}${ctx.parsed.x.toFixed(1)}% vs baseline` } } },
    },
  });

  function updateEffects() {
    rows = effectRows(effectSelect.value);
    const baseline = rows[0].label.match(/\(vs (.*)\)/)[1];
    effectChart.data.labels = rows.map(e => e.label.replace(/ \(vs .*\)/, ''));
    effectChart.data.datasets[0].data = rows.map(e => e.pct_effect);
    effectChart.data.datasets[0].backgroundColor = rows.map(e => e.pct_effect >= 0 ? COLORS.series[0] : COLORS.negative);
    effectChart.update();
    el('effects-note').textContent = `Baseline: ${baseline}. ` +
      (effectSelect.value === 'Fuel type'
        ? 'The diesel premium is partly a truck effect: most diesel listings are heavy-duty pickups.'
        : effectSelect.value === 'Vehicle model'
          ? 'The 20 most listed models, compared with all other models.'
          : 'These are associations in asking prices, not causal effects.');
  }
  effectSelect.addEventListener('change', updateEffects);
  updateEffects();
}

// ---------- Recalls ----------

function buildRecalls() {
  const r = D.recalls;

  renderTiles('recalls-tiles', [
    { value: fmtInt(r.total_recalls), label: 'Recalls', detail: `${r.first_year} to ${r.export_date}` },
    { value: fmtInt(r.manufacturers), label: 'Manufacturers', detail: 'after name normalization' },
    { value: fmtCompact(r.units_affected), label: 'Vehicles and parts affected' },
    { value: fmtInt(r.recalls_with_text), label: 'Recalls with a consequence text', detail: 'used for the topic model' },
  ]);

  el('recalls-year-sub').textContent =
    `${r.first_year} to ${r.last_full_year}. 2026 is left out because the export covers only its first weeks.`;

  // Per year, with a manufacturer selector
  const select = el('select-mfr');
  const mfrs = Object.keys(r.per_year_by_manufacturer);
  select.innerHTML = '<option value="">All manufacturers</option>' + mfrs.map(m => `<option>${m}</option>`).join('');
  const yearChart = lineChart('chart-recalls-year', r.years,
    [lineSeries('All manufacturers', r.per_year, COLORS.series[0])], { yTitle: 'Recalls' });
  select.addEventListener('change', () => {
    const m = select.value;
    yearChart.data.datasets = [lineSeries(m || 'All manufacturers', m ? r.per_year_by_manufacturer[m] : r.per_year, COLORS.series[0])];
    yearChart.update();
  });

  // Exposure bias: the same 10 manufacturers ranked two ways
  const top = r.top_manufacturers;
  const short = name => name.replace(/,? (Inc\.|LLC|North America).*$/, '').replace(' North America', '');
  hBarChart('chart-mfr-recalls', top.map(m => short(m.manufacturer)), top.map(m => m.recalls));
  const byUnits = [...top].sort((a, b) => b.units_affected - a.units_affected);
  hBarChart('chart-mfr-units', byUnits.map(m => short(m.manufacturer)), byUnits.map(m => m.units_affected / 1e6),
    { tickFormat: v => v + 'M', tooltipFormat: v => v.toFixed(1) + ' million units' });

  // Components over time
  const comps = Object.keys(r.component_trends);
  lineChart('chart-components', r.years,
    comps.map((c, i) => lineSeries(titleCase(c.toLowerCase()), r.component_trends[c], COLORS.series[i])),
    { yTitle: 'Recalls', legend: true });
  el('components-note').textContent =
    `Electrical system recalls have grown the fastest since 2010. "Equipment" is NHTSA's catch-all category. ` +
    `${fmtPct(r.missing_component_pct)} of the recalls have no component recorded.`;

  // Topics and severity
  el('topics-sub').textContent =
    `${r.topics.length} topics from an NMF topic model on ${fmtInt(r.recalls_with_text)} consequence summaries, ranked by severity`;
  renderTable('table-topics', [
    { key: 'name', label: 'Failure mode' },
    { key: 'recalls', label: 'Recalls', num: true, format: fmtInt },
    { key: 'mean_severity', label: 'Mean severity (1-3)', num: true, format: v => `
        <div class="cell-bar">${v.toFixed(2)}
          <div class="cell-bar-track"><div class="cell-bar-fill" style="width:${(v - 1) / 2 * 100}%"></div></div>
        </div>` },
    { key: 'share_high', label: 'High severity', num: true, format: v => fmtPct(v) },
    { key: 'top_words', label: 'Top terms', muted: true, format: v => v.split(', ').slice(0, 5).join(', ') },
  ], r.topics);

  renderTiles('severity-tiles', r.severity_validation.map(s => ({
    value: fmtPct(s.share_scored_high, s.share_scored_high === 100 ? 0 : 1),
    label: 'scored high severity',
    detail: `${s.group.replace(' Advisory', ' advisory')} (${fmtInt(s.recalls)} recalls)`,
  })));

  // Join coverage
  const jl = r.join_listings;
  hBarChart('chart-join-listings',
    ['Manufacturer matched', 'Model name usable', 'Recall for make + year', 'Recall for model + year'],
    jl.map(j => j.pct_of_listings),
    { max: 100, tickFormat: v => v + '%', tooltipFormat: v => fmtPct(v) + ' of listings' });
  renderTable('table-join-recalls', [
    { key: 'join_quality', label: 'Recall side: best join level' },
    { key: 'recalls', label: 'Recalls', num: true, format: fmtInt },
    { key: 'pct_of_recalls', label: 'Share', num: true, format: v => fmtPct(v) },
  ], r.join_recalls);

  // Most listed models
  const models = r.top_models;
  new Chart(el('chart-top-models'), {
    type: 'bar',
    data: { labels: models.map(m => { const [make, model] = m.model_label.split(' '); return brandName(make) + ' ' + model.toUpperCase().replace(/^([A-Z])([A-Z]+)$/, (_, a, b) => a + b.toLowerCase()); }), datasets: [{ data: models.map(m => m.avg_recalls), backgroundColor: COLORS.series[0], maxBarThickness: 18 }] },
    options: {
      indexAxis: 'y',
      scales: { x: gridScale({ title: axisTitle('Average recalls per listing') }), y: plainScale({ ticks: { autoSkip: false } }) },
      plugins: { tooltip: { callbacks: {
        label: ctx => ` ${ctx.parsed.x.toFixed(1)} recalls per listing on average`,
        afterLabel: ctx => ` ${fmtPct(models[ctx.dataIndex].share_recalled)} of ${fmtInt(models[ctx.dataIndex].listings)} listings have at least one`,
      } } },
    },
  });
}

// ---------- VIN ----------

function buildVin() {
  const v = D.vin;

  renderTiles('vin-tiles', [
    { value: fmtPct(v.with_vin_pct), label: 'Listings that include a VIN', detail: `${fmtInt(v.malformed_vins)} malformed VINs found` },
    { value: fmtInt(v.sample_size), label: 'VINs sampled at random', detail: 'NHTSA vPIC batch API' },
    { value: fmtPct(v.decoded / v.sample_size * 100), label: 'Decoded successfully', detail: `${v.sample_size - v.decoded} failed` },
    { value: String(v.audit.reduce((sum, a) => sum + a.gaps_filled, 0)), label: 'Empty fields filled', detail: 'across make, drive and fuel' },
  ]);

  hBarChart('chart-vin-coverage', v.coverage.map(c => c.field), v.coverage.map(c => c.coverage_pct),
    { max: 100, tickFormat: x => x + '%', tooltipFormat: x => fmtPct(x) + ' of sampled VINs' });

  renderTable('table-vin-audit', [
    { key: 'field', label: 'Field' },
    { key: 'compared', label: 'Compared', num: true, format: fmtInt },
    { key: 'gaps_filled', label: 'Gaps filled', num: true, format: fmtInt },
    { key: 'conflicts', label: 'Conflicts', num: true, format: fmtInt },
    { key: 'conflict_pct', label: 'Conflict rate', num: true, format: x => fmtPct(x) },
  ], v.audit);

  // Drive type before / after enrichment
  const order = ['4wd', 'fwd', 'rwd', '2wd', 'unknown'];
  const drive = order.map(d => v.drive_before_after.find(row => row.drive === d));
  const names = { '4wd': '4WD / AWD', fwd: 'FWD', rwd: 'RWD', '2wd': '2WD (side unknown)', unknown: 'Unknown' };
  new Chart(el('chart-vin-drive'), {
    type: 'bar',
    data: {
      labels: drive.map(d => names[d.drive]),
      datasets: [
        { label: 'Before (seller input)', data: drive.map(d => d.listings_before), backgroundColor: COLORS.light, maxBarThickness: 36 },
        { label: 'After VIN enrichment', data: drive.map(d => d.listings_after), backgroundColor: COLORS.series[0], maxBarThickness: 36 },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { x: plainScale(), y: gridScale({ title: axisTitle('Listings in the sample') }) },
      plugins: {
        legend: { display: true },
        tooltip: { callbacks: {
          label: ctx => ` ${ctx.dataset.label}: ${fmtInt(ctx.parsed.y)} listings`,
          footer: items => {
            const d = drive[items[0].dataIndex];
            const before = d.median_price_before ? fmtUsd(d.median_price_before) : 'n/a';
            return `Median price: ${before} before, ${fmtUsd(d.median_price_after)} after`;
          },
        } },
      },
    },
  });
  const unknown = drive[4], fourWd = drive[0];
  el('vin-drive-note').textContent =
    `Unknown drive types fall from ${unknown.listings_before} to ${unknown.listings_after}. ` +
    `Most of them turn out to be 4WD / AWD (${fourWd.listings_before} to ${fourWd.listings_after}), ` +
    `and the median 4WD price stays close (${fmtUsd(fourWd.median_price_before)} to ${fmtUsd(fourWd.median_price_after)}), ` +
    'so the stage 2 conclusion that 4WD vehicles are priced higher holds after enrichment.';

  renderTable('table-vin-rules', [
    { key: 'rule', label: 'Rule' },
    { key: 'violations', label: 'Violations', num: true },
    { key: 'violation_pct', label: 'Share', num: true, format: x => fmtPct(x) },
  ], v.validation);

  renderTable('table-vin-taxonomy', [
    { key: 'error_type', label: 'Error type' },
    { key: 'category', label: 'Category' },
    { key: 'count', label: 'Count', num: true },
    { key: 'pct_of_sample', label: 'Share', num: true, format: x => fmtPct(x) },
  ], v.taxonomy);

  const reasons = { Keep: 'No issue found', Correct: 'Model year replaced by the VIN year', Flag: 'Make conflict, needs manual review', Drop: 'VIN could not be decoded' };
  renderTable('table-vin-decisions', [
    { key: 'action', label: 'Decision' },
    { key: 'action', label: 'Reason', muted: true, format: a => reasons[a] },
    { key: 'listings', label: 'Listings', num: true },
  ], v.decisions);
}

// ---------- Telematics ----------

function buildTelematics() {
  const t = D.telematics;

  renderTiles('telematics-tiles', [
    { value: fmtInt(t.rows), label: 'Sensor readings', detail: `${t.devices} vehicles` },
    { value: fmtInt(t.trips), label: 'Trips rebuilt from timestamps', detail: `the file's ${t.original_trip_ids} trip IDs were not reliable` },
    { value: fmtInt(t.total_distance_km) + ' km', label: 'Distance covered', detail: `median trip ${t.median_trip_min} minutes` },
    { value: fmtPct(t.nominal_rate_pct), label: 'Readings exactly 1 second apart', detail: 'nominal sampling rate 1 Hz' },
  ]);

  const trip = t.example_trip;
  el('trip-sub').textContent = `Speed and engine RPM of trip ${trip.trip_id} (one point every 5 seconds)`;
  const minuteLabels = trip.minutes.map(m => m.toFixed(1));
  const tripOptions = title => ({ yTitle: title, xTitle: 'Minutes from the start of the trip', xTicks: 12 });
  lineChart('chart-trip-speed', minuteLabels, [lineSeries('Speed (km/h)', trip.speed, COLORS.series[0])], tripOptions('Speed (km/h)'));
  lineChart('chart-trip-rpm', minuteLabels, [lineSeries('Engine RPM', trip.rpm, COLORS.series[1])], tripOptions('Engine RPM'));

  renderTable('table-quality', [
    { key: 'check', label: 'Check' },
    { key: 'rows', label: 'Rows', num: true, format: fmtInt },
    { key: 'pct_of_rows', label: 'Share', num: true, format: x => x.toFixed(2) + '%' },
  ], t.quality);
  const frozen = t.quality.find(q => q.check.startsWith('Accelerometer frozen'));
  el('quality-note').textContent =
    `The main issue is the accelerometer: ${fmtPct(frozen.pct_of_rows)} of the readings repeat the same value ` +
    'while the car is moving, so harsh events are computed from the speed signal instead.';

  const devices = t.devices_summary;
  new Chart(el('chart-harsh'), {
    type: 'bar',
    data: { labels: devices.map(d => 'Device ' + d.deviceID), datasets: [{ data: devices.map(d => d.harsh_events_per_100km), backgroundColor: COLORS.series[0], maxBarThickness: 36 }] },
    options: {
      scales: { x: plainScale(), y: gridScale({ title: axisTitle('Events per 100 km') }) },
      plugins: { tooltip: { callbacks: {
        label: ctx => ` ${ctx.parsed.y.toFixed(1)} events per 100 km`,
        afterLabel: ctx => ` ${devices[ctx.dataIndex].trips} trips, ${fmtInt(devices[ctx.dataIndex].distance_km)} km`,
      } } },
    },
  });
}

// ---------- Start ----------

const BUILDERS = { overview: buildOverview, pricing: buildPricing, recalls: buildRecalls, vin: buildVin, telematics: buildTelematics };

const startTab = location.hash.replace('#', '');
showTab(BUILDERS[startTab] ? startTab : 'overview');
