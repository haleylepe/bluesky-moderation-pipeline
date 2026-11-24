// Bluesky moderation dashboard. Reads data/dashboard.json, written by scripts/export_dashboard_data.py.
const C = { blue: '#0085FF', orange: '#eb6834', aqua: '#1baf7a', yellow: '#eda100',
  good: '#0ca30c', critical: '#d03b3b', grid: '#EEF1F5', tick: '#6E7F91' };
const CATS = [
  { key: 'share_toxic', name: 'Toxicity', color: C.blue },
  { key: 'share_insult', name: 'Insult', color: C.orange },
  { key: 'share_identity_attack', name: 'Identity attack', color: C.aqua },
  { key: 'share_threat', name: 'Threat', color: C.yellow },
];
const TASKS = [['extract_jetstream', 'Extract'], ['score_posts', 'Score'], ['dbt_run', 'dbt run'], ['dbt_test', 'dbt test']];

const pct = (v, d = 1) => `${(v * 100).toFixed(d)}%`;
const fmt = n => n.toLocaleString('en-US');
const dayLabel = s => new Date(s + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
Chart.defaults.font.size = 12;
Chart.defaults.color = C.tick;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.boxHeight = 8;
Chart.defaults.plugins.tooltip.backgroundColor = '#0B0F14';
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.maintainAspectRatio = false;

const axes = (yFmt, extra = {}) => ({
  x: { grid: { display: false }, border: { color: '#D4DBE2' } },
  y: { beginAtZero: true, grid: { color: C.grid }, border: { display: false }, ticks: { callback: yFmt, maxTicksLimit: 6 }, ...extra },
});

let DATA, charts = {};
const state = { range: 'all', agg: 'day', sort: 'toxicity' };

function chart(id, config) {
  charts[id]?.destroy();
  charts[id] = new Chart(document.getElementById(id), config);
}

function emptyState(el, title, body) {
  el.innerHTML = `<div class="empty"><strong>${title}</strong><span>${body}</span></div>`;
}

// Filter by date range, then roll days up to ISO weeks (weighted by posts scored) if asked.
function series() {
  let days = DATA.daily;
  if (state.range !== 'all') days = days.slice(-Number(state.range));
  if (state.agg === 'day') return days.map(d => ({ ...d, label: dayLabel(d.day) }));
  const weeks = new Map();
  for (const d of days) {
    const dt = new Date(d.day + 'T00:00:00Z');
    dt.setUTCDate(dt.getUTCDate() - ((dt.getUTCDay() + 6) % 7));
    const k = dt.toISOString().slice(0, 10);
    if (!weeks.has(k)) weeks.set(k, []);
    weeks.get(k).push(d);
  }
  return [...weeks].map(([k, ds]) => {
    const n = ds.reduce((s, d) => s + d.posts_scored, 0);
    const w = key => ds.reduce((s, d) => s + d[key] * d.posts_scored, 0) / n;
    return { label: `Week of ${dayLabel(k)}`, posts_scored: n, avg_toxicity: w('avg_toxicity'),
      ...Object.fromEntries(CATS.map(c => [c.key, w(c.key)])) };
  });
}

function renderOverview() {
  const s = series();
  const n = s.reduce((a, d) => a + d.posts_scored, 0);
  const w = k => s.reduce((a, d) => a + d[k] * d.posts_scored, 0) / n;
  const first = state.range === 'all' ? DATA.summary.first_day : DATA.daily.slice(-Number(state.range))[0].day;
  document.getElementById('range-note').textContent = `${dayLabel(first)} to ${dayLabel(DATA.summary.last_day)}, ${DATA.summary.last_day.slice(0, 4)} · UTC`;

  document.getElementById('kpis').innerHTML = [
    ['Posts scored', fmt(n), `${s.length} ${state.agg === 'day' ? 'days' : 'weeks'} of data`],
    ['Flagged at 0.5', pct(w('share_toxic')), `about 1 in ${Math.round(1 / w('share_toxic'))} posts`],
    ['Average toxicity', w('avg_toxicity').toFixed(2), 'on a 0 to 1 scale'],
    ['Threat flags', pct(w('share_threat'), 2), 'the rarest category'],
  ].map(([l, v, sub]) => `<div class="kpi"><p class="label">${l}</p><p class="value">${v}</p><p class="sub">${sub}</p></div>`).join('');

  const labels = s.map(d => d.label);
  chart('c-rate', { type: 'line',
    data: { labels, datasets: CATS.map(c => ({ label: c.name, data: s.map(d => d[c.key]), borderColor: c.color, backgroundColor: c.color,
      borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: .25 })) },
    options: { interaction: { mode: 'index', intersect: false }, scales: axes(v => pct(v, 1)),
      plugins: { legend: { position: 'top', align: 'start' }, tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${pct(c.parsed.y, 2)}` } } } } });

  chart('c-volume', { type: 'bar',
    data: { labels, datasets: [{ label: 'Posts scored', data: s.map(d => d.posts_scored), backgroundColor: C.blue, borderRadius: 4, maxBarThickness: 36 }] },
    options: { scales: axes(v => v >= 1000 ? `${v / 1000}k` : v), plugins: { legend: { display: false },
      tooltip: { callbacks: { label: c => ` ${fmt(c.parsed.y)} posts` } } } } });

  chart('c-avg', { type: 'line',
    data: { labels, datasets: [{ label: 'Average toxicity', data: s.map(d => d.avg_toxicity), borderColor: C.blue, backgroundColor: 'rgba(0,133,255,.08)',
      fill: true, borderWidth: 2, pointRadius: 3, tension: .25 }] },
    options: { interaction: { mode: 'index', intersect: false }, scales: axes(v => v.toFixed(2), { suggestedMax: 0.2 }),
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.y.toFixed(3)}` } } } } });

  chart('c-cats', { type: 'bar',
    data: { labels: CATS.map(c => c.name), datasets: [{ data: CATS.map(c => w(c.key)), backgroundColor: CATS.map(c => c.color), borderRadius: 4, maxBarThickness: 28 }] },
    options: { indexAxis: 'y', scales: { x: { beginAtZero: true, grid: { color: C.grid }, border: { display: false }, ticks: { callback: v => pct(v, 0) } },
      y: { grid: { display: false }, border: { color: '#D4DBE2' } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${pct(c.parsed.x, 2)} of posts` } } } } });

  const wrap = document.getElementById('dist-wrap');
  if (DATA.distribution?.length) {
    if (!wrap.querySelector('canvas')) wrap.innerHTML = '<canvas id="c-dist"></canvas>';
    chart('c-dist', { type: 'bar',
      data: { labels: DATA.distribution.map(d => d.bucket.toFixed(2)), datasets: [{ data: DATA.distribution.map(d => d.posts),
        backgroundColor: DATA.distribution.map(d => d.bucket >= 0.5 ? C.blue : '#B8D9FF'), borderRadius: 3, barPercentage: .95, categoryPercentage: .95 }] },
      options: { scales: axes(v => v >= 1000 ? `${v / 1000}k` : v), plugins: { legend: { display: false },
        tooltip: { callbacks: { title: c => `Score ${c[0].label} to ${(+c[0].label + .05).toFixed(2)}`, label: c => ` ${fmt(c.parsed.y)} posts` } } } } });
  } else {
    emptyState(wrap, 'Not exported yet', 'Run <code>python scripts/export_dashboard_data.py</code> with Postgres running to add the distribution.');
  }
}

function renderReview() {
  const el = document.getElementById('review');
  if (!DATA.top_posts?.length) {
    emptyState(el, 'Not exported yet', 'Run <code>python scripts/export_dashboard_data.py</code> with Postgres running to fill the review feed.');
    return;
  }
  const rows = [...DATA.top_posts].sort((a, b) => b[state.sort] - a[state.sort]).slice(0, 50);
  const cell = v => `<td><span class="score"><span class="bar"><i style="width:${v * 100}%"></i></span>${v.toFixed(3)}</span></td>`;
  el.innerHTML = `<div class="scroll"><table><thead><tr><th>Seen (UTC)</th><th>Post</th><th>Account</th><th>Toxicity</th><th>Severe</th><th>Obscene</th><th>Threat</th><th>Insult</th><th>Identity attack</th></tr></thead><tbody>${
    rows.map(r => `<tr><td>${r.seen_at ? esc(r.seen_at.slice(0, 16).replace('T', ' ')) : ''}</td><td class="mono">${esc(r.post)}</td><td class="mono">${esc(r.account)}</td>${
      ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack'].map(k => cell(r[k])).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function renderHealth() {
  const runs = DATA.runs || [];
  if (!runs.length) { emptyState(document.getElementById('runs-table'), 'No runs exported', 'Run <code>python scripts/run_report.py</code>, then the export script.'); return; }
  const ok = runs.filter(r => r.state === 'success');
  const firstFail = r => TASKS.find(([k]) => r.tasks[k].state === 'failed');
  const failedAt = Object.fromEntries(TASKS.map(([, n]) => [n, 0]));
  runs.filter(r => r.state === 'failed').forEach(r => { const t = firstFail(r); if (t) failedAt[t[1]]++; });
  const testFails = runs.filter(r => r.tasks.dbt_test.state === 'failed').length;

  document.getElementById('health-kpis').innerHTML = [
    ['Runs logged', fmt(runs.length), `${dayLabel(runs[0].logical_date.slice(0, 10))} to ${dayLabel(runs.at(-1).logical_date.slice(0, 10))}`],
    ['Succeeded', pct(ok.length / runs.length, 0), `${ok.length} of ${runs.length} runs`],
    ['dbt test failures', String(testFails), 'bad data never reached the charts'],
    ['Most failures at', Object.entries(failedAt).sort((a, b) => b[1] - a[1])[0][0], 'usually the laptop sleeping mid-run'],
  ].map(([l, v, sub]) => `<div class="kpi"><p class="label">${l}</p><p class="value">${v}</p><p class="sub">${sub}</p></div>`).join('');

  const byDay = new Map();
  runs.forEach(r => { const d = r.logical_date.slice(0, 10); const e = byDay.get(d) || { success: 0, failed: 0 }; e[r.state === 'success' ? 'success' : 'failed']++; byDay.set(d, e); });
  const days = [...byDay.keys()].sort();
  chart('c-runs', { type: 'bar',
    data: { labels: days.map(dayLabel), datasets: [
      { label: 'Succeeded', data: days.map(d => byDay.get(d).success), backgroundColor: C.good, borderRadius: 4, maxBarThickness: 40 },
      { label: 'Failed', data: days.map(d => byDay.get(d).failed), backgroundColor: C.critical, borderRadius: 4, maxBarThickness: 40 }] },
    options: { interaction: { mode: 'index', intersect: false }, scales: { x: { stacked: true, grid: { display: false } },
      y: { stacked: true, grid: { color: C.grid }, border: { display: false }, ticks: { precision: 0 } } },
      plugins: { legend: { position: 'top', align: 'start' } } } });

  chart('c-fail', { type: 'bar',
    data: { labels: Object.keys(failedAt), datasets: [{ data: Object.values(failedAt), backgroundColor: C.critical, borderRadius: 4, maxBarThickness: 28 }] },
    options: { indexAxis: 'y', scales: { x: { beginAtZero: true, grid: { color: C.grid }, border: { display: false }, ticks: { precision: 0 } }, y: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.x} failed runs` } } } } });

  const median = a => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };
  chart('c-dur', { type: 'bar',
    data: { labels: TASKS.map(t => t[1]), datasets: [{ data: TASKS.map(([k]) => median(ok.map(r => r.tasks[k].s).filter(v => v != null)) / 60),
      backgroundColor: C.blue, borderRadius: 4, maxBarThickness: 28 }] },
    options: { indexAxis: 'y', scales: { x: { beginAtZero: true, grid: { color: C.grid }, border: { display: false }, ticks: { callback: v => `${v} min` } }, y: { grid: { display: false } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.x < 1 ? Math.round(c.parsed.x * 60) + ' s' : c.parsed.x.toFixed(1) + ' min'}` } } } } });

  const recent = runs.slice(-15).reverse();
  const st = s => s ? `<span class="status ${s === 'success' ? 'success' : 'failed'}">${s === 'success' ? 'Success' : s === 'failed' ? 'Failed' : 'Skipped'}</span>` : '';
  document.getElementById('runs-table').innerHTML = `<div class="scroll"><table><thead><tr><th>Run (UTC)</th><th>Outcome</th>${TASKS.map(t => `<th>${t[1]}</th>`).join('')}<th>Wall time</th></tr></thead><tbody>${
    recent.map(r => `<tr><td>${esc(r.logical_date.slice(0, 16).replace('T', ' '))}</td><td>${st(r.state)}</td>${TASKS.map(([k]) => `<td>${st(r.tasks[k].state)}</td>`).join('')}<td>${r.duration_s ? Math.round(r.duration_s / 60) + ' min' : ''}</td></tr>`).join('')}</tbody></table></div>`;
}

function show(tab) {
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
  document.getElementById('filters').style.display = tab === 'overview' ? '' : 'none';
  ({ overview: renderOverview, review: renderReview, health: renderHealth })[tab]?.();
}

document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => show(b.dataset.tab)));
document.querySelectorAll('.seg-btn').forEach(b => b.addEventListener('click', () => {
  state.range = b.dataset.range;
  document.querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('active', x === b));
  renderOverview();
}));
document.getElementById('agg').addEventListener('change', e => { state.agg = e.target.value; renderOverview(); });
document.getElementById('sort').addEventListener('change', e => { state.sort = e.target.value; renderReview(); });

fetch('data/dashboard.json').then(r => r.json()).then(d => {
  DATA = d;
  document.getElementById('updated').textContent = `Data through ${dayLabel(d.summary.last_day)}, ${d.summary.last_day.slice(0, 4)}.`;
  document.getElementById('source').textContent = `Exported ${d.generated_at.slice(0, 10)} from ${d.source}`;
  show('overview');
});
