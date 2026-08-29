#!/usr/bin/env python3
"""Render trusted public HTML from an exact active owned-static v4 status file."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

STATUS_SCHEMA = "acts-v4-owned-static-continuous-status-v1"
PROTOCOL_ID = "acts-seeding-v4-owned-static"
PROTOCOL_REVISION = 2
DATASET_ID = (
    "acts-seeding-v4-owned-static-"
    "a05ae8663452d52dc2b90e2fa5372091a2cb04feb8cce86646da9f6ccbc2f3fb"
)
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CATEGORY_COLORS = {
    "major": "#38bdf8",
    "minor": "#fbbf24",
    "combination": "#a78bfa",
}


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _milliseconds(value: Any) -> str:
    return f"{value / 1_000_000:.6f}" if isinstance(value, int) else "unavailable"


def _fraction(value: Any) -> str:
    if not isinstance(value, dict):
        return "unavailable"
    return f"{value.get('numerator')}/{value.get('denominator')}"


def _counts(stats: Any) -> tuple[str, str, str]:
    if not isinstance(stats, dict):
        return ("unavailable",) * 3
    return (
        f"{stats.get('nTotalMatchedParticles')}/{stats.get('nTotalParticles')}",
        f"{stats.get('nTotalFakeTracks')}/{stats.get('nTotalTracks')}",
        f"{stats.get('nTotalDuplicateTracks')}/{stats.get('nTotalTracks')}",
    )


def _validate(status: Any, deployed_commit: str) -> dict[str, Any]:
    if not isinstance(status, dict) or status.get("schema") != STATUS_SCHEMA:
        raise ValueError(
            "public dashboard accepts exact revision-2 static-v4 status only"
        )
    campaign = status.get("campaign")
    if (
        not isinstance(campaign, dict)
        or campaign.get("protocol_id") != PROTOCOL_ID
        or campaign.get("protocol_revision") != PROTOCOL_REVISION
        or campaign.get("dataset_id") != DATASET_ID
    ):
        raise ValueError(
            "public dashboard accepts exact revision-2 static-v4 status only"
        )
    if FULL_SHA.fullmatch(deployed_commit) is None:
        raise ValueError("deployed campaign commit must be a full Git SHA")
    if not isinstance(status.get("attempts"), list):
        raise ValueError("public static-v4 status attempts must be an array")
    return status


def _chart(attempts: list[dict[str, Any]], genesis_ns: Any) -> str:
    points = []
    for attempt in attempts:
        value = (attempt.get("timing") or {}).get("per_event_nanoseconds")
        slot = attempt.get("slot")
        if isinstance(value, int) and isinstance(slot, int):
            points.append((slot, value / 1_000_000, attempt))
    width, height = 920, 330
    left, right, top, bottom = 76, 30, 32, 58
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [value for _, value, _ in points]
    if isinstance(genesis_ns, int):
        values.append(genesis_ns / 1_000_000)
    if values:
        low, high = min(values), max(values)
        padding = max((high - low) * 0.18, 0.25)
        low -= padding
        high += padding
    else:
        low, high = 0.0, 1.0
    max_slot = max((slot for slot, _, _ in points), default=1)

    def x(slot: int) -> float:
        return left + (slot - 0.5) / max_slot * plot_width

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    grid = []
    for index in range(5):
        value = high - index * (high - low) / 4
        py = y(value)
        grid.append(
            f'<line x1="{left}" y1="{py:.2f}" x2="{width - right}" y2="{py:.2f}" class="grid-line"/>'
            f'<text x="{left - 10}" y="{py + 4:.2f}" text-anchor="end" class="axis-label">{value:.3f}</text>'
        )
    marks = []
    for slot, value, attempt in points:
        color = CATEGORY_COLORS.get(attempt.get("classification"), "#94a3b8")
        title = (
            f"Slot {slot}: {attempt.get('candidate')} - {value:.6f} ms/event - "
            f"{(attempt.get('scientific_classification') or {}).get('overall', 'invalid')}"
        )
        marks.append(
            f'<circle class="chart-point" cx="{x(slot):.2f}" cy="{y(value):.2f}" r="7" fill="{color}" '
            f'data-slot="{slot}" tabindex="0"><title>{_escape(title)}</title></circle>'
            f'<text x="{x(slot):.2f}" y="{height - bottom + 23}" text-anchor="middle" class="axis-label">{slot}</text>'
        )
    genesis_line = ""
    if isinstance(genesis_ns, int):
        genesis = genesis_ns / 1_000_000
        genesis_line = (
            f'<line x1="{left}" y1="{y(genesis):.2f}" x2="{width - right}" y2="{y(genesis):.2f}" class="genesis-line"/>'
            f'<text x="{width - right - 4}" y="{y(genesis) - 7:.2f}" text-anchor="end" class="genesis-label">Genesis {genesis:.6f}</text>'
        )
    return (
        f'<svg id="metric-chart" viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Candidate GridTriplet seeding time by immutable slot">'
        f'<text x="{left}" y="18" class="chart-title">GridTriplet seeding time (ms/event, lower is better)</text>'
        f"{''.join(grid)}{genesis_line}{''.join(marks)}"
        f'<text x="{width / 2}" y="{height - 8}" text-anchor="middle" class="axis-title">Immutable candidate slot</text>'
        f'<text x="18" y="{height / 2}" text-anchor="middle" transform="rotate(-90 18 {height / 2})" class="axis-title">ms/event</text>'
        "</svg>"
    )


def render(status: dict[str, Any], *, deployed_commit: str) -> str:
    status = _validate(status, deployed_commit)
    campaign = status["campaign"]
    calibration = status.get("calibration")
    genesis_ns = None
    if isinstance(calibration, dict):
        genesis_ns = calibration.get("median_per_event_nanoseconds")
        timings = ", ".join(
            _milliseconds(value)
            for value in calibration.get("genesis_per_event_nanoseconds", [])
        )
        calibration_html = (
            f"<p>Five independent timings (ms/event): {_escape(timings)}<br>"
            f"Median: {_milliseconds(genesis_ns)} ms/event<br>"
            "Empirical noise envelope: "
            f"{_escape(_fraction(calibration.get('relative_empirical_noise_envelope')))}. "
            "This is not a confidence level.</p>"
        )
    else:
        calibration_html = "<p>Fresh campaign calibration is pending.</p>"

    rows = []
    for attempt in status["attempts"]:
        if not isinstance(attempt, dict):
            raise ValueError("public static-v4 attempt is malformed")
        matched, fake, duplicate = _counts(attempt.get("stats"))
        scientific = attempt.get("scientific_classification") or {}
        timing_class = (scientific.get("timing") or {}).get("label", "invalid")
        latency = attempt.get("latency") or {}
        resources = attempt.get("resources") or {}
        rows.append(
            f'<tr data-classification="{_escape(attempt.get("classification"))}">'
            f"<td>{_escape(attempt.get('slot'))}</td>"
            f"<td>{_escape(attempt.get('candidate'))}</td>"
            f'<td><span class="badge {_escape(attempt.get("classification"))}">{_escape(attempt.get("classification"))}</span></td>'
            f"<td><code>{_escape(attempt.get('mechanism_key'))}</code></td>"
            f"<td>{_escape(attempt.get('status'))}</td>"
            f"<td>{_milliseconds((attempt.get('timing') or {}).get('per_event_nanoseconds'))}</td>"
            f"<td>{_escape(timing_class)}</td>"
            f"<td>{_escape(matched)}</td><td>{_escape(fake)}</td><td>{_escape(duplicate)}</td>"
            f"<td>{_escape(latency.get('build_seconds', 'unavailable'))}</td>"
            f"<td>{_escape(latency.get('queue_to_immutable_record_seconds', 'unavailable'))}</td>"
            f"<td>{_escape(resources.get('wall_seconds', 'unavailable'))}</td>"
            f"<td>{_escape(resources.get('peak_rss_kb', 'unavailable'))}</td>"
            f"<td>{_escape(scientific.get('overall', 'invalid'))}</td>"
            f"<td><code>{_escape(attempt.get('implementation_commit'))}</code></td>"
            "</tr>"
        )

    composition = status.get("composition") or {}
    counts = composition.get("counts") or {}
    total = max(sum(value for value in counts.values() if isinstance(value, int)), 1)
    cards = []
    for category, target in (("major", 50), ("minor", 25), ("combination", 25)):
        count = counts.get(category, 0)
        actual = count / total * 100
        fill = min(actual / target * 100, 100)
        cards.append(
            f'<article class="composition-card"><span class="eyebrow">{category}</span>'
            f"<strong>{count}</strong><span>{actual:.1f}% / {target}% target</span>"
            f'<div class="progress"><i style="width:{fill:.1f}%"></i></div></article>'
        )
    control = status.get("control") or {}
    scheduler = status.get("scheduler") or {}
    finish_url = (
        "https://github.com/Aksth070600/autoresearch-acts-seeding/"
        "actions/workflows/finish-campaign.yml?query=branch%3Amain"
    )
    script_data = json.dumps(
        [
            {
                "slot": attempt.get("slot"),
                "candidate": attempt.get("candidate"),
                "classification": attempt.get("classification"),
                "time": (attempt.get("timing") or {}).get("per_event_nanoseconds"),
                "efficiency": (
                    (attempt.get("stats") or {}).get("nTotalMatchedParticles", 0)
                    / (attempt.get("stats") or {}).get("nTotalParticles", 1)
                ),
                "rss": (attempt.get("resources") or {}).get("peak_rss_kb"),
                "latency": (attempt.get("latency") or {}).get(
                    "queue_to_immutable_record_seconds"
                ),
            }
            for attempt in status["attempts"]
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    chart = _chart(status["attempts"], genesis_ns)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Continuous owned-static ACTS Seeding v4</title>
<style>
:root{{--bg:#07111f;--panel:#101d2f;--panel2:#15263b;--text:#e5eef8;--muted:#9fb0c4;--line:#29415c;--cyan:#38bdf8;--amber:#fbbf24;--violet:#a78bfa;--green:#34d399}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at top right,#132a45 0,#07111f 42%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;line-height:1.45}}
main{{max-width:1500px;margin:auto;padding:32px 24px 64px}}h1{{margin:.2rem 0;font-size:clamp(1.8rem,4vw,3rem)}}h2{{margin:0 0 14px}}p{{color:var(--muted)}}code{{color:#c8e7ff;font-size:.84em;overflow-wrap:anywhere}}.eyebrow{{color:var(--cyan);font-size:.76rem;font-weight:800;text-transform:uppercase;letter-spacing:.12em}}
.hero,.panel,.controls,.composition-card{{background:linear-gradient(145deg,rgba(21,38,59,.96),rgba(11,25,42,.96));border:1px solid var(--line);border-radius:14px;box-shadow:0 12px 32px rgba(0,0,0,.22)}}.hero{{padding:28px;margin-bottom:18px}}.identity{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:7px 22px;margin-top:18px}}.identity div{{color:var(--muted)}}
.controls{{display:grid;grid-template-columns:minmax(230px,1fr) minmax(230px,1fr) auto;gap:14px;align-items:end;padding:16px;margin-bottom:18px}}label{{display:grid;gap:6px;color:var(--muted);font-size:.82rem;font-weight:700}}select,.finish-button{{border:1px solid #45617f;border-radius:8px;background:#0a1727;color:var(--text);padding:10px 12px;font:inherit}}.finish-button{{display:inline-flex;text-decoration:none;align-items:center;justify-content:center;background:#991b1b;border-color:#ef4444;font-weight:800}}.finish-button:hover{{background:#b91c1c}}
.warning{{border-left:4px solid var(--amber);padding:10px 14px;background:rgba(251,191,36,.08);color:#f8d991}}.composition-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0}}.composition-card{{padding:16px;display:grid;gap:4px}}.composition-card strong{{font-size:1.8rem}}.progress{{height:7px;background:#23374e;border-radius:9px;overflow:hidden;margin-top:8px}}.progress i{{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--violet));border-radius:inherit}}
.panel{{padding:20px;margin:18px 0;overflow:hidden}}#metric-chart{{display:block;width:100%;height:auto;min-height:280px;background:#091728;border:1px solid var(--line);border-radius:10px}}.grid-line{{stroke:#233b55;stroke-width:1}}.genesis-line{{stroke:var(--green);stroke-width:2;stroke-dasharray:7 5}}.genesis-label{{fill:var(--green);font-size:12px}}.axis-label,.axis-title,.chart-title{{fill:var(--muted);font-size:12px}}.chart-title{{fill:var(--text);font-weight:700}}.chart-point{{stroke:#e5eef8;stroke-width:1.5;transition:r .15s}}.chart-point:hover,.chart-point:focus{{r:10;outline:none}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:10px}}table{{border-collapse:collapse;width:100%;min-width:1450px;font-size:.82rem}}th,td{{padding:9px 10px;border-bottom:1px solid #223a54;text-align:right;vertical-align:top}}th{{position:sticky;top:0;background:#14253a;color:#bcd0e5}}th:nth-child(2),td:nth-child(2),th:nth-child(4),td:nth-child(4){{text-align:left}}tbody tr:hover{{background:#132942}}.badge{{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:800}}.badge.major{{background:rgba(56,189,248,.15);color:var(--cyan)}}.badge.minor{{background:rgba(251,191,36,.15);color:var(--amber)}}.badge.combination{{background:rgba(167,139,250,.15);color:var(--violet)}}.footer-note{{font-size:.9rem}}
@media(max-width:800px){{main{{padding:18px 12px 40px}}.controls,.composition-grid{{grid-template-columns:1fr}}}}
</style></head>
<body><main><header class="hero"><span class="eyebrow">Live Development campaign</span><h1>Continuous owned-static ACTS Seeding v4</h1>
<div class="identity"><div><b>Campaign ID</b><br><code>{_escape(campaign.get("campaign_id"))}</code></div><div><b>Branch</b><br><code>{_escape(campaign.get("branch"))}</code></div><div><b>Public control ID</b><br><code>{_escape(campaign.get("control_id"))}</code></div><div><b>Deployed commit</b><br><code>{_escape(deployed_commit)}</code></div><div><b>Protocol</b><br><code>{PROTOCOL_ID}</code>, revision {PROTOCOL_REVISION}</div><div><b>Dataset and optimization Genesis</b><br><code>{_escape(campaign.get("scientific_genesis_commit"))}</code></div></div></header>
<section class="controls" aria-label="Campaign controls"><label>Campaign<select id="campaign-select" disabled><option>{_escape(campaign.get("campaign_id"))}</option></select></label><label>Chart metric<select id="metric-select"><option value="time">GridTriplet time</option><option value="efficiency">Particle efficiency</option><option value="rss">Peak RSS</option><option value="latency">Queue-to-record latency</option></select></label><a class="finish-button" href="{finish_url}" target="_blank" rel="noopener noreferrer">Finish campaign</a></section>
<p class="warning">Only exact protocol-revision-2 evidence for the canonical owned-static dataset is displayed. Pilot revision 1, v2, v3, generated-input v4, and the shared Athena dump are excluded. Pages availability never controls science or authenticated stop checks.</p>
<section class="composition-grid">{"".join(cards)}</section>
<section class="panel"><h2>Fresh Genesis calibration</h2>{calibration_html}<p><b>Control:</b> {_escape(control.get("state"))} · <b>Scheduler:</b> {_escape(scheduler.get("state"))} · <b>Next:</b> {_escape(scheduler.get("next_category"))}</p></section>
<section class="panel"><h2>Candidate trend</h2>{chart}<p id="chart-status" aria-live="polite">Showing GridTriplet seeding time.</p></section>
<section class="panel"><h2>Every immutable attempt</h2><div class="table-wrap"><table><thead><tr><th>Slot</th><th>Candidate</th><th>Class</th><th>Mechanism</th><th>Validity</th><th>ms/event</th><th>Timing class</th><th>Matched/selected</th><th>Fake/track</th><th>Duplicate/track</th><th>Build s</th><th>Total s</th><th>Wall s</th><th>Peak RSS KiB</th><th>Overall</th><th>Implementation</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>
<p class="footer-note">Platform commit <code>{_escape(campaign.get("platform_commit"))}</code> · ACTS <code>{_escape(campaign.get("acts_commit"))}</code> · Dataset <code>{DATASET_ID}</code>. The final archive requires a regular merge commit, never squash. The campaign worker does not merge it and does not run Evaluation.</p>
<script>
const attempts = {script_data};
const metricConfig = {{
  time: {{label: 'GridTriplet seeding time', unit: 'ms/event', better: 'lower', value: row => row.time / 1e6}},
  efficiency: {{label: 'Particle efficiency', unit: 'matched / selected', better: 'higher', value: row => row.efficiency}},
  rss: {{label: 'Peak RSS', unit: 'KiB', better: 'diagnostic', value: row => row.rss}},
  latency: {{label: 'Queue-to-record latency', unit: 'seconds', better: 'lower', value: row => Number(row.latency)}}
}};
const colors = {{major:'#38bdf8', minor:'#fbbf24', combination:'#a78bfa'}};
const svg = document.getElementById('metric-chart');
const statusLine = document.getElementById('chart-status');
function element(name, attributes, text) {{
  const node = document.createElementNS('http://www.w3.org/2000/svg', name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text !== undefined) node.textContent = text;
  return node;
}}
function renderMetric(metric) {{
  const config = metricConfig[metric];
  const rows = attempts.map(row => ({{...row, value: config.value(row)}})).filter(row => Number.isFinite(row.value));
  const width=920, height=330, left=76, right=30, top=32, bottom=58;
  const plotWidth=width-left-right, plotHeight=height-top-bottom;
  const values=rows.map(row=>row.value); let low=Math.min(...values), high=Math.max(...values);
  if (!values.length) {{ low=0; high=1; }} const padding=Math.max((high-low)*.18, Math.abs(high)*.002, .000001); low-=padding; high+=padding;
  const maxSlot=Math.max(...rows.map(row=>row.slot),1); const x=slot=>left+(slot-.5)/maxSlot*plotWidth; const y=value=>top+(high-value)/(high-low)*plotHeight;
  svg.replaceChildren(); svg.append(element('text',{{x:left,y:18,class:'chart-title'}},`${{config.label}} (${{config.unit}}, ${{config.better}})`));
  for(let index=0;index<5;index++){{const value=high-index*(high-low)/4, py=y(value);svg.append(element('line',{{x1:left,y1:py,x2:width-right,y2:py,class:'grid-line'}}));svg.append(element('text',{{x:left-10,y:py+4,'text-anchor':'end',class:'axis-label'}},value.toFixed(metric==='efficiency'?6:3)));}}
  rows.forEach(row=>{{const circle=element('circle',{{class:'chart-point',cx:x(row.slot),cy:y(row.value),r:7,fill:colors[row.classification]||'#94a3b8','data-slot':row.slot,tabindex:0}});circle.append(element('title',{{}},`Slot ${{row.slot}}: ${{row.candidate}} · ${{row.value}} ${{config.unit}}`));svg.append(circle);svg.append(element('text',{{x:x(row.slot),y:height-bottom+23,'text-anchor':'middle',class:'axis-label'}},row.slot));}});
  svg.append(element('text',{{x:width/2,y:height-8,'text-anchor':'middle',class:'axis-title'}},'Immutable candidate slot'));
  svg.append(element('text',{{x:18,y:height/2,'text-anchor':'middle',transform:`rotate(-90 18 ${{height/2}})`,class:'axis-title'}},config.unit));
  svg.setAttribute('aria-label',`${{config.label}} by immutable candidate slot`); statusLine.textContent=`Showing ${{config.label}}.`;
}}
document.getElementById('metric-select').addEventListener('change', event => renderMetric(event.target.value));
</script></main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--deployed-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = json.loads(args.status.read_text(encoding="utf-8"))
    output = render(status, deployed_commit=args.deployed_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"wrote trusted active campaign dashboard: {args.output}")
    print(f"deployed campaign commit: {args.deployed_commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
