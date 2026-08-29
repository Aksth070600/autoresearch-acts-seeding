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


def render(status: dict[str, Any], *, deployed_commit: str) -> str:
    status = _validate(status, deployed_commit)
    campaign = status["campaign"]
    calibration = status.get("calibration")
    if isinstance(calibration, dict):
        timings = ", ".join(
            _milliseconds(value)
            for value in calibration.get("genesis_per_event_nanoseconds", [])
        )
        calibration_html = (
            f"<p>Five independent timings (ms/event): {_escape(timings)}<br>"
            f"Median: {_milliseconds(calibration.get('median_per_event_nanoseconds'))} ms/event<br>"
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
            "<tr>"
            f"<td>{_escape(attempt.get('slot'))}</td>"
            f"<td>{_escape(attempt.get('candidate'))}</td>"
            f"<td>{_escape(attempt.get('classification'))}</td>"
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
    control = status.get("control") or {}
    scheduler = status.get("scheduler") or {}
    finish_url = (
        "https://github.com/Aksth070600/autoresearch-acts-seeding/"
        "actions/workflows/finish-campaign.yml?query=branch%3Amain"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Continuous owned-static ACTS Seeding v4</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:1800px}}table{{border-collapse:collapse;font-size:.86rem}}th,td{{border:1px solid #bbb;padding:.35rem;vertical-align:top}}th{{background:#fff;position:sticky;top:0}}code{{font-size:.82em;overflow-wrap:anywhere}}.warning{{border-left:4px solid #b66;padding-left:1rem}}</style></head>
<body><h1>Continuous owned-static ACTS Seeding v4 Development</h1>
<p><b>Campaign ID:</b> <code>{_escape(campaign.get("campaign_id"))}</code><br>
<b>Campaign branch:</b> <code>{_escape(campaign.get("branch"))}</code><br>
<b>Public control ID:</b> <code>{_escape(campaign.get("control_id"))}</code><br>
<b>Deployed campaign commit:</b> <code>{_escape(deployed_commit)}</code><br>
<b>Platform commit:</b> <code>{_escape(campaign.get("platform_commit"))}</code><br>
<b>Dataset and optimization Genesis:</b> <code>{_escape(campaign.get("scientific_genesis_commit"))}</code><br>
<b>ACTS commit:</b> <code>{_escape(campaign.get("acts_commit"))}</code><br>
<b>Protocol:</b> <code>{PROTOCOL_ID}</code>, revision {PROTOCOL_REVISION}<br>
<b>Dataset:</b> <code>{DATASET_ID}</code><br>
<b>Control:</b> {_escape(control.get("state"))}; <b>scheduler:</b> {_escape(scheduler.get("state"))}; <b>next:</b> {_escape(scheduler.get("next_category"))}</p>
<p><a href="{finish_url}" target="_blank" rel="noopener noreferrer">Finish campaign through the authenticated main workflow</a></p>
<p class="warning">Only exact protocol-revision-2 evidence for the canonical owned-static dataset is displayed. Pilot revision 1, v2, v3, generated-input v4, and the shared Athena dump are excluded.</p>
<h2>Fresh campaign Genesis calibration</h2>{calibration_html}
<h2>Composition</h2><p>{_escape(counts.get("major", 0))} major, {_escape(counts.get("minor", 0))} minor, {_escape(counts.get("combination", 0))} combination. Completed exact blocks: {_escape(composition.get("completed_blocks", 0))}.</p>
<h2>Every immutable attempt</h2>
<table><thead><tr><th>Slot</th><th>Candidate</th><th>Class</th><th>Mechanism</th><th>Validity</th><th>ms/event</th><th>Timing class</th><th>Matched/selected</th><th>Fake/track</th><th>Duplicate/track</th><th>Build s</th><th>Total s</th><th>Wall s</th><th>Peak RSS KiB</th><th>Overall</th><th>Implementation</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<p>The final archive requires a regular merge commit, never squash. The campaign worker does not merge it and does not run Evaluation.</p>
</body></html>"""


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
