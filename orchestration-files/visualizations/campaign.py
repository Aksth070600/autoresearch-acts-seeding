"""Render the public live-campaign dashboard shell."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from campaign_status import StatusError, validate_ref


REPOSITORY = "Aksth070600/autoresearch-acts-seeding"
POLL_INTERVAL_MS = 60_000


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ACTS Seeding Live Campaign</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root { color-scheme: dark; font-family: system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #0b1120; color: #e5e7eb; }
    main { max-width: 1280px; margin: 0 auto; padding: 24px; }
    a { color: #a5b4fc; text-underline-offset: 3px; }
    a:hover { color: #c4b5fd; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 8px; }
    h2 { margin-bottom: 12px; font-size: 1.2rem; }
    .controls { background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
    label { display: grid; gap: 5px; font-size: 0.9rem; font-weight: 650; }
    select { min-width: 0; width: 100%; padding: 8px 10px; border: 1px solid #475569; border-radius: 6px;
      background: #1e293b; color: #e5e7eb; font: inherit; }
    .notice { margin-top: 12px; padding: 11px 13px; border: 1px solid #475569; border-radius: 8px; background: #111827; }
    .notice.error { border-color: #b45309; color: #fed7aa; background: rgba(120,53,15,0.18); }
    [hidden] { display: none !important; }
    #empty-state { min-height: 270px; display: grid; place-items: center; margin-top: 14px; padding: 32px;
      text-align: center; color: #94a3b8; background: #111827; border: 1px solid #334155; border-radius: 10px; }
    #empty-state strong { display: block; margin-bottom: 7px; color: #e2e8f0; font-size: 1.05rem; }
    .campaign-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 22px 0 12px; }
    .campaign-heading h2 { margin: 0; }
    .chips { display: flex; flex-wrap: wrap; gap: 7px; }
    .chip { display: inline-flex; align-items: center; width: max-content; max-width: 100%; padding: 4px 9px;
      border: 1px solid #475569; border-radius: 999px; color: #cbd5e1; background: #1e293b;
      font-size: 0.76rem; font-weight: 700; }
    .chip.good { color: #bbf7d0; border-color: #15803d; background: rgba(20,83,45,0.35); }
    .chip.warn { color: #fde68a; border-color: #a16207; background: rgba(113,63,18,0.35); }
    .chip.bad { color: #fecaca; border-color: #b91c1c; background: rgba(127,29,29,0.35); }
    .grid { display: grid; gap: 12px; }
    .progress-grid, .timing-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 12px; }
    .results-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .card { min-width: 0; min-height: 82px; padding: 12px 14px; background: #111827;
      border: 1px solid #334155; border-radius: 12px; }
    .result-card { display: block; color: inherit; text-decoration: none; }
    .result-card[href] { cursor: pointer; }
    .result-card[href]:hover, .result-card[href]:focus-visible { border-color: #818cf8; background: #172033; }
    .card-label { display: block; margin-bottom: 5px; color: #94a3b8; font-size: 0.75rem; font-weight: 750;
      letter-spacing: 0.05em; text-transform: uppercase; }
    .card-name { display: block; margin-bottom: 5px; overflow-wrap: anywhere; color: #f8fafc;
      font-size: 0.9rem; font-weight: 750; }
    .card-value { display: block; overflow-wrap: anywhere; color: #f8fafc; font-size: 1.05rem; font-weight: 750; }
    .card-note { display: block; margin-top: 5px; color: #94a3b8; font-size: 0.79rem; line-height: 1.35; }
    .progress-track { height: 6px; margin-top: 10px; overflow: hidden; border-radius: 999px; background: #334155; }
    .progress-fill { display: block; width: 0; height: 100%; border-radius: inherit; background: #818cf8; transition: width 220ms ease; }
    .progress-fill.good { background: #22c55e; }
    .progress-fill.warn { background: #eab308; }
    .section { margin-top: 24px; }
    .section-heading { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
    .note { color: #94a3b8; font-size: 0.86rem; }
    #chart-frame { position: relative; height: 615px; margin-top: 8px; background: #111827;
      border: 1px solid #334155; border-radius: 10px; overflow: hidden; }
    #chart { width: 100%; height: 100%; }
    #chart .point { cursor: pointer; }
    #plot-empty { position: absolute; inset: 0; display: grid; place-items: center; padding: 24px;
      color: #94a3b8; text-align: center; pointer-events: none; }
    .attempt-head, .attempt summary { display: grid; grid-template-columns: 1.25fr 1.25fr .72fr .72fr .8fr .9fr .9fr .8fr;
      gap: 10px; align-items: center; }
    .attempt-head { padding: 0 34px 7px 14px; color: #94a3b8; font-size: 0.7rem; font-weight: 750;
      letter-spacing: 0.04em; text-transform: uppercase; }
    .attempts { display: grid; gap: 7px; }
    .attempt { background: #111827; border: 1px solid #334155; border-radius: 9px; }
    .attempt[open] { border-color: #475569; }
    .attempt summary { min-height: 58px; padding: 9px 12px; cursor: pointer; list-style-position: inside; }
    .attempt summary:hover { background: rgba(30,41,59,0.55); }
    .attempt-cell { min-width: 0; overflow-wrap: anywhere; font-size: 0.85rem; }
    .attempt-cell strong { color: #f8fafc; }
    .attempt-cell .mobile-label { display: none; color: #94a3b8; font-size: 0.67rem; font-weight: 750;
      letter-spacing: 0.04em; text-transform: uppercase; }
    .attempt-detail { display: grid; grid-template-columns: 1fr auto; gap: 12px; margin: 0 12px 12px; padding: 11px 12px;
      color: #cbd5e1; background: #0b1120; border-radius: 7px; font-size: 0.84rem; }
    .attempt-detail p { margin: 0; }
    .evidence-links { display: flex; flex-wrap: wrap; gap: 9px; }
    code { background: #334155; padding: 2px 5px; border-radius: 4px; }
    @media (max-width: 950px) {
      .timing-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .attempt-head { display: none; }
      .attempt summary { grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 12px 14px; }
      .attempt-cell .mobile-label { display: block; margin-bottom: 2px; }
    }
    @media (max-width: 700px) {
      main { padding: 18px; }
      .campaign-heading, .section-heading { align-items: flex-start; flex-direction: column; }
      .progress-grid, .results-grid { grid-template-columns: 1fr; }
      #chart-frame { height: 510px; }
      .attempt-detail { grid-template-columns: 1fr; }
    }
    @media (max-width: 470px) {
      .timing-grid { grid-template-columns: 1fr; }
      .attempt summary { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<main>
  <h1>ACTS Seeding Live Campaign</h1>

  <section class="controls" aria-label="Campaign selection">
    <label>Campaign
      <select id="campaign-select" disabled>
        <option>Discovering public campaigns…</option>
      </select>
    </label>
  </section>
  <div id="fetch-error" class="notice error" role="alert" hidden></div>
  <div id="empty-state">
    <div><strong>Discovering public campaigns</strong>Loading the campaign list once, without credentials.</div>
  </div>

  <div id="dashboard" hidden>
    <div class="campaign-heading">
      <h2>ACTS Seeding Campaign</h2>
      <div class="chips">
        <span id="campaign-lifecycle" class="chip"></span>
        <span id="freshness" class="chip"></span>
      </div>
    </div>

    <section class="grid progress-grid" aria-label="Campaign progress">
      <div class="card"><span class="card-label">Completed attempts</span><strong id="completed-progress" class="card-value"></strong><div class="progress-track"><span id="completed-bar" class="progress-fill"></span></div></div>
      <div class="card"><span class="card-label">Structural attempts</span><strong id="structural-progress" class="card-value"></strong><div class="progress-track"><span id="structural-bar" class="progress-fill"></span></div></div>
      <div class="card"><span class="card-label">Micro-optimizations</span><strong id="micro-progress" class="card-value"></strong><div class="progress-track"><span id="micro-bar" class="progress-fill warn"></span></div></div>
    </section>

    <section class="grid timing-grid" aria-label="Campaign timing">
      <div class="card"><span class="card-label">Elapsed</span><strong id="elapsed" class="card-value"></strong></div>
      <div class="card"><span class="card-label">Estimated remaining</span><strong id="remaining" class="card-value"></strong></div>
      <div class="card"><span class="card-label">Expected finish</span><strong id="expected-finish" class="card-value"></strong></div>
    </section>

    <section class="section" aria-labelledby="results-heading">
      <div class="section-heading">
        <h2 id="results-heading">Promising Early Results</h2>
      </div>
      <div id="seeding-leaders" class="grid results-grid"></div>
    </section>

    <section class="section" aria-label="Campaign results comparison">
      <div id="chart-frame">
        <div id="plot-empty" hidden>No complete protocol-compatible Development results yet.</div>
        <div id="chart" role="img" aria-label="Interactive campaign comparison chart"></div>
      </div>
    </section>

    <section class="section" aria-labelledby="history-heading">
      <div class="section-heading">
        <h2 id="history-heading">Attempt history</h2>
        <span id="history-count" class="note"></span>
      </div>
      <div class="attempt-head" aria-hidden="true"><span>Candidate</span><span>Mechanism</span><span>Class</span><span>State</span><span>Duration</span><span>Seeding</span><span>Ambiguity eff.</span><span>Evidence</span></div>
      <div id="attempts" class="attempts"></div>
      <div id="history-empty" class="notice" hidden>No attempt evidence has been recorded for this campaign.</div>
    </section>
  </div>
</main>
<script>
/* CAMPAIGN_DISCOVERY_LOGIC_START */
const REPOSITORY = '__REPOSITORY__';
const STATUS_PATH = 'campaign-status.json';
const CAMPAIGN_BRANCH_PREFIX = 'autoresearch-acts-seeding/';

function safeRef(raw) {
  if (typeof raw !== 'string') return null;
  const ref = raw.trim();
  const forbidden = ['..', '@{', '\\', '~', '^', ':', '?', '*', '['];
  if (!ref || ref.length > 200 || /^[/.\-]/.test(ref) || /[/.]$/.test(ref)
      || ref.includes('//') || forbidden.some((token) => ref.includes(token))
      || [...ref].some((character) => character.charCodeAt(0) < 33 || character.charCodeAt(0) === 127)
      || !/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(ref)) return null;
  if (ref.split('/').some((part) => !part || part === '.' || part === '..' || part.startsWith('.') || part.endsWith('.lock'))) return null;
  return ref;
}
function safeSha(raw) {
  return typeof raw === 'string' && /^[0-9a-f]{40}$/i.test(raw) ? raw.toLowerCase() : null;
}
function campaignFromPull(pull) {
  if (!pull || !Number.isInteger(pull.number) || !['open', 'closed'].includes(pull.state)
      || !Number.isFinite(Date.parse(pull.created_at)) || pull.head?.repo?.full_name !== REPOSITORY) return null;
  const ref = safeRef(pull.head?.ref);
  if (!ref || !ref.startsWith(CAMPAIGN_BRANCH_PREFIX)) return null;
  let pullUrl = null;
  try {
    const candidateUrl = new URL(pull.html_url);
    if (candidateUrl.protocol === 'https:' && candidateUrl.hostname === 'github.com'
        && candidateUrl.pathname === `/${REPOSITORY}/pull/${pull.number}`) pullUrl = candidateUrl.href;
  } catch (_) { return null; }
  if (!pullUrl) return null;
  return {
    id: `pr-${pull.number}`,
    number: pull.number,
    title: typeof pull.title === 'string' && pull.title.trim() ? pull.title.trim().slice(0, 160) : ref,
    ref,
    sha: safeSha(pull.head?.sha),
    createdAt: new Date(pull.created_at).toISOString(),
    state: pull.state,
    pullUrl
  };
}
function sortCampaigns(pulls) {
  if (!Array.isArray(pulls)) return [];
  return pulls.map(campaignFromPull).filter(Boolean).sort((left, right) =>
    Date.parse(right.createdAt) - Date.parse(left.createdAt) || right.number - left.number
  );
}
function directCampaign(rawRef) {
  const ref = safeRef(rawRef);
  if (!ref) return null;
  return {
    id: `direct-${ref}`,
    number: null,
    title: 'Direct campaign ref',
    ref,
    sha: safeSha(ref),
    createdAt: null,
    state: 'direct',
    pullUrl: null
  };
}
function selectInitialCampaign(campaigns, deepLinkRef) {
  const ref = safeRef(deepLinkRef);
  if (ref) {
    return campaigns.find((campaign) => campaign.ref === ref || campaign.sha === ref)
      || directCampaign(ref);
  }
  return campaigns[0] || null;
}
function campaignFetchSource(campaign) {
  if (!campaign) return null;
  const branch = safeRef(campaign.ref);
  const immutableSha = campaign.state === 'closed' ? safeSha(campaign.sha) : null;
  const directSha = campaign.state === 'direct' ? safeSha(campaign.ref) : null;
  if (immutableSha || directSha) {
    return {
      fetchRef: immutableSha || directSha,
      expectedBranch: directSha ? null : branch,
      immutable: true,
      poll: false
    };
  }
  if (!branch) return null;
  return {
    fetchRef: `refs/heads/${branch}`,
    expectedBranch: branch,
    immutable: false,
    poll: campaign.state !== 'closed'
  };
}
function snapshotUrl(source, cacheBuster = Date.now()) {
  if (!source || !safeRef(source.fetchRef)) return null;
  const encodedRef = source.fetchRef.split('/').map(encodeURIComponent).join('/');
  return `https://raw.githubusercontent.com/${REPOSITORY}/${encodedRef}/${STATUS_PATH}?_=${cacheBuster}`;
}
function topSeedingAttempts(attempts) {
  if (!Array.isArray(attempts)) return [];
  return attempts
    .filter((attempt) => attempt?.candidate !== 'Genesis'
      && attempt?.state === 'completed'
      && Number.isFinite(attempt?.timed_seeding_time_per_event_ms))
    .sort((left, right) => left.timed_seeding_time_per_event_ms - right.timed_seeding_time_per_event_ms)
    .slice(0, 3);
}
function seedingComparison(result, genesis) {
  const resultMs = result?.timed_seeding_time_per_event_ms;
  const genesisMs = genesis?.timed_seeding_time_per_event_ms;
  if (!Number.isFinite(resultMs) || !Number.isFinite(genesisMs) || genesisMs === 0) return null;
  return {
    deltaMs: resultMs - genesisMs,
    percentage: (resultMs - genesisMs) / genesisMs * 100
  };
}
function humanizeCandidateName(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z][a-z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}
/* CAMPAIGN_DISCOVERY_LOGIC_END */

const POLL_INTERVAL_MS = __POLL_INTERVAL_MS__;
const PULLS_API_URL = `https://api.github.com/repos/${REPOSITORY}/pulls?state=all&per_page=100&sort=created&direction=desc`;
const campaignSelect = document.getElementById('campaign-select');
const fetchError = document.getElementById('fetch-error');
const emptyState = document.getElementById('empty-state');
const dashboard = document.getElementById('dashboard');
const lastGoodSnapshots = new Map();
const lastFetchStarted = new Map();
let discoveredCampaigns = [];
let activeCampaign = null;

function finite(value) { return typeof value === 'number' && Number.isFinite(value); }
function validObjective(value) { return value === null || finite(value); }
function validateSnapshot(value, expectedBranch) {
  const snapshotBranch = safeRef(value?.campaign?.branch);
  if (!value || typeof value !== 'object' || value.schema_version !== '1.0.0'
      || value.protocol_id !== 'acts-seeding-v2' || !snapshotBranch
      || (expectedBranch && snapshotBranch !== expectedBranch)
      || !value.progress || !value.promising_results || !Array.isArray(value.attempts)
      || !Array.isArray(value.blockers) || !Array.isArray(value.failures)
      || !Number.isFinite(Date.parse(value.generated_at))) {
    throw new Error('The fetched file is not a compatible campaign-status v1 snapshot.');
  }
  const target = value.campaign.targets;
  if (!target || !finite(target.completed_attempts) || !finite(target.structural_attempts)
      || !finite(target.micro_optimization_cap)) {
    throw new Error('The campaign snapshot has invalid targets.');
  }
  for (const attempt of value.attempts) {
    if (!attempt || typeof attempt.candidate !== 'string'
        || !['baseline', 'structural', 'micro'].includes(attempt.classification)
        || !validObjective(attempt.timed_seeding_time_per_event_ms)
        || !validObjective(attempt.timed_ambiguity_particle_efficiency)) {
      throw new Error('The campaign snapshot has invalid attempt evidence.');
    }
  }
  return value;
}
function setText(id, value) { document.getElementById(id).textContent = value; }
function unavailable(value) { return value === null || value === undefined || value === ''; }
function formatDuration(seconds) {
  if (!finite(seconds)) return 'Unavailable';
  const rounded = Math.max(0, Math.round(seconds));
  const days = Math.floor(rounded / 86400);
  const hours = Math.floor((rounded % 86400) / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${rounded}s`;
}
function formatInstant(value) {
  if (!value || !Number.isFinite(Date.parse(value))) return 'Unavailable';
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit'
  }).format(new Date(value));
}
function formatRelative(value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return 'unknown time';
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
function formatMs(value) { return finite(value) ? `${value.toFixed(2)} ms/event` : 'Unavailable'; }
function formatEfficiency(value) { return finite(value) ? `${(value * 100).toFixed(2)}%` : 'Unavailable'; }
function formatSigned(value) {
  if (!finite(value)) return 'Unavailable';
  const sign = value < 0 ? '−' : value > 0 ? '+' : '';
  return `${sign}${Math.abs(value).toFixed(2)}`;
}
function freshnessState(snapshot) {
  const updated = Date.parse(snapshot.generated_at);
  const age = Math.max(0, (Date.now() - updated) / 1000);
  const staleAfter = finite(snapshot.stale_after_seconds) ? snapshot.stale_after_seconds : 900;
  if (age >= staleAfter) return { className: 'bad' };
  if (age >= staleAfter / 2) return { className: 'warn' };
  return { className: 'good' };
}
function renderFreshness(snapshot, campaign = activeCampaign) {
  const element = document.getElementById('freshness');
  if (campaign?.state !== 'open') {
    element.hidden = true;
    return;
  }
  const freshness = freshnessState(snapshot);
  element.hidden = false;
  element.textContent = `Update · ${formatRelative(snapshot.generated_at)}`;
  element.className = `chip ${freshness.className}`;
}
function safeLink(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com') return null;
    if (url.pathname === `/${REPOSITORY}` || url.pathname === `/${REPOSITORY}/`) {
      return `https://github.com/${REPOSITORY}`;
    }
    if (!url.pathname.startsWith(`/${REPOSITORY}/`)) return null;
    if (!/^\/(Aksth070600\/autoresearch-acts-seeding)\/(commit|blob|tree|pull)\//.test(url.pathname)) return null;
    return url.href;
  } catch (_) { return null; }
}
function link(label, href) {
  const safe = safeLink(href);
  if (!safe) return null;
  const anchor = document.createElement('a');
  anchor.textContent = label;
  anchor.href = safe;
  anchor.target = '_blank';
  anchor.rel = 'noopener noreferrer';
  return anchor;
}
function setProgress(valueId, barId, current, target, cap = false) {
  setText(valueId, `${current} / ${target}`);
  const percentage = target > 0 ? Math.min(current / target * 100, 100) : 0;
  const bar = document.getElementById(barId);
  bar.style.width = `${percentage}%`;
  bar.classList.toggle('good', !cap && current >= target);
  bar.classList.toggle('bad', cap && current > target);
}
function renderSeedingLeaders(snapshot) {
  const container = document.getElementById('seeding-leaders');
  container.replaceChildren();
  const leaders = topSeedingAttempts(snapshot.attempts);
  const genesis = snapshot.promising_results.latest_genesis;
  if (!leaders.length) {
    const card = document.createElement('div');
    card.className = 'card';
    const value = document.createElement('strong');
    value.className = 'card-value';
    value.textContent = 'Waiting for complete Development evidence.';
    card.appendChild(value);
    container.appendChild(card);
    return;
  }
  leaders.forEach((result) => {
    const commitUrl = safeLink(result.links?.commit);
    const card = document.createElement(commitUrl ? 'a' : 'div');
    card.className = 'card result-card';
    if (commitUrl) {
      card.href = commitUrl;
      card.target = '_blank';
      card.rel = 'noopener noreferrer';
      card.setAttribute('aria-label', `Open ${humanizeCandidateName(result.candidate)} implementation commit`);
    }
    const name = document.createElement('span');
    name.className = 'card-name';
    name.textContent = humanizeCandidateName(result.candidate);
    const value = document.createElement('strong');
    value.className = 'card-value';
    value.textContent = formatMs(result.timed_seeding_time_per_event_ms);
    const note = document.createElement('span');
    note.className = 'card-note';
    const comparison = seedingComparison(result, genesis);
    note.textContent = comparison
      ? `${formatSigned(comparison.deltaMs)} ms (${formatSigned(comparison.percentage)}%)`
      : 'Genesis comparison unavailable';
    card.append(name, value, note);
    container.appendChild(card);
  });
}
function evidenceCell(attempt) {
  const wrapper = document.createElement('span');
  wrapper.className = 'evidence-links';
  const record = link('Record', attempt.links?.record);
  const commit = link('Commit', attempt.links?.commit);
  if (record) wrapper.appendChild(record);
  if (commit) wrapper.appendChild(commit);
  if (!wrapper.childElementCount) wrapper.textContent = 'Unavailable';
  return wrapper;
}
function cell(label, content) {
  const wrapper = document.createElement('span');
  wrapper.className = 'attempt-cell';
  const mobile = document.createElement('span');
  mobile.className = 'mobile-label';
  mobile.textContent = label;
  wrapper.appendChild(mobile);
  if (content instanceof Node) wrapper.appendChild(content); else wrapper.appendChild(document.createTextNode(content));
  return wrapper;
}
function attemptElement(attempt) {
  const details = document.createElement('details');
  details.className = 'attempt';
  const summary = document.createElement('summary');
  const candidate = document.createElement('strong');
  candidate.textContent = attempt.candidate;
  const state = document.createElement('span');
  state.className = `chip ${attempt.state === 'completed' ? 'good' : attempt.state === 'failed' ? 'bad' : 'warn'}`;
  state.textContent = attempt.state;
  summary.append(
    cell('Candidate', candidate),
    cell('Mechanism', attempt.mechanism_family || 'Unavailable'),
    cell('Class', attempt.classification || 'Unavailable'),
    cell('State', state),
    cell('Duration', formatDuration(attempt.duration_seconds)),
    cell('Seeding', formatMs(attempt.timed_seeding_time_per_event_ms)),
    cell('Ambiguity eff.', formatEfficiency(attempt.timed_ambiguity_particle_efficiency)),
    cell('Evidence', evidenceCell(attempt))
  );
  const detail = document.createElement('div');
  detail.className = 'attempt-detail';
  const outcome = document.createElement('p');
  outcome.textContent = attempt.outcome || 'Current attempt has no recorded outcome yet.';
  const dates = document.createElement('p');
  dates.textContent = `${formatInstant(attempt.started_at)} → ${formatInstant(attempt.finished_at)}`;
  detail.append(outcome, dates);
  details.append(summary, detail);
  return details;
}
function renderHistory(snapshot) {
  const container = document.getElementById('attempts');
  container.replaceChildren();
  const attempts = [...snapshot.attempts];
  const current = snapshot.current_attempt;
  const currentStarted = current?.started_at ? Date.parse(current.started_at) : NaN;
  const currentRecorded = current && attempts.some((attempt) =>
    attempt.candidate === current.candidate
    && (!Number.isFinite(currentStarted) || Date.parse(attempt.started_at) >= currentStarted)
  );
  if (current && !currentRecorded) {
    const started = currentStarted;
    attempts.push({
      ...current,
      state: current.state,
      duration_seconds: Number.isFinite(started) ? Math.max(0, (Date.now() - started) / 1000) : null,
      timed_seeding_time_per_event_ms: null,
      timed_ambiguity_particle_efficiency: null,
      outcome: `Current controlled stage: ${current.controlled_stage}`,
      finished_at: null,
      links: {}
    });
  }
  attempts.reverse().forEach((attempt) => container.appendChild(attemptElement(attempt)));
  setText('history-count', `${attempts.length} attempt${attempts.length === 1 ? '' : 's'}`);
  document.getElementById('history-empty').hidden = attempts.length !== 0;
}
function comparisonPoints(snapshot) {
  const baseline = snapshot.promising_results.latest_genesis;
  const points = snapshot.attempts.filter((attempt) =>
    attempt.candidate !== 'Genesis'
    && attempt.state === 'completed'
    && finite(attempt.timed_seeding_time_per_event_ms)
    && finite(attempt.timed_ambiguity_particle_efficiency)
  );
  if (baseline
      && finite(baseline.timed_seeding_time_per_event_ms)
      && finite(baseline.timed_ambiguity_particle_efficiency)) {
    points.push({
      ...baseline,
      candidate: 'Genesis',
      links: { ...baseline.links, commit: `https://github.com/${REPOSITORY}` }
    });
  }
  return points;
}
function paddedRange(points, key) {
  const values = points.map((point) => point[key]);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = maximum - minimum || Math.max(Math.abs(maximum), 1);
  return [minimum - span * 0.20, maximum + span * 0.20];
}
function chartCandidateColor(point, baseline) {
  if (!baseline) return '#94a3b8';
  if (point.candidate === 'Genesis') return '#fbbf24';
  const faster = point.timed_seeding_time_per_event_ms <= baseline.timed_seeding_time_per_event_ms;
  const moreEfficient = point.timed_ambiguity_particle_efficiency >= baseline.timed_ambiguity_particle_efficiency;
  if (faster && moreEfficient) return '#22c55e';
  if (!faster && !moreEfficient) return '#ef4444';
  return '#eab308';
}
function quadrantFill(xLower, yHigher) {
  const good = Number(xLower) + Number(yHigher);
  if (good === 2) return 'rgba(34,197,94,0.14)';
  if (good === 0) return 'rgba(239,68,68,0.14)';
  return 'rgba(234,179,8,0.14)';
}
function updatePointCursors(points) {
  document.querySelectorAll('#chart .point').forEach((point, index) => {
    point.style.cursor = safeLink(points[index]?.links?.commit) ? 'pointer' : 'default';
  });
}
function registerChartClickHandler() {
  const chart = document.getElementById('chart');
  if (chart.campaignClickHandler) chart.removeListener?.('plotly_click', chart.campaignClickHandler);
  chart.campaignClickHandler = (event) => {
    const target = safeLink(event.points?.[0]?.customdata);
    if (target) window.open(target, '_blank', 'noopener,noreferrer');
  };
  chart.on('plotly_click', chart.campaignClickHandler);
}
function renderComparisonChart(snapshot) {
  const points = comparisonPoints(snapshot);
  const baseline = points.find((point) => point.candidate === 'Genesis');
  const plotEmpty = document.getElementById('plot-empty');
  plotEmpty.hidden = points.length !== 0;
  if (!points.length || typeof Plotly === 'undefined') {
    if (typeof Plotly !== 'undefined') Plotly.purge('chart');
    if (typeof Plotly === 'undefined') {
      plotEmpty.hidden = false;
      plotEmpty.textContent = 'Interactive chart library could not be loaded.';
    }
    return;
  }
  const xRange = paddedRange(points, 'timed_seeding_time_per_event_ms');
  const yRange = paddedRange(points, 'timed_ambiguity_particle_efficiency');
  const shapes = [];
  if (baseline) {
    const bx = baseline.timed_seeding_time_per_event_ms;
    const by = baseline.timed_ambiguity_particle_efficiency;
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
  const trace = {
    x: points.map((point) => point.timed_seeding_time_per_event_ms),
    y: points.map((point) => point.timed_ambiguity_particle_efficiency),
    text: points.map((point) => `<b>${escapeHtml(humanizeCandidateName(point.candidate))}</b><br>${formatMs(point.timed_seeding_time_per_event_ms)}<br>${formatEfficiency(point.timed_ambiguity_particle_efficiency)}`),
    customdata: points.map((point) => safeLink(point.links?.commit) || ''),
    mode: 'markers', type: 'scatter', name: 'Candidates',
    marker: {
      size: points.map((point) => point.candidate === 'Genesis' ? 16 : 12),
      symbol: points.map((point) => point.candidate === 'Genesis' ? 'star' : 'circle'),
      color: points.map((point) => chartCandidateColor(point, baseline)),
      line: { width: 1, color: '#e2e8f0' }
    },
    hovertemplate: '%{text}<extra></extra>'
  };
  Plotly.react('chart', [trace], {
    xaxis: { tickformat: '.0f', ticksuffix: ' ms', range: xRange, zeroline: false, showgrid: true, gridcolor: 'rgba(71,85,105,0.35)', tickfont: { color: '#cbd5e1', size: 14 } },
    yaxis: { tickformat: '.3%', range: yRange, zeroline: false, showgrid: true, gridcolor: 'rgba(71,85,105,0.35)', tickfont: { color: '#cbd5e1', size: 14 } },
    autosize: true, hovermode: 'closest', shapes, margin: { l: 80, r: 30, t: 45, b: 55 },
    legend: { orientation: 'h', x: 0, y: 1.12, xanchor: 'left', yanchor: 'bottom', font: { color: '#cbd5e1' } },
    paper_bgcolor: '#111827', plot_bgcolor: '#0b1120', font: { color: '#cbd5e1' }
  }, { responsive: true, displaylogo: false }).then(() => {
    updatePointCursors(points);
    registerChartClickHandler();
  });
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}
function renderSnapshot(snapshot, campaign) {
  const lifecycle = document.getElementById('campaign-lifecycle');
  lifecycle.textContent = campaign?.state === 'closed' ? 'Completed' : campaign?.state === 'open' ? 'Running' : 'Direct ref';
  lifecycle.className = `chip ${campaign?.state === 'open' ? 'good' : ''}`.trim();
  const progress = snapshot.progress;
  const targets = snapshot.campaign.targets;
  setProgress('completed-progress', 'completed-bar', progress.completed_attempts, targets.completed_attempts);
  setProgress('structural-progress', 'structural-bar', progress.structural_attempts, targets.structural_attempts);
  setProgress('micro-progress', 'micro-bar', progress.micro_optimizations, targets.micro_optimization_cap, true);
  setText('elapsed', formatDuration(progress.elapsed_seconds));
  setText('remaining', formatDuration(progress.estimated_remaining_seconds));
  setText('expected-finish', formatInstant(progress.expected_finish_at));
  renderFreshness(snapshot, campaign);
  renderSeedingLeaders(snapshot);
  renderComparisonChart(snapshot);
  renderHistory(snapshot);
  emptyState.hidden = true;
  dashboard.hidden = false;
  document.title = 'ACTS Seeding Campaign · Live Dashboard';
}
function setFetchError(message) {
  fetchError.textContent = message;
  fetchError.hidden = false;
}
function campaignLabel(campaign) {
  const state = campaign.state === 'open' ? 'Running' : campaign.state === 'closed' ? 'Completed' : 'Direct';
  const created = campaign.createdAt ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(campaign.createdAt)) : '';
  return `${state} · ACTS Seeding Campaign${created ? ` · ${created}` : ''}`;
}
function populateCampaignSelect(selected = activeCampaign) {
  campaignSelect.replaceChildren();
  const choices = [...discoveredCampaigns];
  if (selected && !choices.some((campaign) => campaign.id === selected.id)) choices.unshift(selected);
  if (!choices.length) {
    const option = document.createElement('option');
    option.textContent = 'No discovered campaigns';
    option.value = '';
    campaignSelect.appendChild(option);
    campaignSelect.disabled = true;
    return;
  }
  choices.forEach((campaign) => {
    const option = document.createElement('option');
    option.value = campaign.id;
    option.textContent = campaignLabel(campaign);
    campaignSelect.appendChild(option);
  });
  campaignSelect.disabled = discoveredCampaigns.length === 0;
  campaignSelect.value = selected?.id || choices[0].id;
}
function campaignForId(id) {
  if (activeCampaign?.id === id) return activeCampaign;
  return discoveredCampaigns.find((campaign) => campaign.id === id) || null;
}
function updateDeepLink(campaign) {
  const url = new URL(window.location.href);
  url.searchParams.set('ref', campaign.ref);
  window.history.replaceState(null, '', url);
}
function showEmptyState(heading, detail) {
  const wrapper = document.createElement('div');
  const strong = document.createElement('strong');
  strong.textContent = heading;
  wrapper.append(strong, document.createTextNode(detail));
  emptyState.replaceChildren(wrapper);
  emptyState.hidden = false;
  dashboard.hidden = true;
}
async function loadCampaign(campaign, { automatic = false } = {}) {
  const source = campaignFetchSource(campaign);
  if (!source) {
    setFetchError('This campaign does not have a safe public source.');
    return;
  }
  const key = campaign.ref;
  const now = Date.now();
  if (now - (lastFetchStarted.get(key) || 0) < POLL_INTERVAL_MS) {
    const retained = lastGoodSnapshots.get(key);
    if (retained && activeCampaign?.id === campaign.id) renderSnapshot(retained, campaign);
    else if (activeCampaign?.id === campaign.id) {
      showEmptyState('Campaign status unavailable', 'A recent fetch failed. Automatic retry waits at least one minute.');
    }
    return;
  }
  lastFetchStarted.set(key, now);
  fetchError.hidden = true;
  try {
    const response = await fetch(snapshotUrl(source), { cache: 'no-store', credentials: 'omit', mode: 'cors' });
    if (!response.ok) {
      const message = response.status === 404
        ? 'Status unavailable. This campaign may predate campaign-status v1.'
        : `GitHub returned HTTP ${response.status}.`;
      throw new Error(message);
    }
    const snapshot = validateSnapshot(await response.json(), source.expectedBranch);
    lastGoodSnapshots.set(key, snapshot);
    if (activeCampaign?.id === campaign.id) renderSnapshot(snapshot, campaign);
  } catch (error) {
    if (activeCampaign?.id !== campaign.id) return;
    const retained = lastGoodSnapshots.get(key);
    if (retained) {
      renderSnapshot(retained, campaign);
      setFetchError(`Refresh failed: ${error.message} Showing the last good snapshot for ${campaign.ref}.`);
    } else {
      setFetchError(`Refresh failed: ${error.message}`);
      showEmptyState(
        'Campaign status unavailable',
        'This public campaign has no compatible snapshot. Older campaigns may predate live status publishing.'
      );
    }
  }
}
function selectCampaign(campaign, { automatic = false } = {}) {
  if (!campaign) return;
  fetchError.hidden = true;
  activeCampaign = campaign;
  populateCampaignSelect(campaign);
  updateDeepLink(campaign);
  const cached = lastGoodSnapshots.get(campaign.ref);
  if (cached) renderSnapshot(cached, campaign);
  else if (!automatic) showEmptyState('Loading campaign status', `Fetching ${campaign.ref} from the public repository.`);
  loadCampaign(campaign, { automatic });
}
async function discoverCampaigns(initialRef) {
  let discoveryError = null;
  try {
    const response = await fetch(PULLS_API_URL, { cache: 'no-store', credentials: 'omit', mode: 'cors' });
    if (!response.ok) throw new Error(`GitHub returned HTTP ${response.status}.`);
    discoveredCampaigns = sortCampaigns(await response.json());
  } catch (error) {
    discoveredCampaigns = [];
    discoveryError = error;
  }
  const selected = selectInitialCampaign(discoveredCampaigns, initialRef);
  populateCampaignSelect(selected);
  if (selected) {
    selectCampaign(selected);
    if (discoveryError) setFetchError(`Campaign discovery unavailable: ${discoveryError.message}`);
  } else {
    if (discoveryError) setFetchError(`Campaign discovery unavailable: ${discoveryError.message}`);
    showEmptyState('No campaigns available', 'No public campaign could be selected.');
  }
}
campaignSelect.addEventListener('change', () => {
  const selected = campaignForId(campaignSelect.value);
  if (selected) selectCampaign(selected);
});
const requestedRef = new URLSearchParams(window.location.search).get('ref');
const invalidRequestedRef = Boolean(requestedRef && !safeRef(requestedRef));
discoverCampaigns(requestedRef).then(() => {
  if (invalidRequestedRef) {
    setFetchError('The ?ref= deep link is not a safe Git ref. Loaded the newest discovered campaign instead.');
  }
});
setInterval(() => {
  const source = campaignFetchSource(activeCampaign);
  if (source?.poll && document.visibilityState === 'visible') loadCampaign(activeCampaign, { automatic: true });
}, POLL_INTERVAL_MS);
</script>
</body>
</html>
"""


def freshness_state(updated_at: str, now: datetime, stale_after_seconds: int = 900) -> str:
    """Return the dashboard freshness class for focused state tests."""

    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise StatusError("updated_at must be an ISO 8601 timestamp") from error
    if updated.tzinfo is None:
        raise StatusError("updated_at must include a timezone")
    age = max((now.astimezone(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds(), 0)
    if age >= stale_after_seconds:
        return "stale"
    if age >= stale_after_seconds / 2:
        return "aging"
    return "fresh"


def render(output: Path) -> None:
    """Write the static dashboard without changing the results report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        HTML_TEMPLATE.replace("__REPOSITORY__", REPOSITORY).replace(
            "__POLL_INTERVAL_MS__", str(POLL_INTERVAL_MS)
        ),
        encoding="utf-8",
    )


__all__ = ["freshness_state", "render", "validate_ref"]
