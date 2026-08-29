#!/usr/bin/env python3
"""Render the exact revision-2 owned-static continuous campaign dashboard."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from continuous_campaign import DATASET_ID, STATUS_SCHEMA

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATUS = (
    PROJECT_ROOT / "orchestration-files" / "acts-v4-continuous-campaign" / "status.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "site" / "static-v4" / "index.html"


def _fraction(value: Any) -> str:
    if not isinstance(value, dict):
        return "unavailable"
    return f"{value.get('numerator')}/{value.get('denominator')}"


def _ns(value: Any) -> str:
    return f"{value / 1_000_000:.6f}" if isinstance(value, int) else "unavailable"


def _rates(stats: dict[str, Any]) -> tuple[str, str, str]:
    selected = stats.get("nTotalParticles")
    matched = stats.get("nTotalMatchedParticles")
    tracks = stats.get("nTotalTracks")
    fake = stats.get("nTotalFakeTracks")
    duplicate = stats.get("nTotalDuplicateTracks")
    return f"{matched}/{selected}", f"{fake}/{tracks}", f"{duplicate}/{tracks}"


def render(status: dict[str, Any]) -> str:
    if (
        status.get("schema") != STATUS_SCHEMA
        or status.get("campaign", {}).get("protocol_revision") != 2
        or status.get("campaign", {}).get("dataset_id") != DATASET_ID
    ):
        raise ValueError(
            "continuous report accepts exact revision-2 canonical static-v4 status only"
        )
    calibration = status.get("calibration")
    if isinstance(calibration, dict) and "genesis_per_event_nanoseconds" in calibration:
        genesis_values = ", ".join(
            _ns(value) for value in calibration["genesis_per_event_nanoseconds"]
        )
        median = _ns(calibration.get("median_per_event_nanoseconds"))
        envelope = _fraction(calibration.get("relative_empirical_noise_envelope"))
        genesis = (
            f"<p>Five independent timings (ms/event): {genesis_values}<br>"
            f"Median: {median} ms/event<br>Empirical noise envelope: {envelope}. "
            "This is not a confidence level.</p>"
        )
    else:
        genesis = "<p>Fresh five-process Genesis calibration is pending.</p>"

    rows = []
    for attempt in status.get("attempts", []):
        stats = attempt.get("stats") or {}
        efficiency, fake, duplicate = _rates(stats)
        timing = attempt.get("timing") or {}
        resources = attempt.get("resources") or {}
        latency = attempt.get("latency") or {}
        classification = attempt.get("scientific_classification") or {}
        timing_class = (classification.get("timing") or {}).get("label", "invalid")
        overall = classification.get("overall", "invalid")
        rows.append(
            "<tr>"
            f"<td>{attempt['slot']}</td>"
            f"<td>{html.escape(attempt['candidate'])}</td>"
            f"<td>{html.escape(attempt['classification'])}</td>"
            f"<td><code>{html.escape(attempt['mechanism_key'])}</code></td>"
            f"<td>{html.escape(attempt['status'])}</td>"
            f"<td>{_ns(timing.get('per_event_nanoseconds'))}</td>"
            f"<td>{html.escape(timing_class)}</td>"
            f"<td>{efficiency}</td><td>{fake}</td><td>{duplicate}</td>"
            f"<td>{html.escape(str(latency.get('preparation_seconds', 'unavailable')))}</td>"
            f"<td>{html.escape(str(latency.get('build_seconds', 'unavailable')))}</td>"
            f"<td>{html.escape(str(latency.get('queue_to_immutable_record_seconds', 'unavailable')))}</td>"
            f"<td>{html.escape(str(resources.get('wall_seconds', 'unavailable')))}</td>"
            f"<td>{html.escape(str(resources.get('peak_rss_kb', 'unavailable')))}</td>"
            f"<td>{html.escape(overall)}</td>"
            f"<td><code>{html.escape(attempt['implementation_commit'])}</code></td>"
            f"<td><code>{html.escape(str(attempt.get('loaded_dso_manifest_sha256')))}</code></td>"
            "</tr>"
        )
    campaign = status["campaign"]
    composition = status["composition"]
    control = status["control"]
    corrections = (
        "".join(
            f"<li><code>{html.escape(str(item.get('id', 'correction')))}</code>: "
            f"{html.escape(str(item.get('resolution', item)))}</li>"
            for item in status.get("corrections", [])
        )
        or "<li>None</li>"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Continuous owned-static ACTS Seeding v4</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:1800px}}table{{border-collapse:collapse;font-size:.86rem}}th,td{{border:1px solid #bbb;padding:.35rem;vertical-align:top}}th{{position:sticky;top:0;background:#fff}}code{{font-size:.82em;overflow-wrap:anywhere}}.warning{{border-left:4px solid #b66;padding-left:1rem}}</style></head>
<body><h1>Continuous owned-static ACTS Seeding v4 Development</h1>
<p><b>Campaign:</b> <code>{html.escape(campaign["campaign_id"])}</code><br>
<b>Platform commit:</b> <code>{campaign["platform_commit"]}</code><br>
<b>Dataset and optimization Genesis commit:</b> <code>{campaign["scientific_genesis_commit"]}</code><br>
<b>ACTS commit:</b> <code>{campaign["acts_commit"]}</code><br>
<b>Protocol:</b> <code>{campaign["protocol_id"]}</code>, revision {campaign["protocol_revision"]}<br>
<b>Dataset:</b> <code>{campaign["dataset_id"]}</code><br>
<b>Control:</b> {html.escape(control["state"])}; <b>scheduler:</b> {html.escape(status["scheduler"]["state"])}; <b>next category:</b> {html.escape(str(status["scheduler"]["next_category"]))}</p>
<p class="warning">Only exact protocol-revision-2 evidence for the canonical owned-static dataset is shown. Pilot revision 1, v2, v3, generated-input v4, and the shared Athena dump are excluded.</p>
<h2>Fresh campaign Genesis calibration</h2>{genesis}
<h2>Composition</h2><p>{composition["counts"]["major"]} major, {composition["counts"]["minor"]} minor, {composition["counts"]["combination"]} combination. Completed exact blocks: {composition["completed_blocks"]}.</p>
<h2>Every immutable attempt</h2>
<table><thead><tr><th>Slot</th><th>Candidate</th><th>Class</th><th>Mechanism</th><th>Validity</th><th>ms/event</th><th>Timing class</th><th>Matched/selected</th><th>Fake/track</th><th>Duplicate/track</th><th>Preparation s</th><th>Build s</th><th>Total s</th><th>Wall s</th><th>Peak RSS KiB</th><th>Overall</th><th>Implementation</th><th>Loaded closure hash</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<h2>Correction history</h2><ul>{corrections}</ul>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    status = json.loads(args.status.read_text(encoding="utf-8"))
    output = render(status)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"wrote {args.output}")
    print(
        f"included {len(status.get('attempts', []))} exact revision-2 static-v4 attempts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
