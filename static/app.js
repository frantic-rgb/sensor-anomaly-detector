'use strict';

const MAX_POINTS = 60;
const LOG_MAX    = 15;
const SPEC_TEMP_LIMIT = -30;  // °C — minimum allowed specimen temperature

const SENSORS = {
  pressure:      { color: '#0F766E', unit: 'MPa',    yMax: 120,  yMin: 0 },
  temperature:   { color: '#0EA5E9', unit: '°C',     yMax: 80,   yMin: 20 },
  flow:          { color: '#8B5CF6', unit: 'ml/min', yMax: 2.5,  yMin: 0 },
  specimen_temp: { color: '#F59E0B', unit: '°C',     yMax: 35,   yMin: -45 },
};

const ANOMALY_TYPE_LABEL = {
  PRESSURE_DROP:  'Pressure Drop',
  OVERPRESSURE:   'Overpressure',
  THERMAL:        'Thermal Excursion',
  FLOW_SPIKE:     'H₂ Flow Spike',
  UNDERCOOLING:   'Specimen Undercooling',
};

const chartState = {};
const charts     = {};

let totalReadings = 0;
let anomalyCount  = 0;
const log = [];

// ── Chart factory ─────────────────────────────────────────────────────────

function buildChart(key) {
  const { color, unit, yMax, yMin } = SENSORS[key];
  const data  = new Array(MAX_POINTS).fill(null);
  const flags = new Array(MAX_POINTS).fill(false);

  chartState[key] = { data, flags };

  const ctx = document.getElementById(`chart-${key}`).getContext('2d');

  const datasets = [{
    data,
    borderColor: color,
    backgroundColor: color + '18',
    borderWidth: 1.5,
    tension: 0.35,
    fill: true,
    pointRadius:          (ctx) => flags[ctx.dataIndex] ? 7  : 0,
    pointBackgroundColor: (ctx) => flags[ctx.dataIndex] ? '#EF4444' : color,
    pointBorderColor:     (ctx) => flags[ctx.dataIndex] ? '#EF4444' : color,
    pointBorderWidth:     (ctx) => flags[ctx.dataIndex] ? 2.5 : 0,
    pointStyle:           (ctx) => flags[ctx.dataIndex] ? 'crossRot' : 'circle',
  }];

  // Threshold line for specimen temperature
  if (key === 'specimen_temp') {
    datasets.push({
      data: new Array(MAX_POINTS).fill(SPEC_TEMP_LIMIT),
      borderColor: '#EF444466',
      borderWidth: 1,
      borderDash: [5, 4],
      pointRadius: 0,
      fill: false,
      tension: 0,
    });
  }

  return new Chart(ctx, {
    type: 'line',
    data: { labels: new Array(MAX_POINTS).fill(''), datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#162032',
          borderColor: '#243447',
          borderWidth: 1,
          callbacks: {
            label: (ctx) => {
              if (ctx.datasetIndex !== 0) return '';
              if (ctx.raw == null) return '';
              const anomalous = flags[ctx.dataIndex];
              return ` ${ctx.raw.toFixed(2)} ${unit}${anomalous ? '  ⚠' : ''}`;
            },
          },
        },
      },
      scales: {
        x: { display: false },
        y: {
          suggestedMin: yMin,
          suggestedMax: yMax,
          grid:   { color: '#1E2D40', lineWidth: 1 },
          ticks:  { color: '#4A6080', font: { size: 11 }, maxTicksLimit: 5 },
          border: { display: false },
        },
      },
    },
  });
}

function pushValue(key, value, isAnomaly) {
  const { data, flags } = chartState[key];
  data.shift();  data.push(value);
  flags.shift(); flags.push(isAnomaly);
  charts[key].data.labels.shift();
  charts[key].data.labels.push('');
  // Also shift threshold line dataset if present
  if (key === 'specimen_temp') {
    const thresh = charts[key].data.datasets[1].data;
    thresh.shift(); thresh.push(SPEC_TEMP_LIMIT);
  }
  charts[key].update('none');
}

// ── Reading handler ───────────────────────────────────────────────────────

function handleReading(d) {
  totalReadings++;
  const isAnomaly = d.is_anomaly;
  const topSensor = d.top_sensor;
  if (isAnomaly) anomalyCount++;

  for (const key of Object.keys(SENSORS)) {
    const isTrigger = isAnomaly && key === topSensor;
    pushValue(key, d[key], isTrigger);

    const valEl = document.getElementById(`val-${key}`);
    valEl.textContent = (key === 'flow')
      ? d[key].toFixed(2)
      : d[key].toFixed(1);
    valEl.className = 'sensor-value' + (isTrigger ? ' anomaly' : '');

    document.getElementById(`card-${key}`)
      .classList.toggle('anomaly', isTrigger);
  }

  // Warn if specimen temp approaches limit
  const specCard = document.getElementById('card-specimen_temp');
  if (d.specimen_temp <= SPEC_TEMP_LIMIT) {
    specCard.classList.add('limit-breach');
  } else {
    specCard.classList.remove('limit-breach');
  }

  document.getElementById('cycle-count').textContent = d.cycle_count;

  document.getElementById('stat-total').textContent     = totalReadings.toLocaleString('de-DE');
  document.getElementById('stat-anomalies').textContent = anomalyCount;
  document.getElementById('stat-rate').textContent      =
    totalReadings > 0 ? (anomalyCount / totalReadings * 100).toFixed(1) + '%' : '—';

  if (isAnomaly) appendLog(d);
}

// ── Anomaly log ───────────────────────────────────────────────────────────

const SENSOR_LABEL = {
  pressure:      'Test Pressure',
  temperature:   'Gas Temp.',
  flow:          'H₂ Flow',
  specimen_temp: 'Specimen Temp.',
};

function appendLog(d) {
  const time      = new Date(d.timestamp).toLocaleTimeString('de-DE', { hour12: false });
  const typeLabel = ANOMALY_TYPE_LABEL[d.anomaly_type] ?? d.anomaly_type ?? '—';
  const sensor    = SENSOR_LABEL[d.top_sensor] ?? d.top_sensor;
  const risk      = d.risk_score;
  const fillColor = risk >= 70 ? '#EF4444' : risk >= 40 ? '#F59E0B' : '#34D399';

  log.unshift({ time, typeLabel, sensor, risk, fillColor, cycle: d.cycle_count });
  if (log.length > LOG_MAX) log.pop();
  renderLog();
}

function renderLog() {
  const el = document.getElementById('anomaly-log');
  if (log.length === 0) {
    el.innerHTML = '<p class="log-empty">No anomalies detected yet.</p>';
    return;
  }
  el.innerHTML = log.map(e => `
    <div class="log-entry">
      <div class="log-row">
        <span class="log-type">${e.typeLabel}</span>
        <span class="log-time">${e.time}</span>
      </div>
      <div class="log-sensor">Cycle ${e.cycle} · ${e.sensor}</div>
      <div class="risk-label">Risk: ${e.risk}%</div>
      <div class="risk-bar">
        <div class="risk-fill" style="width:${e.risk}%;background:${e.fillColor}"></div>
      </div>
    </div>
  `).join('');
}

// ── Connection status ─────────────────────────────────────────────────────

function setStatus(state) {
  const el = document.getElementById('ws-badge');
  if (state === 'live') {
    el.textContent = '● LIVE';
    el.className   = 'badge badge-live';
  } else {
    el.textContent = '● OFFLINE';
    el.className   = 'badge badge-offline';
  }
}

// ── WebSocket with auto-reconnect ─────────────────────────────────────────

let activeWs = null;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws    = new WebSocket(`${proto}//${location.host}/ws`);
  activeWs    = ws;

  ws.onopen    = () => setStatus('live');
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    if (d.speed !== undefined) {
      document.getElementById('stream-rate').textContent = `${d.speed}× (${d.speed * 2} rdg/s)`;
    }
    handleReading(d);
  };
  ws.onclose   = () => { setStatus('offline'); setTimeout(connect, 3000); };
  ws.onerror   = () => ws.close();
}

// ── Speed control ─────────────────────────────────────────────────────────

function setupSpeedControl() {
  document.querySelectorAll('.speed-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const speed = parseInt(btn.dataset.speed);
      if (activeWs && activeWs.readyState === WebSocket.OPEN) {
        activeWs.send(JSON.stringify({ speed }));
      }
    });
  });
}

// ── Dataset export ────────────────────────────────────────────────────────

function setupExport() {
  const cyclesInput = document.getElementById('export-cycles');
  const btn         = document.getElementById('export-btn');
  if (!cyclesInput || !btn) return;
  cyclesInput.addEventListener('input', () => {
    const n = Math.max(10, Math.min(1000, parseInt(cyclesInput.value) || 100));
    btn.href = `/api/dataset?cycles=${n}`;
  });
}

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  for (const key of Object.keys(SENSORS)) {
    charts[key] = buildChart(key);
  }
  renderLog();
  setupExport();
  setupSpeedControl();
  connect();
});
