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
  <title>ACTS Seeding Autoresearch</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #0b1120; color: #e5e7eb; }
    main { max-width: 1280px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; }
    .topline { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .campaign-link { color: #a5b4fc; font-size: 0.9rem; font-weight: 650; white-space: nowrap; text-underline-offset: 3px; }
    .lede { color: #a5b4fc; margin: 0 0 20px; }
    .controls { display: grid; grid-template-columns: repeat(2, minmax(230px, 1fr)); gap: 14px; align-items: end;
      background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
    label { display: grid; gap: 5px; font-size: 0.9rem; font-weight: 650; }
    select { min-width: 0; padding: 7px; border: 1px solid #475569; border-radius: 6px; background: #1e293b; color: #e5e7eb; }
    .axis-picker { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; border: 1px solid #334155; border-radius: 8px; padding: 12px; margin: 0; }
    .axis-picker legend { color: #c4b5fd; font-weight: 700; padding: 0 6px; }
    .axis-picker label[hidden] { display: none; }
    @media (max-width: 700px) { .controls { grid-template-columns: 1fr; } .axis-picker { grid-template-columns: 1fr; } }
    #summary { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin: 14px 0 0; }
    .summary-card { display: grid; gap: 4px; min-height: 62px; padding: 12px 14px; background: #111827; border: 1px solid #334155; border-radius: 12px; }
    .summary-heading { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .summary-label { color: #94a3b8; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
    .summary-chip { padding: 3px 8px; background: #1e293b; border: 1px solid #475569; border-radius: 999px; color: #cbd5e1; font-size: 0.76rem; font-weight: 650; }
    .summary-value { color: #f8fafc; font-size: 1.1rem; font-weight: 750; }
    @media (max-width: 700px) { #summary { grid-template-columns: 1fr; } }
    #chart-frame { position: relative; height: 680px; margin-top: 8px; background: #111827; border: 1px solid #334155; border-radius: 10px; overflow: hidden; }
    #chart { height: 100%; }
    #chart .point { cursor: pointer; }
    #corner-overlays { position: absolute; inset: 28px 30px; z-index: 10; pointer-events: none; }
    .corner-stack { position: absolute; display: grid; gap: 5px; }
    .corner-stack.top-left { top: 18px; left: 49px; }
    .corner-stack.top-right { top: 18px; right: 2px; justify-items: end; }
    .corner-stack.bottom-left { bottom: 30px; left: 49px; justify-items: start; }
    .corner-stack.bottom-right { right: 2px; bottom: 30px; justify-items: end; }
    .corner-badge { width: max-content; padding: 4px 8px; border: 1px solid; border-radius: 999px; font-size: 0.72rem; font-weight: 750; letter-spacing: 0.03em; }
    .corner-badge.better { background: rgba(34,197,94,0.85); border-color: #4ade80; color: #052e16; }
    .corner-badge.worse { background: rgba(239,68,68,0.85); border-color: #f87171; color: #450a0a; }
    @media (max-width: 700px) { #corner-overlays { inset: 16px; } .corner-badge { font-size: 0.64rem; } }
    .note { color: #94a3b8; font-size: 0.88rem; }
    #empty-state { position: absolute; inset: 0; display: grid; place-items: center; padding: 24px; text-align: center; }
    #empty-state[hidden] { display: none; }
    code { background: #334155; padding: 2px 5px; border-radius: 4px; }
  </style>
</head>
<body>
<main>
  <div class="topline">
    <h1>ACTS Seeding Autoresearch</h1>
    <a class="campaign-link" href="campaign/">Open live campaign</a>
  </div>
  <p id="axis-guidance" class="lede">Lower X is better. Higher Y is better. The reference lines show the selected baseline.</p>
  <section class="controls" aria-label="Chart controls">
    <label>Dataset<select id="dataset"></select></label>
    <label>Baseline<select id="baseline"></select></label>
    <fieldset class="axis-picker">
      <legend>X axis</legend>
      <label>Type<select id="x-kind"></select></label>
      <label id="x-stage-label">Stage<select id="x-stage"></select></label>
      <label id="x-metric-label">Metric<select id="x-metric"></select></label>
    </fieldset>
    <fieldset class="axis-picker">
      <legend>Y axis</legend>
      <label>Type<select id="y-kind"></select></label>
      <label id="y-stage-label">Stage<select id="y-stage"></select></label>
      <label id="y-metric-label">Metric<select id="y-metric"></select></label>
    </fieldset>
  </section>
  <section id="summary" aria-live="polite">
    <div class="summary-card"><span class="summary-label">Records</span><strong id="summary-count" class="summary-value"></strong></div>
    <div class="summary-card"><span class="summary-label">Baseline</span><strong id="summary-baseline" class="summary-value"></strong></div>
    <div class="summary-card"><div class="summary-heading"><span class="summary-label">X axis baseline</span><span id="summary-x-label" class="summary-chip"></span></div><strong id="summary-x-value" class="summary-value"></strong></div>
    <div class="summary-card"><div class="summary-heading"><span class="summary-label">Y axis baseline</span><span id="summary-y-label" class="summary-chip"></span></div><strong id="summary-y-value" class="summary-value"></strong></div>
  </section>
  <div id="chart-frame">
    <div id="empty-state" class="note" hidden>No protocol-compatible summaries yet. Run a fresh Genesis baseline to populate this report.</div>
    <div id="chart" role="img" aria-label="Interactive Pareto comparison chart"></div>
    <div id="corner-overlays" aria-hidden="true">
      <div id="corner-top-left" class="corner-stack top-left"></div>
      <div id="corner-top-right" class="corner-stack top-right"></div>
      <div id="corner-bottom-left" class="corner-stack bottom-left"></div>
      <div id="corner-bottom-right" class="corner-stack bottom-right"></div>
    </div>
  </div>

</main>
<script>
const REPORT = __REPORT_JSON__;
const DEFAULTS = __DEFAULTS_JSON__;
const rows = REPORT.rows || [];
const datasetSelect = document.getElementById('dataset');
const baselineSelect = document.getElementById('baseline');
const summaryCount = document.getElementById('summary-count');
const summaryBaseline = document.getElementById('summary-baseline');
const summaryXValue = document.getElementById('summary-x-value');
const summaryXLabel = document.getElementById('summary-x-label');
const summaryYValue = document.getElementById('summary-y-value');
const summaryYLabel = document.getElementById('summary-y-label');
const emptyState = document.getElementById('empty-state');
const axisGuidance = document.getElementById('axis-guidance');
const cornerOverlays = {
  topLeft: document.getElementById('corner-top-left'),
  topRight: document.getElementById('corner-top-right'),
  bottomLeft: document.getElementById('corner-bottom-left'),
  bottomRight: document.getElementById('corner-bottom-right')
};

const STAGES = {
  seeding: { label: 'Seeding', time: 'timed_seeding_time_per_event_ms', quality: 'timed_seeding' },
  ckf: { label: 'CKF', time: 'timed_ckf_time_per_event_ms', quality: 'timed_ckf' },
  ambiguity: { label: 'Ambiguity', time: 'timed_ambiguity_time_per_event_ms', quality: 'timed_ambiguity' },
  full_chain: { label: 'Full chain', time: 'timed_total_time_per_event_ms', quality: null }
};
const QUALITY_METRICS = [
  ['particle_efficiency', 'Particle efficiency'],
  ['track_efficiency', 'Track efficiency'],
  ['particle_fake_ratio', 'Particle fake ratio'],
  ['track_fake_ratio', 'Track fake ratio'],
  ['particle_duplicate_ratio', 'Particle duplicate ratio'],
  ['track_duplicate_ratio', 'Track duplicate ratio']
];
const TOOLTIP_ROWS = [
  { label: 'T', type: 'time' },
  { label: 'E', type: 'quality', suffix: 'particle_efficiency' },
  { label: 'F', type: 'quality', suffix: 'particle_fake_ratio' },
  { label: 'D', type: 'quality', suffix: 'particle_duplicate_ratio' }
];
const TOOLTIP_STAGES = ['seeding', 'ckf', 'ambiguity'];
const TIMED_PEAK_RSS_KEY = 'timed_peak_rss_kb';
const AXES = ['x', 'y'];

function option(select, value, label) {
  const element = document.createElement('option');
  element.value = value;
  element.textContent = label;
  select.appendChild(element);
}

option(datasetSelect, 'Development', 'Development');
option(datasetSelect, 'Evaluation', 'Evaluation');
datasetSelect.value = REPORT.dataset === 'evaluation' ? 'Evaluation' : 'Development';

function scopedRows() {
  return rows.filter((row) => row.category === datasetSelect.value);
}
function updateBaselineOptions() {
  const names = [...new Set(scopedRows().map((row) => row.candidate))].sort();
  baselineSelect.replaceChildren();
  names.forEach((name) => option(baselineSelect, name, name));
  baselineSelect.value = names.includes(DEFAULTS.baseline) ? DEFAULTS.baseline : (names[0] || '');
}
function axisElements(axis) {
  return {
    kind: document.getElementById(`${axis}-kind`),
    stage: document.getElementById(`${axis}-stage`),
    stageLabel: document.getElementById(`${axis}-stage-label`),
    metric: document.getElementById(`${axis}-metric`),
    metricLabel: document.getElementById(`${axis}-metric-label`)
  };
}
function updateAxisOptions(axis) {
  const elements = axisElements(axis);
  const rssSelected = elements.kind.value === 'rss';
  elements.stageLabel.hidden = rssSelected;
  elements.metricLabel.hidden = rssSelected || elements.kind.value === 'time';
  if (rssSelected) return;

  const previousStage = elements.stage.value;
  const previousMetric = elements.metric.value;
  elements.stage.replaceChildren();
  Object.entries(STAGES)
    .filter(([key]) => elements.kind.value === 'time' || key !== 'full_chain')
    .forEach(([key, stage]) => option(elements.stage, key, stage.label));
  elements.stage.value = [...elements.stage.options].some((item) => item.value === previousStage)
    ? previousStage
    : elements.stage.options[0]?.value || '';
  elements.metric.replaceChildren();
  if (elements.kind.value === 'time') {
    option(elements.metric, 'time_per_event', 'Time per event');
  } else {
    QUALITY_METRICS.forEach(([value, label]) => option(elements.metric, value, label));
  }
  elements.metric.value = [...elements.metric.options].some((item) => item.value === previousMetric)
    ? previousMetric
    : elements.metric.options[0]?.value || '';
}
function axisKey(axis) {
  const elements = axisElements(axis);
  if (elements.kind.value === 'rss') return TIMED_PEAK_RSS_KEY;
  if (elements.kind.value === 'time') return STAGES[elements.stage.value].time;
  return `timed_${elements.stage.value}_${elements.metric.value}`;
}
function axisLabel(axis) {
  const elements = axisElements(axis);
  if (elements.kind.value === 'rss') return 'PEAK RSS';
  const stageLabel = STAGES[elements.stage.value].label;
  if (elements.kind.value === 'time') return `${stageLabel} TIME/EVENT`.toUpperCase();
  const metricLabel = QUALITY_METRICS.find(([value]) => value === elements.metric.value)?.[1] || elements.metric.value;
  return `${stageLabel} ${metricLabel}`.toUpperCase();
}
function axisDefaults(axis, defaultKey) {
  const elements = axisElements(axis);
  const timeStage = Object.entries(STAGES).find(([, stage]) => stage.time === defaultKey);
  const qualityMatch = /^timed_(seeding|ckf|ambiguity)_(.+)$/.exec(defaultKey || '');
  if (defaultKey === TIMED_PEAK_RSS_KEY) {
    elements.kind.value = 'rss';
    updateAxisOptions(axis);
  } else if (timeStage) {
    elements.kind.value = 'time';
    updateAxisOptions(axis);
    elements.stage.value = timeStage[0];
  } else if (qualityMatch) {
    elements.kind.value = 'metric';
    updateAxisOptions(axis);
    elements.stage.value = qualityMatch[1];
    updateAxisOptions(axis);
    elements.metric.value = qualityMatch[2];
  } else {
    elements.kind.value = axis === 'x' ? 'time' : 'metric';
    updateAxisOptions(axis);
  }
}
AXES.forEach((axis) => {
  const elements = axisElements(axis);
  option(elements.kind, 'time', 'Time');
  option(elements.kind, 'metric', 'Metric');
  option(elements.kind, 'rss', 'RSS');
});
axisDefaults('x', DEFAULTS.x_metric);
axisDefaults('y', DEFAULTS.y_metric);
updateBaselineOptions();

function formatPeakRss(value, unavailable = 'Unavailable') {
  if (!Number.isFinite(value)) return unavailable;
  const mebibytes = value / 1024;
  if (mebibytes >= 1024) return `${(mebibytes / 1024).toFixed(2)} GiB`;
  if (mebibytes >= 1) return `${mebibytes.toFixed(1)} MiB`;
  return `${value.toFixed(0)} KiB`;
}
function formatAxisValue(axis, value) {
  if (!Number.isFinite(value)) return 'Unavailable';
  const elements = axisElements(axis);
  if (elements.kind.value === 'rss') return formatPeakRss(value);
  return elements.kind.value === 'time' ? `${value.toFixed(2)} ms` : `${(value * 100).toFixed(2)}%`;
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
}
function formatTooltipValue(value, type) {
  if (!Number.isFinite(value)) return 'n/a';
  return type === 'time' ? `${value.toFixed(2)} ms` : `${(value * 100).toFixed(2)}%`;
}
function tooltipValue(row, stageKey, metric) {
  const stage = STAGES[stageKey];
  if (metric.type === 'quality' && !stage.quality) return 'n/a';
  const key = metric.type === 'time' ? stage.time : `${stage.quality}_${metric.suffix}`;
  return formatTooltipValue(row.metrics[key], metric.type);
}
function timingEvidenceTooltip(row) {
  const evidence = row.timing_evidence;
  if (!evidence) return '';
  const runs = evidence.runs?.length ? evidence.runs : [evidence];
  const repetitions = runs.map((run, index) => {
    const values = run.repetitions.map((item) => `${item.time_per_event_ms.toFixed(2)}`).join(', ');
    return `${runs.length > 1 ? `run ${index + 1}: ` : ''}[${values}] ms`;
  }).join('<br>');
  const claim = row.speed_claim ? `<br>Speed claim&nbsp;&nbsp;${escapeHtml(row.speed_claim.classification)}` : '';
  return `<br>Repetitions&nbsp;&nbsp;${repetitions}<br>Median/range/MAD&nbsp;&nbsp;${evidence.median_ms.toFixed(2)} / ${evidence.range_ms.toFixed(2)} / ${evidence.median_absolute_deviation_ms.toFixed(2)} ms${claim}`;
}
function candidateTooltip(row) {
  const stageKeys = TOOLTIP_STAGES;
  const stageHeading = stageKeys.map((stageKey) => STAGES[stageKey].label).join('&nbsp;&nbsp;→&nbsp;&nbsp;');
  const metricLines = TOOLTIP_ROWS.map((metric) => {
    const values = stageKeys.map((stageKey) => tooltipValue(row, stageKey, metric));
    return `${metric.label}&nbsp;&nbsp;&nbsp;${values.join('&nbsp;→&nbsp;')}`;
  }).join('<br>');
  const peakRss = formatPeakRss(row.metrics[TIMED_PEAK_RSS_KEY], 'n/a');
  const hypothesis = row.proposal ? `<br>Hypothesis&nbsp;&nbsp;${escapeHtml(row.proposal.hypothesis)}` : '';
  return `<b>${escapeHtml(row.candidate)}</b><br><span style="font-family:monospace">Stage&nbsp;&nbsp;${stageHeading}<br>${metricLines}<br>Peak RSS&nbsp;&nbsp;${peakRss}${timingEvidenceTooltip(row)}${hypothesis}</span>`;
}
function validCommitUrl(value) {
  return typeof value === 'string'
    && (value === 'https://github.com/Aksth070600/autoresearch-acts-seeding'
      || /^https:\/\/github\.com\/Aksth070600\/autoresearch-acts-seeding\/commit\/[0-9a-f]{40}$/i.test(value));
}
function registerCommitClickHandler() {
  const chart = document.getElementById('chart');
  if (chart.commitClickHandler) chart.removeListener?.('plotly_click', chart.commitClickHandler);
  chart.commitClickHandler = (event) => {
    const url = event.points?.[0]?.customdata;
    if (validCommitUrl(url)) window.open(url, '_blank', 'noopener,noreferrer');
  };
  chart.on('plotly_click', chart.commitClickHandler);
}
function updatePointCursors(points) {
  document.querySelectorAll('#chart .point').forEach((point, index) => {
    point.style.cursor = validCommitUrl(points[index]?.commit_url) ? 'pointer' : 'default';
  });
}
function axisDirection(axis) {
  const elements = axisElements(axis);
  if (elements.kind.value === 'rss') return { lowerBetter: true, good: 'lower peak RSS', bad: 'higher peak RSS' };
  if (elements.kind.value === 'time') return { lowerBetter: true, good: 'faster', bad: 'slower' };
  const metric = elements.metric.value;
  if (metric.includes('efficiency')) return { lowerBetter: false, good: 'higher efficiency', bad: 'lower efficiency' };
  if (metric.includes('fake_ratio')) return { lowerBetter: true, good: 'lower fake rate', bad: 'higher fake rate' };
  return { lowerBetter: true, good: 'lower duplicate rate', bad: 'higher duplicate rate' };
}
function badge(text, good) {
  return `<span class="corner-badge ${good ? 'better' : 'worse'}">${text.toUpperCase()}</span>`;
}
function renderCornerOverlays(baseline) {
  if (!baseline) {
    Object.values(cornerOverlays).forEach((overlay) => { overlay.replaceChildren(); });
    return;
  }
  const x = axisDirection('x');
  const y = axisDirection('y');
  const badges = (xLower, yHigher) => {
    const xGood = x.lowerBetter === xLower;
    const yGood = y.lowerBetter !== yHigher;
    return `${badge(xGood ? x.good : x.bad, xGood)}${badge(yGood ? y.good : y.bad, yGood)}`;
  };
  cornerOverlays.topLeft.innerHTML = badges(true, true);
  cornerOverlays.topRight.innerHTML = badges(false, true);
  cornerOverlays.bottomLeft.innerHTML = badges(true, false);
  cornerOverlays.bottomRight.innerHTML = badges(false, false);
}
function quadrantFill(xLower, yHigher) {
  const x = axisDirection('x');
  const y = axisDirection('y');
  const good = Number(x.lowerBetter === xLower) + Number(y.lowerBetter !== yHigher);
  if (good === 2) return 'rgba(34,197,94,0.14)';
  if (good === 0) return 'rgba(239,68,68,0.14)';
  return 'rgba(234,179,8,0.14)';
}
function candidateColor(row, baseline, xKey, yKey) {
  if (!baseline) return '#94a3b8';
  if (row.candidate === baselineSelect.value) return '#fbbf24';
  const x = axisDirection('x');
  const y = axisDirection('y');
  const xBetter = x.lowerBetter ? row.metrics[xKey] <= baseline.metrics[xKey] : row.metrics[xKey] >= baseline.metrics[xKey];
  const yBetter = y.lowerBetter ? row.metrics[yKey] <= baseline.metrics[yKey] : row.metrics[yKey] >= baseline.metrics[yKey];
  if (xBetter && yBetter) return '#22c55e';
  if (!xBetter && !yBetter) return '#ef4444';
  return '#eab308';
}
function validRows(xKey, yKey) {
  return scopedRows().filter((row) => Number.isFinite(row.metrics[xKey]) && Number.isFinite(row.metrics[yKey]));
}
function axisPlotValue(axis, value) {
  return axisElements(axis).kind.value === 'rss' ? value / 1024 : value;
}
function paddedRange(points, key, axis) {
  const values = points.map((row) => axisPlotValue(axis, row.metrics[key]));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = maximum - minimum || Math.max(Math.abs(maximum), 1);
  return [minimum - span * 0.20, maximum + span * 0.20];
}
function axisTickFormat(axis) {
  const kind = axisElements(axis).kind.value;
  if (kind === 'rss') return { tickformat: '.1f', ticksuffix: ' MiB' };
  return kind === 'time' ? { tickformat: '.0f', ticksuffix: ' ms' } : { tickformat: '.3%' };
}
function baselineLabel(name, row) {
  return row && Number.isFinite(row.sample_count) ? `${name} (${row.sample_count})` : (name || 'Unavailable');
}
function render() {
  const xKey = axisKey('x');
  const yKey = axisKey('y');
  const points = validRows(xKey, yKey);
  const baselineName = baselineSelect.value;
  const baseline = points.find((row) => row.candidate === baselineName);
  const xLabel = axisLabel('x');
  const yLabel = axisLabel('y');
  summaryCount.textContent = String(points.length);
  summaryBaseline.textContent = baselineLabel(baselineName, baseline);
  summaryXValue.textContent = baseline ? formatAxisValue('x', baseline.metrics[xKey]) : 'Unavailable';
  summaryXLabel.textContent = xLabel;
  summaryYValue.textContent = baseline ? formatAxisValue('y', baseline.metrics[yKey]) : 'Unavailable';
  summaryYLabel.textContent = yLabel;
  const xDirection = axisDirection('x').lowerBetter ? 'Lower' : 'Higher';
  const yDirection = axisDirection('y').lowerBetter ? 'Lower' : 'Higher';
  axisGuidance.textContent = `${xDirection} X is better. ${yDirection} Y is better. The reference lines show the selected baseline.`;
  renderCornerOverlays(baseline);
  emptyState.hidden = points.length !== 0;
  if (!points.length) {
    Plotly.purge('chart');
    return;
  }
  const traces = [{
    x: points.map((row) => axisPlotValue('x', row.metrics[xKey])),
    y: points.map((row) => axisPlotValue('y', row.metrics[yKey])),
    text: points.map((row) => candidateTooltip(row)),
    customdata: points.map((row) => row.commit_url || ''),
    mode: 'markers', type: 'scatter', name: 'Candidates',
    marker: { size: points.map((row) => row.candidate === baselineName ? 16 : 12), symbol: points.map((row) => row.candidate === baselineName ? 'star' : 'circle'), color: points.map((row) => candidateColor(row, baseline, xKey, yKey)), line: { width: 1, color: '#e2e8f0' } },
    hovertemplate: '%{text}<extra></extra>'
  }];
  const xRange = paddedRange(points, xKey, 'x');
  const yRange = paddedRange(points, yKey, 'y');
  const shapes = [];
  if (baseline) {
    const bx = axisPlotValue('x', baseline.metrics[xKey]);
    const by = axisPlotValue('y', baseline.metrics[yKey]);
    [
      [xRange[0], bx, by, yRange[1], true, true],
      [bx, xRange[1], by, yRange[1], false, true],
      [xRange[0], bx, yRange[0], by, true, false],
      [bx, xRange[1], yRange[0], by, false, false]
    ].forEach(([x0, x1, y0, y1, xLower, yHigher]) => {
      shapes.push({ type: 'rect', x0, x1, y0, y1, layer: 'below', fillcolor: quadrantFill(xLower, yHigher), line: { width: 0 } });
    });
    shapes.push({ type: 'line', x0: bx, x1: bx, y0: 0, y1: 1, yref: 'paper', layer: 'below', line: { color: 'rgba(96,165,250,0.55)', width: 2 } });
    shapes.push({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: by, y1: by, layer: 'below', line: { color: 'rgba(96,165,250,0.55)', width: 2 } });
  }
  Plotly.react('chart', traces, {
    xaxis: { ...axisTickFormat('x'), range: xRange, zeroline: false, showgrid: true, gridcolor: 'rgba(71,85,105,0.35)', tickfont: { color: '#cbd5e1', size: 14 } },
    yaxis: { ...axisTickFormat('y'), range: yRange, zeroline: false, showgrid: true, gridcolor: 'rgba(71,85,105,0.35)', tickfont: { color: '#cbd5e1', size: 14 } },
    hovermode: 'closest', shapes, margin: { l: 80, r: 30, t: 45, b: 55 },
    legend: { orientation: 'h', x: 0, y: 1.12, xanchor: 'left', yanchor: 'bottom', font: { color: '#cbd5e1' } },
    paper_bgcolor: '#111827', plot_bgcolor: '#0b1120', font: { color: '#cbd5e1' }
  }, { responsive: true, displaylogo: false }).then(() => {
    updatePointCursors(points);
    registerCommitClickHandler();
  });
}
AXES.forEach((axis) => {
  const elements = axisElements(axis);
  elements.kind.addEventListener('change', () => { updateAxisOptions(axis); render(); });
  elements.stage.addEventListener('change', render);
  elements.metric.addEventListener('change', render);
});
datasetSelect.addEventListener('change', () => { updateBaselineOptions(); render(); });
baselineSelect.addEventListener('change', render);
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
