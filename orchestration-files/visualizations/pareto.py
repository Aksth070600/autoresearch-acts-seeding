"""Render an interactive Pareto comparison page."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ACTS Seeding comparison</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f5f7fb; color: #172033; }
    main { max-width: 1280px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; }
    .lede { color: #536078; margin: 0 0 20px; }
    .controls { display: flex; flex-wrap: wrap; gap: 14px; align-items: end;
      background: white; border: 1px solid #dce2ef; border-radius: 10px; padding: 16px; }
    label { display: grid; gap: 5px; font-size: 0.9rem; font-weight: 650; }
    select { min-width: 230px; padding: 7px; border: 1px solid #b8c2d6; border-radius: 6px; background: white; }
    #summary { margin: 14px 0 0; color: #536078; min-height: 1.4em; }
    #chart { height: 680px; margin-top: 8px; background: white; border: 1px solid #dce2ef; border-radius: 10px; }
    .note { color: #536078; font-size: 0.88rem; }
    code { background: #e9edf5; padding: 2px 5px; border-radius: 4px; }
  </style>
</head>
<body>
<main>
  <h1>ACTS Seeding Pareto comparison</h1>
  <p class="lede">Lower X is better. Higher Y is better. The reference lines show the selected baseline.</p>
  <section class="controls" aria-label="Chart controls">
    <label>Dataset<select id="dataset"></select></label>
    <label>X metric<select id="x-metric"></select></label>
    <label>Y metric<select id="y-metric"></select></label>
    <label>Baseline<select id="baseline"></select></label>
  </section>
  <p id="summary"></p>
  <div id="chart" role="img" aria-label="Interactive Pareto comparison chart"></div>
  <p class="note">Points above and left of the baseline are faster and more efficient. The orange line is the Pareto frontier.</p>
</main>
<script>
const REPORT = __REPORT_JSON__;
const DEFAULTS = __DEFAULTS_JSON__;
const rows = REPORT.rows || [];
const metricLabels = REPORT.metric_labels || {};
const metricKeys = REPORT.metric_keys || [];
const xSelect = document.getElementById('x-metric');
const ySelect = document.getElementById('y-metric');
const datasetSelect = document.getElementById('dataset');
const baselineSelect = document.getElementById('baseline');
const summary = document.getElementById('summary');

function option(select, value, label) {
  const element = document.createElement('option');
  element.value = value;
  element.textContent = label;
  select.appendChild(element);
}
metricKeys.forEach((key) => {
  option(xSelect, key, metricLabels[key] || key);
  option(ySelect, key, metricLabels[key] || key);
});
option(datasetSelect, 'all', 'All datasets');
[...new Set(rows.map((row) => row.category))].sort().forEach((category) => {
  option(datasetSelect, category, category);
});
xSelect.value = DEFAULTS.x_metric;
ySelect.value = DEFAULTS.y_metric;

function scopedRows() {
  return datasetSelect.value === 'all'
    ? rows
    : rows.filter((row) => row.category === datasetSelect.value);
}
function updateBaselineOptions() {
  const baselineNames = [...new Set(scopedRows().map((row) => row.candidate))].sort();
  baselineSelect.replaceChildren();
  baselineNames.forEach((name) => option(baselineSelect, name, name));
  baselineSelect.value = baselineNames.includes(DEFAULTS.baseline) ? DEFAULTS.baseline : (baselineNames[0] || '');
}
function validRows(xKey, yKey) {
  return scopedRows().filter((row) => Number.isFinite(row.metrics[xKey]) && Number.isFinite(row.metrics[yKey]));
}
updateBaselineOptions();
function frontier(points) {
  const sorted = [...points].sort((a, b) => a.metrics[xSelect.value] - b.metrics[xSelect.value]);
  const result = [];
  let bestY = -Infinity;
  sorted.forEach((point) => {
    const y = point.metrics[ySelect.value];
    if (y >= bestY) {
      result.push(point);
      bestY = y;
    }
  });
  return result;
}
function render() {
  const xKey = xSelect.value;
  const yKey = ySelect.value;
  const points = validRows(xKey, yKey);
  const baselineName = baselineSelect.value;
  const baseline = points.find((row) => row.candidate === baselineName);
  const xLabel = metricLabels[xKey] || xKey;
  const yLabel = metricLabels[yKey] || yKey;
  if (!points.length) {
    summary.textContent = 'No records contain both selected metrics.';
    Plotly.purge('chart');
    return;
  }
  if (!baseline) {
    summary.textContent = `No baseline record contains both ${xLabel} and ${yLabel}.`;
  } else {
    summary.textContent = `${points.length} records in ${datasetSelect.value}. Baseline: ${baselineName} (${xLabel} = ${baseline.metrics[xKey].toFixed(2)}, ${yLabel} = ${baseline.metrics[yKey].toFixed(6)}).`;
  }
  const traces = [{
    x: points.map((row) => row.metrics[xKey]),
    y: points.map((row) => row.metrics[yKey]),
    text: points.map((row) => `${row.candidate} (${row.category})`),
    customdata: points.map((row) => [row.category, row.record, row.commit]),
    mode: 'markers',
    type: 'scatter',
    name: 'Candidates',
    marker: { size: 12, color: points.map((row) => row.candidate === baselineName ? '#2563eb' : '#64748b'), line: { width: 1, color: '#172033' } },
    hovertemplate: '<b>%{text}</b><br>X: %{x}<br>Y: %{y}<br>Category: %{customdata[0]}<br>Record: %{customdata[1]}<br>Commit: %{customdata[2]}<extra></extra>'
  }];
  const pareto = frontier(points);
  if (pareto.length > 1) {
    traces.push({
      x: pareto.map((row) => row.metrics[xKey]),
      y: pareto.map((row) => row.metrics[yKey]),
      mode: 'lines+markers',
      type: 'scatter',
      name: 'Pareto frontier',
      line: { color: '#f97316', width: 3 },
      marker: { size: 7, color: '#f97316' },
      hoverinfo: 'skip'
    });
  }
  const xValues = points.map((row) => row.metrics[xKey]);
  const yValues = points.map((row) => row.metrics[yKey]);
  const shapes = [];
  const annotations = [];
  if (baseline) {
    const bx = baseline.metrics[xKey];
    const by = baseline.metrics[yKey];
    shapes.push({ type: 'line', x0: bx, x1: bx, y0: 0, y1: 1, yref: 'paper', line: { color: '#2563eb', dash: 'dash', width: 2 } });
    shapes.push({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: by, y1: by, line: { color: '#2563eb', dash: 'dash', width: 2 } });
    annotations.push({ x: 0.02, y: 0.98, xref: 'paper', yref: 'paper', text: 'faster + more efficient', showarrow: false, font: { color: '#15803d' }, bgcolor: 'rgba(255,255,255,0.8)' });
    annotations.push({ x: 0.98, y: 0.05, xref: 'paper', yref: 'paper', text: 'slower + less efficient', showarrow: false, xanchor: 'right', font: { color: '#b91c1c' }, bgcolor: 'rgba(255,255,255,0.8)' });
  }
  Plotly.react('chart', traces, {
    title: 'Baseline-relative performance',
    xaxis: { title: xLabel, zeroline: false },
    yaxis: { title: yLabel, zeroline: false },
    hovermode: 'closest',
    shapes,
    annotations,
    margin: { l: 80, r: 30, t: 70, b: 80 },
    legend: { orientation: 'h' },
    paper_bgcolor: 'white', plot_bgcolor: 'white'
  }, { responsive: true, displaylogo: false });
}
[xSelect, ySelect, baselineSelect].forEach((select) => select.addEventListener('change', render));
datasetSelect.addEventListener('change', () => {
  updateBaselineOptions();
  render();
});
render();
</script>
</body>
</html>
"""


def render(report: dict[str, Any], output: Path, *, defaults: dict[str, str]) -> None:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    default_json = json.dumps(defaults, sort_keys=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        HTML_TEMPLATE.replace("__REPORT_JSON__", payload).replace("__DEFAULTS_JSON__", default_json),
        encoding="utf-8",
    )
