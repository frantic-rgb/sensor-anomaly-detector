'use strict';

const MODEL_NAMES = [
  "isolation_forest", "local_outlier_factor", "one_class_svm",
  "elliptic_envelope", "zscore",
];
const MODEL_LABELS = {
  isolation_forest:     "Isolation Forest",
  local_outlier_factor: "Local Outlier Factor",
  one_class_svm:        "One-Class SVM",
  elliptic_envelope:    "Elliptic Envelope",
  zscore:               "Z-Score (σ ≥ 3.2)",
};

const MODEL_COLORS = {
  isolation_forest:     '#0F766E',
  local_outlier_factor: '#0EA5E9',
  one_class_svm:        '#8B5CF6',
  elliptic_envelope:    '#F59E0B',
  zscore:               '#34D399',
};

let f1Chart = null, prChart = null, timelineChart = null;

// ── Run comparison (simulation) ───────────────────────────────────────────

document.getElementById('run-btn').addEventListener('click', async () => {
  const cycles = parseInt(document.getElementById('cmp-cycles').value) || 100;
  await runFromApi(`/api/compare?cycles=${cycles}`, `Simulating ${cycles} cycles…`, 'Run');
});

// ── Load pre-generated sample ─────────────────────────────────────────────

document.getElementById('sample-btn').addEventListener('click', async () => {
  const status = document.getElementById('cmp-status');
  const btn    = document.getElementById('sample-btn');
  btn.disabled = true;
  status.textContent = 'Loading sample dataset (100 cycles)…';
  try {
    const res  = await fetch('/h2_sample_dataset.csv');
    if (!res.ok) throw new Error('Sample file not ready yet — start the server first.');
    const text = await res.text();
    const data = parseCsvToCompareData(text);
    render(data);
    status.textContent = `Loaded — ${data.total_steps.toLocaleString()} readings, ${data.total_injected} injected anomaly steps.`;
    document.getElementById('results').classList.remove('hidden');
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
});

async function runFromApi(url, loadingMsg, btnLabel) {
  const status = document.getElementById('cmp-status');
  const btn    = document.getElementById('run-btn');
  btn.disabled    = true;
  btn.textContent = 'Running…';
  status.textContent = loadingMsg;
  try {
    const res  = await fetch(url);
    const data = await res.json();
    render(data);
    status.textContent = `Done — ${data.total_steps.toLocaleString()} readings, ${data.total_injected} injected anomaly steps.`;
    document.getElementById('results').classList.remove('hidden');
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
  } finally {
    btn.disabled    = false;
    btn.textContent = btnLabel;
  }
}

// ── CSV parser → compare data format ─────────────────────────────────────

function parseCsvToCompareData(csvText) {
  const lines   = csvText.trim().split('\n');
  const headers = lines[0].split(',');
  const rows    = lines.slice(1).map(l => {
    const vals = l.split(',');
    const obj  = {};
    headers.forEach((h, i) => obj[h.trim()] = vals[i]?.trim() ?? '');
    return obj;
  });

  const RELEASE_HOLD  = 0.70;
  const RELEASE_WIDTH = 0.125;

  const counters = {};
  MODEL_NAMES.forEach(m => { counters[m] = { tp: 0, fp: 0, fn: 0, tn: 0 }; });

  let totalInjected = 0;
  const timeline = [];

  rows.forEach((row, idx) => {
    const truth      = row.injected_anomaly === 'True';
    const phase      = parseFloat(row.cycle_phase);
    const inRelease  = phase >= RELEASE_HOLD && phase <= RELEASE_HOLD + RELEASE_WIDTH;
    if (truth) totalInjected++;

    MODEL_NAMES.forEach(m => {
      const raw      = row[`${m}_detected`];
      const detected = (raw === 'True') && !(inRelease && !truth);
      if (truth && detected)       counters[m].tp++;
      else if (!truth && detected) counters[m].fp++;
      else if (truth && !detected) counters[m].fn++;
      else                         counters[m].tn++;
    });

    if (idx % 4 === 0) {
      const entry = {
        step: idx, cycle: parseInt(row.cycle_count), phase,
        truth,
      };
      MODEL_NAMES.forEach(m => {
        entry[`${m}_score`]   = parseFloat(row[`${m}_score`]) || 0;
        entry[`${m}_det`]     = row[`${m}_detected`] === 'True';
      });
      timeline.push(entry);
    }
  });

  const metrics = {};
  MODEL_NAMES.forEach(m => {
    const c  = counters[m];
    const pr = c.tp / (c.tp + c.fp) || 0;
    const rc = c.tp / (c.tp + c.fn) || 0;
    const f1 = (pr + rc) > 0 ? 2 * pr * rc / (pr + rc) : 0;
    const fpr= c.fp / (c.fp + c.tn) || 0;
    metrics[m] = {
      label: MODEL_LABELS[m],
      ...c,
      precision: +pr.toFixed(3), recall: +rc.toFixed(3),
      f1: +f1.toFixed(3), fpr: +fpr.toFixed(3),
    };
  });

  return {
    cycles: Math.max(...rows.map(r => parseInt(r.cycle_count))) + 1,
    total_steps: rows.length,
    total_injected: totalInjected,
    metrics,
    model_names: MODEL_NAMES,
    model_labels: MODEL_LABELS,
    timeline,
  };
}

// ── Render ────────────────────────────────────────────────────────────────

function render(data) {
  renderTable(data);
  renderF1Chart(data);
  renderPRChart(data);
  renderTimeline(data);
}

function renderTable(data) {
  const tbody = document.getElementById('metrics-body');
  tbody.innerHTML = '';

  const sorted = [...data.model_names].sort(
    (a, b) => data.metrics[b].f1 - data.metrics[a].f1
  );

  sorted.forEach((m, rank) => {
    const mt = data.metrics[m];
    const tr = document.createElement('tr');
    if (rank === 0) tr.className = 'best-row';
    tr.innerHTML = `
      <td class="model-name-cell">
        <span class="model-dot" style="background:${MODEL_COLORS[m]}"></span>
        ${mt.label}
        ${rank === 0 ? '<span class="best-badge">best</span>' : ''}
      </td>
      <td class="num ${pct(mt.precision)}">${pf(mt.precision)}</td>
      <td class="num ${pct(mt.recall)}">${pf(mt.recall)}</td>
      <td class="num ${pct(mt.f1)} bold">${pf(mt.f1)}</td>
      <td class="num ${fprClass(mt.fpr)}">${pf(mt.fpr)}</td>
      <td class="num dim">${mt.tp}</td>
      <td class="num dim red">${mt.fp}</td>
      <td class="num dim red">${mt.fn}</td>
      <td class="num dim">${mt.tn}</td>
    `;
    tbody.appendChild(tr);
  });
}

function pf(v) { return (v * 100).toFixed(1) + '%'; }
function pct(v) { return v >= 0.7 ? 'good' : v >= 0.4 ? 'warn' : 'bad'; }
function fprClass(v) { return v <= 0.05 ? 'good' : v <= 0.15 ? 'warn' : 'bad'; }

function renderF1Chart(data) {
  if (f1Chart) { f1Chart.destroy(); f1Chart = null; }

  const sorted = [...data.model_names].sort(
    (a, b) => data.metrics[b].f1 - data.metrics[a].f1
  );

  f1Chart = new Chart(document.getElementById('f1-chart'), {
    type: 'bar',
    data: {
      labels: sorted.map(m => data.metrics[m].label),
      datasets: [{
        data:            sorted.map(m => +(data.metrics[m].f1 * 100).toFixed(1)),
        backgroundColor: sorted.map(m => MODEL_COLORS[m] + 'CC'),
        borderColor:     sorted.map(m => MODEL_COLORS[m]),
        borderWidth: 1.5,
        borderRadius: 5,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#94A3B8', font: { size: 11 } }, grid: { display: false }, border: { display: false } },
        y: { suggestedMax: 100, ticks: { color: '#4A6080', callback: v => v + '%' }, grid: { color: '#1E2D40' }, border: { display: false } },
      },
    },
  });
}

function renderPRChart(data) {
  if (prChart) { prChart.destroy(); prChart = null; }

  prChart = new Chart(document.getElementById('pr-chart'), {
    type: 'scatter',
    data: {
      datasets: data.model_names.map(m => ({
        label: data.metrics[m].label,
        data: [{ x: data.metrics[m].recall * 100, y: data.metrics[m].precision * 100 }],
        backgroundColor: MODEL_COLORS[m],
        borderColor:     MODEL_COLORS[m],
        pointRadius: 9,
        pointHoverRadius: 12,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: '#94A3B8', font: { size: 11 }, boxWidth: 10, padding: 12 } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.dataset.label}  P=${ctx.parsed.y.toFixed(1)}%  R=${ctx.parsed.x.toFixed(1)}%` } },
      },
      scales: {
        x: { title: { display: true, text: 'Recall %', color: '#64748B' }, suggestedMin: 0, suggestedMax: 100, ticks: { color: '#4A6080' }, grid: { color: '#1E2D40' }, border: { display: false } },
        y: { title: { display: true, text: 'Precision %', color: '#64748B' }, suggestedMin: 0, suggestedMax: 100, ticks: { color: '#4A6080' }, grid: { color: '#1E2D40' }, border: { display: false } },
      },
    },
  });
}

function renderTimeline(data) {
  if (timelineChart) { timelineChart.destroy(); timelineChart = null; }

  const tl     = data.timeline;
  const labels = tl.map(d => d.step);

  // Ground-truth markers as a bar dataset (thin red lines at anomaly steps)
  const truthData = tl.map(d => d.truth ? 1 : null);

  const modelDatasets = data.model_names.map(m => ({
    label:           data.metrics[m].label,
    data:            tl.map(d => d[`${m}_score`]),
    borderColor:     MODEL_COLORS[m],
    backgroundColor: 'transparent',
    borderWidth: 1.2,
    tension: 0,
    pointRadius: 0,
    yAxisID: 'y',
  }));

  document.getElementById('zoom-reset-btn').onclick = () => timelineChart?.resetZoom();

  timelineChart = new Chart(document.getElementById('timeline-chart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Ground Truth',
          data: truthData,
          borderColor: 'transparent',
          backgroundColor: '#EF444430',
          borderWidth: 0,
          fill: true,
          pointRadius: 0,
          tension: 0,
          yAxisID: 'y2',
        },
        ...modelDatasets,
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#94A3B8', font: { size: 11 }, boxWidth: 12, filter: item => item.text !== 'Ground Truth' } },
        tooltip: {
          backgroundColor: '#162032',
          borderColor: '#243447',
          borderWidth: 1,
          filter: item => item.datasetIndex !== 0,
        },
        zoom: {
          zoom:  { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'x' },
          pan:   { enabled: true, mode: 'x' },
        },
      },
      scales: {
        x:  { display: false },
        y:  { title: { display: true, text: 'Anomaly Score', color: '#64748B' }, grid: { color: '#1E2D40' }, ticks: { color: '#4A6080' }, border: { display: false } },
        y2: { display: false, min: 0, max: 1 },
      },
    },
  });
}
